# =============================================================
#  qa_bia.py  —  SISTEMA QA AUTOMATIZADO DE ACTAS BIA ENERGY
#  Motor de IA: Groq (Llama)
#  Version: 2.0
# =============================================================

import os
import json
import time
import csv
import io
import re
import requests
import pdfplumber
from groq import Groq
from datetime import datetime, date
from twilio.rest import Client as TwilioClient

# GitHub Actions: leer de variables de entorno
if os.environ.get('GROQ_API_KEY'):
    class config:
        METABASE_CSV_URL     = "https://bia.metabaseapp.com/public/question/5ec265f5-182d-409d-bfbd-45303880da2d.csv"
        GROQ_API_KEY         = os.environ['GROQ_API_KEY']
        GROQ_MODEL           = "llama-3.1-8b-instant"
        SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL', '')
        TWILIO_ACCOUNT_SID   = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        TWILIO_AUTH_TOKEN    = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        TWILIO_FROM_WHATSAPP = "whatsapp:+14155238886"
        TWILIO_TO_WHATSAPP   = "whatsapp:+57TUNUMERODECELULAR"
        MODO_PRUEBA          = False
        MODO_UNICO           = True
        ACTAS_PRUEBA         = 2
        FECHA_INICIO         = "2026-05-02"
        PAUSA_GROQ_SEGUNDOS  = 5
        INTERVALO_SEGUNDOS   = 300
        ARCHIVO_PROCESADOS   = "actas_procesadas.json"
        CARPETA_REPORTES     = "reportes_qa"
        TIPOS_SERVICIO_VALIDOS = ["Instalación", "Visita previa"]
        ESTADOS_EXITOSOS       = ["CLOSURE_SUCCESSFUL", "COMPLETED"]
        ESTADOS_FALLIDOS       = ["CLOSURE_FAILED", "ELECTRICIAN_FAILED_VISIT"]
        ESTADOS_ANALIZAR       = ESTADOS_EXITOSOS + ESTADOS_FALLIDOS
        OR_PLANNERS = {
            "ESSA":   "Ervison Plata",
            "EPM":    "Ervison Plata",
            "AIRE":   "Ervison Plata",
            "AIR-E":  "Ervison Plata",
            "AFINIA": "Ervison Plata",
        }
        PLANNER_DEFAULT = "Dinovi Sanchez"
        SLACK_USER_IDS = {
            "Ervison Plata":  "D090K7XK0R1",
            "Dinovi Sanchez": "D06PM8PT6GY",
        }
else:
    import config

cliente_groq = Groq(api_key=config.GROQ_API_KEY)

CATALOGO_CAUSAS_FALLA = [
    "Cliente abandona proceso",
    "Cliente no conoce alcance de la actividad",
    "Documentacion incompleta",
    "OR no conoce requerimiento descargos",
    "OR no tiene conocimiento de la actividad",
    "Propietario no conoce alcance de la actividad",
    "Datos de ubicacion erroneos",
    "Permisos de ingreso",
    "Error en la creacion de la OT",
    "Falta activar frontera para realizar actividad",
    "La OT ya fue realizada",
    "OT Duplicada",
    "OT Fuera de SLA",
    "No se cancelo actividad apesar de solicitud del cliente",
    "Falla en la red, debe normalizar OR",
    "OR exige adecuaciones adicionales",
    "OR no asiste o llega tarde",
    "OR no cumple requerimientos de la actividad",
    "Permisos del municipio",
    "Documentacion SST",
    "Coordinador no confirma actividad",
    "Contratista/Tecnico no llega a la hora programada",
    "Informacion faltante/erronea en acta",
    "Confirmacion de alcance en actividad",
    "Fallas en el alistamiento operativo",
    "Contratista no asiste o llega tarde",
    "Error en alcance",
    "Certificados de equipo",
    "Equipos en sitio",
    "Averia de equipo pre instalacion",
    "Sim card",
    "Permisos propietario",
    "Falla cliente-Gestion",
    "Agendamiento cliente",
    "Demora en el acceso",
    "Acceso a gabinete",
    "Cliente retira los equipos",
    "Cliente en reclamacion",
    "Cliente realizo pago",
    "Cliente suspendido",
    "Cliente fuera del mercado BIA",
    "Cliente en cobro juridico",
    "Acuerdo de pago en punto",
    "Animales impiden acceso a la medida",
    "Riesgo electrico",
    "Codigo duplicado",
    "Lluvias",
    "Acceso a la medida",
    "Manifestaciones / bloqueos / carretera cerrada",
    "Cobertura en datos moviles",
    "Medidor averiado",
    "Configuracion del modem",
    "No hay registro del medidor BIA encontrado",
    "No se encuentra medidor",
    "No se encuentra modem",
    "Modem averiado",
    "Telemedida conecta y normalizada antes de visita",
    "Equipos averiados",
    "Se requiere acompañamiento policial",
    "Sin acceso a la plataforma para pagar",
    "Medida es compartida",
    "Predio desocupado, imposibilidad de acceso a la medida",
]

def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def cargar_procesados():
    if os.path.exists(config.ARCHIVO_PROCESADOS):
        with open(config.ARCHIVO_PROCESADOS, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_procesado(acta_id):
    procesados = cargar_procesados()
    if acta_id not in procesados:
        procesados.append(acta_id)
    with open(config.ARCHIVO_PROCESADOS, "w", encoding="utf-8") as f:
        json.dump(procesados, f, ensure_ascii=False, indent=2)

def identificar_planner(or_norm):
    for or_key, planner in config.OR_PLANNERS.items():
        if or_key.upper() in or_norm.upper():
            return planner
    return config.PLANNER_DEFAULT

def cargar_inventario_wms():
    print("  WMS pendiente de configurar. Medidores apareceran como Pendiente.")
    return {}

def obtener_actas_nuevas():
    print(f"[{ahora()}] Descargando actas desde Metabase...")
    try:
        respuesta = requests.get(config.METABASE_CSV_URL, timeout=30)
        respuesta.raise_for_status()
    except Exception as e:
        print(f"  ERROR descargando CSV: {e}")
        return []

    procesados   = cargar_procesados()
    fecha_inicio = date.fromisoformat(config.FECHA_INICIO)
    lector       = csv.DictReader(io.StringIO(respuesta.content.decode('utf-8')))
    pendientes   = []
    omitidas     = 0

    for fila in lector:
        tipo       = fila.get("Tipo de servicio", "").strip()
        estado     = fila.get("electrician_status_id", "").strip()
        acta_id    = fila.get("id", "").strip()
        pdf_url    = fila.get("act_pdf_url", "").strip()
        fecha_str  = fila.get("start", "").strip()
        tiene_acta = fila.get("Tiene Acta", "").strip()

        if not (tipo in config.TIPOS_SERVICIO_VALIDOS
                and estado in config.ESTADOS_ANALIZAR
                and tiene_acta == "Con Acta"
                and pdf_url):
            continue
        try:
            if date.fromisoformat(fecha_str[:10]) < fecha_inicio:
                omitidas += 1
                continue
        except Exception:
            continue
        if acta_id in procesados:
            continue
        pendientes.append(fila)

    pendientes.sort(key=lambda x: (x.get("start", ""), x.get("created_at", "")))
    print(f"  {len(pendientes)} acta(s) nueva(s) (omitidas por fecha: {omitidas})")

    if config.MODO_PRUEBA and len(pendientes) > config.ACTAS_PRUEBA:
        print(f"  [MODO PRUEBA] Solo {config.ACTAS_PRUEBA} de {len(pendientes)}.")
        pendientes = pendientes[:config.ACTAS_PRUEBA]

    return pendientes

def descargar_y_leer_pdf(url):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        texto = ""
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            for pagina in pdf.pages:
                try:
                    t = pagina.extract_text()
                    if t:
                        texto += t + "\n"
                except Exception:
                    continue
        return texto.strip() if texto.strip() else None
    except Exception as e:
        print(f"  ERROR leyendo PDF: {e}")
        return None

def analizar_acta(texto_pdf, tipo_servicio, estado_electricista, internal_bia_code=""):
    tipo_label = "INSTALACION" if "nstala" in tipo_servicio else "VISITA PREVIA"
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    catalogo_str = "\n".join(f"- {c}" for c in CATALOGO_CAUSAS_FALLA)

    prompt = f"""
Eres un auditor QA experto en ordenes de trabajo de medicion electrica en Colombia para BIA Energy.

TIPO DE SERVICIO: {tipo_label}
RESULTADO EN APP: {"EXITOSA" if es_exitosa else "FALLIDA"}
CODIGO INTERNO BIA: {internal_bia_code}

INSTRUCCIONES CRITICAS:
- Devuelve UNICAMENTE un JSON valido sin texto adicional ni bloques de codigo.
- NO inventes datos. Si un campo no esta en el acta usa null o "NO APLICA".
- "serie_coincide_foto": busca la serie del medidor en el texto OCR de la seccion "Registro fotografico" cercana. true si la serie aparece literalmente, false si no, null si no hay foto.
- Para "observaciones_tecnicas": redacta un parrafo tecnico denso que incluya hora de llegada, lo encontrado, lo instalado con seriales, pruebas, resultado final.

REGLAS POR TIPO DE MEDIDA:
- DIRECTA: tcs_*, tps_*, bloque_pruebas_*, cable_control_* TODOS con "aplica": false.
- SEMIDIRECTA: tps_* con "aplica": false. tcs_*, bloque_pruebas_*, cable_control_* aplican.
- INDIRECTA: TODOS aplican.

REGLAS POR TIPO DE SERVICIO:
- INSTALACION: campos *_instalado deben llenarse si se instalo el equipo (se_instalo: true) o marcarse false.
- VISITA PREVIA: TODOS los *_instalado tienen "aplica": false.

JSON ESPERADO:
{{
  "tipo_medida": "DIRECTA | SEMIDIRECTA | INDIRECTA",
  "factor_medida": "<numero como string>",
  "estado_ot": "EXITOSA | FALLIDA",

  "transformador": {{
    "tiene": <bool>,
    "numero": "<o null>",
    "capacidad_kva": "<o null>",
    "ubicacion": "<o null>",
    "tipo_uso": "COMPARTIDO | EXCLUSIVO | NO APLICA"
  }},

  "medidor_encontrado": {{
    "serie": "<o null>",
    "marca": "<o null>",
    "referencia": "<o null>",
    "lectura_activa_kwh": "<o null>",
    "lectura_reactiva_kvarh": "<o null>",
    "serie_coincide_foto": <bool o null>,
    "observacion_serie_foto": "<si no coincide explica brevemente, null si coincide>"
  }},

  "medidor_instalado": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "serie": "<o null>",
    "marca": "<o null>",
    "referencia": "<o null>",
    "lectura_activa_kwh": "<o null>",
    "serie_coincide_foto": <bool o null>,
    "observacion_serie_foto": "<o null>"
  }},

  "sellos_instalados": {{
    "aplica": <bool>,
    "total": <int>,
    "todos_completos": <bool>,
    "campos_faltantes": ["<descripcion del sello/campo faltante>"]
  }},

  "medidor_respaldo_instalado": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "serie": "<o null>",
    "marca": "<o null>"
  }},

  "telemedida_encontrada": {{
    "tiene": <bool>,
    "ip": "<o null>",
    "puerto": "<o null>",
    "serie": "<o null>",
    "marca": "<o null>",
    "imei": "<o null>"
  }},

  "telemedida_instalada": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "ip": "<o null>",
    "puerto": "<o null>",
    "serie": "<o null>",
    "marca": "<o null>",
    "imei": "<o null>",
    "operador_sim": "<o null>",
    "serie_sim": "<o null>"
  }},

  "totalizador_encontrado": {{
    "tiene": <bool>,
    "marca": "<o null>",
    "capacidad_a": "<o null>",
    "fases": "<o null>"
  }},

  "totalizador_instalado": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "marca": "<o null>",
    "capacidad_a": "<o null>",
    "fases": "<o null>"
  }},

  "cables_potencia_encontrados": {{
    "tiene": <bool>,
    "calibre_parcial": "<o null>",
    "cables_por_fase_parcial": "<o null>",
    "calibre_acometida": "<o null>",
    "cables_por_fase_acometida": "<o null>"
  }},

  "cables_potencia_instalados": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "calibre_parcial": "<o null>",
    "cables_por_fase_parcial": "<o null>",
    "calibre_acometida": "<o null>",
    "cables_por_fase_acometida": "<o null>"
  }},

  "tcs_encontrados":      {{ "aplica": <bool>, "tiene": <bool>, "detalles": "<o null>" }},
  "tcs_instalados":       {{ "aplica": <bool>, "se_instalo": <bool>, "detalles": "<o null>" }},
  "tps_encontrados":      {{ "aplica": <bool>, "tiene": <bool>, "detalles": "<o null>" }},
  "tps_instalados":       {{ "aplica": <bool>, "se_instalo": <bool>, "detalles": "<o null>" }},

  "bloque_pruebas_encontrado": {{ "aplica": <bool>, "tiene": <bool>, "marca": "<o null>", "tipo": "<o null>" }},
  "bloque_pruebas_instalado":  {{ "aplica": <bool>, "se_instalo": <bool>, "marca": "<o null>", "tipo": "<o null>" }},

  "cable_control_encontrado": {{ "aplica": <bool>, "tiene": <bool>, "marca": "<o null>", "calibre_corriente": "<o null>", "calibre_tension": "<o null>", "metros": "<o null>" }},
  "cable_control_instalado":  {{ "aplica": <bool>, "se_instalo": <bool>, "marca": "<o null>", "calibre_corriente": "<o null>", "calibre_tension": "<o null>", "metros": "<o null>" }},

  "pruebas_funcionamiento": {{
    "se_realizaron": <bool>,
    "resumen": "<resumen tecnico de 2-3 lineas, null si dice No>"
  }},

  "equipo_patron": {{
    "se_uso": <bool>,
    "resumen": "<resumen de mediciones V/A/W clave, null si no se uso>"
  }},

  "diagrama_unifilar": {{ "tiene_foto": <bool> }},

  "observaciones_tecnicas": "<resumen tecnico denso de la actividad>",

  "or_firma": "SI | NO",

  "validaciones": {{
    "campos_completos": <bool>,
    "coherencia": "COHERENTE | INCOHERENTE | INCOMPLETO",
    "errores_encontrados": ["lista de errores reales"]
  }},

  "tipificacion_falla": {{
    "responsable": "<EXACTAMENTE uno del CATALOGO_CAUSAS, solo si FALLIDA>",
    "categoria_falla": "Cliente | Operador de Red | BIA | Contratista | Documentacion | Equipo | Acceso | Externo",
    "actor_a_contactar": "Cliente | Operador de Red | BIA | Contratista",
    "criticidad": "ALTA | MEDIA | BAJA",
    "causa_raiz": "<una linea concreta>",
    "detalle": "<2-3 lineas basadas en el acta>",
    "accion_inmediata": "<24 horas>",
    "requiere_reprogramacion": <bool>,
    "prerequisitos_reprogramacion": ["<requisito>"],
    "mejora": "<accion correctiva estructural>",
    "cinco_por_que": [
      "1. Por que la OT fue fallida? Porque [razon]",
      "2. Por que [problema]? Porque [causa]",
      "3. Por que [causa]? Porque [razon de fondo]",
      "4. Por que esto afecta? Porque [impacto]",
      "5. Por que no se corrigio? Porque [limitacion]"
    ]
  }},

  "observacion_automatica": "<texto listo para copiar en la app>",
  "alertas_qa": ["alertas menores"]
}}

CATALOGO_CAUSAS (si FALLIDA, responsable DEBE ser EXACTAMENTE uno copiado literal):
{catalogo_str}

CRITERIO DE CRITICIDAD:
- ALTA: bloquea SLA, riesgo electrico, manifestaciones, daño a equipo, cliente en cobro juridico, codigo duplicado, OT fuera de SLA.
- MEDIA: requiere reprogramar, OR/cliente ausente, documentacion faltante, demora.
- BAJA: ajustes menores, lluvias, configuracion modem.

REGLA OR_FIRMA:
- SI solo si "El Operador de Red asistio" dice "Si" Y hay nombre, cedula y telefono reales (no guiones).
- NO en cualquier otro caso.

--- TEXTO DEL ACTA ---
{texto_pdf[:7500]}
"""

    intentos = 3
    for intento in range(1, intentos + 1):
        try:
            respuesta = cliente_groq.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            texto = respuesta.choices[0].message.content.strip()
            if "```json" in texto:
                texto = texto.split("```json")[1].split("```")[0].strip()
            elif "```" in texto:
                texto = texto.split("```")[1].split("```")[0].strip()
            return json.loads(texto)
        except json.JSONDecodeError:
            if intento == intentos:
                return None
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate_limit" in msg.lower():
                espera = 30
                m = re.search(r"try again in (\d+\.?\d*)s", msg)
                if m:
                    espera = int(float(m.group(1))) + 2
                if intento < intentos:
                    print(f"  Limite Groq. Esperando {espera}s...")
                    time.sleep(espera)
                else:
                    return None
            else:
                print(f"  ERROR Groq: {e}")
                return None
    return None

def guardar_reporte(acta, resultado_qa):
    os.makedirs(config.CARPETA_REPORTES, exist_ok=True)
    nombre_ot  = acta.get("title", acta.get("id", "sin_titulo")).replace("/", "-")
    sello_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta       = os.path.join(config.CARPETA_REPORTES, f"{sello_hora}_{nombre_ot}.json")
    reporte = {
        "fecha_auditoria":     datetime.now().isoformat(),
        "ot":                  acta.get("title"),
        "tipo_servicio":       acta.get("Tipo de servicio"),
        "fecha_ejecucion":     acta.get("start"),
        "direccion":           acta.get("address"),
        "empresa":             acta.get("company_name"),
        "or_norm":             acta.get("OR_NORM", ""),
        "planner":             resultado_qa.get("planner", ""),
        "internal_bia_code":   acta.get("internal_bia_code", ""),
        "estado_app":          acta.get("status_app"),
        "estado_electricista": acta.get("electrician_status_id"),
        "pdf_url":             acta.get("act_pdf_url"),
        "resultado_qa":        resultado_qa,
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(reporte, f, ensure_ascii=False, indent=2)
    print(f"  Reporte: {os.path.abspath(ruta)}")
    return ruta

def _v(x, na="N/A"):
    if x is None:
        return na
    s = str(x).strip()
    return s if s and s not in ("-", "null", "None") else na

def _check(ok):
    if ok is True:
        return ":white_check_mark:"
    if ok is False:
        return ":x:"
    return ""

def _seccion_transformador(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Transformador:* No reporta\n"
    return (
        "*Transformador*\n"
        f"  Numero: {_v(t.get('numero'))}  |  Capacidad: {_v(t.get('capacidad_kva'))} kVA\n"
        f"  Ubicacion: {_v(t.get('ubicacion'))}  |  Uso: {_v(t.get('tipo_uso'))}\n"
    )

def _seccion_medidor_encontrado(m):
    if not m:
        return ""
    chk = _check(m.get("serie_coincide_foto"))
    obs = m.get("observacion_serie_foto")
    linea_foto = f"  Verificacion serie vs foto: {chk} {_v(obs, '')}".rstrip()
    return (
        "*Medidor encontrado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh  |  Reactiva: {_v(m.get('lectura_reactiva_kvarh'))} kVArh\n"
        f"{linea_foto}\n"
    )

def _seccion_medidor_instalado(m):
    if not m or not m.get("aplica"):
        return ""
    if not m.get("se_instalo"):
        return "*Medidor instalado:* No se instalo\n"
    chk = _check(m.get("serie_coincide_foto"))
    obs = m.get("observacion_serie_foto")
    linea_foto = f"  Verificacion serie vs foto: {chk} {_v(obs, '')}".rstrip()
    return (
        "*Medidor instalado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh\n"
        f"{linea_foto}\n"
    )

def _seccion_sellos(s):
    if not s or not s.get("aplica"):
        return ""
    chk = _check(s.get("todos_completos"))
    falt = s.get("campos_faltantes") or []
    base = f"*Sellos instalados:* {_v(s.get('total'))} sellos {chk}\n"
    if falt:
        base += "  Campos incompletos:\n" + "\n".join(f"   - {f}" for f in falt) + "\n"
    return base

def _seccion_medidor_respaldo(m):
    if not m or not m.get("aplica"):
        return ""
    if not m.get("se_instalo"):
        return "*Medidor de respaldo:* No se instalo\n"
    return (
        "*Medidor de respaldo instalado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}\n"
    )

def _seccion_telemedida_encontrada(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Telemedida encontrada:* No\n"
    return (
        "*Telemedida encontrada*\n"
        f"  IP: {_v(t.get('ip'))}  |  Puerto: {_v(t.get('puerto'))}\n"
        f"  Serie: {_v(t.get('serie'))}  |  Marca: {_v(t.get('marca'))}  |  IMEI: {_v(t.get('imei'))}\n"
    )

def _seccion_telemedida_instalada(t):
    if not t or not t.get("aplica"):
        return ""
    if not t.get("se_instalo"):
        return "*Telemedida instalada:* No se realizaron cambios en el modem\n"
    return (
        "*Telemedida instalada*\n"
        f"  IP: {_v(t.get('ip'))}  |  Puerto: {_v(t.get('puerto'))}\n"
        f"  Serie: {_v(t.get('serie'))}  |  Marca: {_v(t.get('marca'))}  |  IMEI: {_v(t.get('imei'))}\n"
        f"  Operador SIM: {_v(t.get('operador_sim'))}  |  Serie SIM: {_v(t.get('serie_sim'))}\n"
    )

def _seccion_totalizador_encontrado(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Totalizador encontrado:* No\n"
    return (
        "*Totalizador encontrado*\n"
        f"  Marca: {_v(t.get('marca'))}  |  Capacidad: {_v(t.get('capacidad_a'))} A  |  Fases: {_v(t.get('fases'))}\n"
    )

def _seccion_totalizador_instalado(t):
    if not t or not t.get("aplica"):
        return ""
    if not t.get("se_instalo"):
        return "*Totalizador instalado:* No se instalo\n"
    return (
        "*Totalizador instalado*\n"
        f"  Marca: {_v(t.get('marca'))}  |  Capacidad: {_v(t.get('capacidad_a'))} A  |  Fases: {_v(t.get('fases'))}\n"
    )

def _seccion_cables_enc(c):
    if not c:
        return ""
    if not c.get("tiene"):
        return "*Cables de potencia encontrados:* No\n"
    return (
        "*Cables de potencia encontrados*\n"
        f"  Parcial: calibre {_v(c.get('calibre_parcial'))}, {_v(c.get('cables_por_fase_parcial'))} cable(s) por fase\n"
        f"  Acometida: calibre {_v(c.get('calibre_acometida'))}, {_v(c.get('cables_por_fase_acometida'))} cable(s) por fase\n"
    )

def _seccion_cables_inst(c):
    if not c or not c.get("aplica"):
        return ""
    if not c.get("se_instalo"):
        return "*Cables de potencia instalados:* No se instalo cable de potencia\n"
    return (
        "*Cables de potencia instalados*\n"
        f"  Parcial: calibre {_v(c.get('calibre_parcial'))}, {_v(c.get('cables_por_fase_parcial'))} cable(s) por fase\n"
        f"  Acometida: calibre {_v(c.get('calibre_acometida'))}, {_v(c.get('cables_por_fase_acometida'))} cable(s) por fase\n"
    )

def _seccion_aplica_simple(label, d, key_estado="tiene", txt_no="No", extras=None):
    if not d:
        return ""
    if not d.get("aplica"):
        return f"*{label}:* No aplica para esta medida\n"
    if not d.get(key_estado):
        return f"*{label}:* {txt_no}\n"
    if extras:
        return f"*{label}*\n" + extras
    return f"*{label}:* {_v(d.get('detalles'))}\n"

def _seccion_bloque_pruebas(b, instalado=False):
    label = "Bloque de pruebas instalado" if instalado else "Bloque de pruebas encontrado"
    if not b:
        return ""
    if not b.get("aplica"):
        return f"*{label}:* No aplica para esta medida\n"
    estado_key = "se_instalo" if instalado else "tiene"
    if not b.get(estado_key):
        return f"*{label}:* {'No se instalo' if instalado else 'No'}\n"
    return f"*{label}*\n  Marca: {_v(b.get('marca'))}  |  Tipo: {_v(b.get('tipo'))}\n"

def _seccion_cable_control(c, instalado=False):
    label = "Cable de control instalado" if instalado else "Cable de control encontrado"
    if not c:
        return ""
    if not c.get("aplica"):
        return f"*{label}:* No aplica para esta medida\n"
    estado_key = "se_instalo" if instalado else "tiene"
    if not c.get(estado_key):
        return f"*{label}:* {'No se instalo' if instalado else 'No'}\n"
    return (
        f"*{label}*\n"
        f"  Marca: {_v(c.get('marca'))}\n"
        f"  Calibre corriente: {_v(c.get('calibre_corriente'))}  |  Tension: {_v(c.get('calibre_tension'))}  |  Metros: {_v(c.get('metros'))}\n"
    )

def _seccion_pruebas(p):
    if not p:
        return ""
    if not p.get("se_realizaron"):
        return "*Pruebas de funcionamiento:* No\n"
    return f"*Pruebas de funcionamiento*\n  {_v(p.get('resumen'))}\n"

def _seccion_equipo_patron(e):
    if not e:
        return ""
    if not e.get("se_uso"):
        return "*Equipo patron:* No\n"
    return f"*Equipo patron*\n  {_v(e.get('resumen'))}\n"

def _construir_cuerpo_exitosa(acta, qa, encabezado):
    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n",
        f"*Medidor WMS asignado:* Pendiente\n\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado")),
        _seccion_medidor_instalado(qa.get("medidor_instalado")),
        _seccion_sellos(qa.get("sellos_instalados")),
        _seccion_medidor_respaldo(qa.get("medidor_respaldo_instalado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_telemedida_instalada(qa.get("telemedida_instalada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_totalizador_instalado(qa.get("totalizador_instalado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_cables_inst(qa.get("cables_potencia_instalados")),
        _seccion_aplica_simple("TCs encontrados", qa.get("tcs_encontrados")),
        _seccion_aplica_simple("TCs instalados", qa.get("tcs_instalados"), key_estado="se_instalo", txt_no="No se instalo"),
        _seccion_aplica_simple("TPs encontrados", qa.get("tps_encontrados")),
        _seccion_aplica_simple("TPs instalados", qa.get("tps_instalados"), key_estado="se_instalo", txt_no="No se instalo"),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_encontrado")),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_instalado"), instalado=True),
        _seccion_cable_control(qa.get("cable_control_encontrado")),
        _seccion_cable_control(qa.get("cable_control_instalado"), instalado=True),
        _seccion_pruebas(qa.get("pruebas_funcionamiento")),
        _seccion_equipo_patron(qa.get("equipo_patron")),
        f"*Diagrama unifilar:* {'Foto presente' if (qa.get('diagrama_unifilar') or {}).get('tiene_foto') else 'Sin foto'}\n",
        f"*Con OR:* {_v(qa.get('or_firma'))}\n\n",
        f"*Observaciones tecnicas:*\n{_v(qa.get('observaciones_tecnicas'))}\n",
    ]
    alertas = qa.get("alertas_qa") or []
    if alertas:
        secciones.append("\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas) + "\n")
    return "".join(s for s in secciones if s)

def _construir_cuerpo_fallida(acta, qa, encabezado):
    falla   = qa.get("tipificacion_falla") or {}
    prereqs = falla.get("prerequisitos_reprogramacion") or []
    bloque_prereqs = ""
    if prereqs:
        bloque_prereqs = "*Prerequisitos para reprogramar:*\n" + "\n".join(f"- {p}" for p in prereqs) + "\n"

    cuerpo = (
        encabezado
        + f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n"
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n"
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n"
        f"*Tipificacion de la OT fallida*\n"
        f"*Responsable:* {_v(falla.get('responsable'))}\n"
        f"*Categoria:* {_v(falla.get('categoria_falla'))}  |  *Criticidad:* {_v(falla.get('criticidad'))}\n"
        f"*Actor a contactar:* {_v(falla.get('actor_a_contactar'))}\n"
        f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n"
        f"*Detalle:* {_v(falla.get('detalle'))}\n"
        f"*Accion inmediata:* {_v(falla.get('accion_inmediata'))}\n"
        f"*Reprogramar:* {'Si' if falla.get('requiere_reprogramacion') else 'No'}\n"
        f"{bloque_prereqs}"
        f"*Mejora:* {_v(falla.get('mejora'))}\n\n"
        f"*Observaciones tecnicas:*\n{_v(qa.get('observaciones_tecnicas'))}\n"
    )
    alertas = qa.get("alertas_qa") or []
    if alertas:
        cuerpo += "\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas) + "\n"
    return cuerpo

def enviar_slack(acta, resultado_qa):
    url = (config.SLACK_WEBHOOK_URL or "").strip().strip('"').strip("'")
    if not url or "REEMPLAZA" in url:
        print("  Slack: SLACK_WEBHOOK_URL vacio. Se omite envio.")
        return
    if not url.startswith("https://"):
        print(f"  Slack: URL invalida (debe empezar con https://). Se omite envio.")
        return

    es_exitosa = resultado_qa.get("estado_ot") == "EXITOSA"
    color      = "#2eb886" if es_exitosa else "#e01e5a"
    estado_txt = "EXITOSA" if es_exitosa else "FALLIDA"
    planner    = resultado_qa.get("planner", "N/A")
    or_norm    = resultado_qa.get("or_norm", acta.get("OR_NORM", "N/A"))

    user_ids   = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id   = user_ids.get(planner)
    mention    = f"<@{slack_id}>" if slack_id else f"*{planner}*"
    encabezado = f"{mention} {planner}\n\n"

    if es_exitosa:
        cuerpo = _construir_cuerpo_exitosa(acta, resultado_qa, encabezado)
    else:
        cuerpo = _construir_cuerpo_fallida(acta, resultado_qa, encabezado)

    if len(cuerpo) > 7800:
        cuerpo = cuerpo[:7800] + "\n... (truncado)"

    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{estado_txt}] {acta.get('title', 'Sin titulo')}",
            "fields": [
                {"title": "Tipo",    "value": _v(acta.get("Tipo de servicio")), "short": True},
                {"title": "Medida",  "value": _v(resultado_qa.get("tipo_medida")), "short": True},
                {"title": "OR",      "value": _v(or_norm),  "short": True},
                {"title": "Planner", "value": _v(planner),  "short": True},
                {"title": "Fecha",   "value": _v(acta.get("start")), "short": True},
                {"title": "Empresa", "value": _v(acta.get("company_name")), "short": True},
            ],
            "text":   cuerpo,
            "footer": _v(acta.get("address"), ""),
            "mrkdwn_in": ["text"],
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if 200 <= r.status_code < 300:
            print("  Slack enviado.")
        else:
            print(f"  ERROR Slack: HTTP {r.status_code} -> {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Slack: {e}")

def enviar_whatsapp(acta, resultado_qa):
    if not config.TWILIO_ACCOUNT_SID or "xxxxx" in config.TWILIO_ACCOUNT_SID:
        return

    es_exitosa = resultado_qa.get("estado_ot") == "EXITOSA"
    estado_txt = "EXITOSA" if es_exitosa else "FALLIDA"
    planner    = resultado_qa.get("planner", "N/A")
    med_acta   = resultado_qa.get("medidor_instalado_acta", "N/A")
    errores    = resultado_qa.get("validaciones", {}).get("errores_encontrados", [])
    txt_err    = (" | " + " | ".join(errores[:2])) if errores else ""

    mensaje = (
        f"{estado_txt} - {acta.get('title', 'N/A')}\n"
        f"Planner: {planner}\n"
        f"{acta.get('Tipo de servicio', '')} | {resultado_qa.get('tipo_medida', '')}\n"
        f"Medidor: {med_acta}\n"
        f"{acta.get('address', 'N/A')}"
        f"{txt_err}"
    )

    try:
        cliente = TwilioClient(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        cliente.messages.create(
            from_=config.TWILIO_FROM_WHATSAPP,
            to=config.TWILIO_TO_WHATSAPP,
            body=mensaje
        )
        print("  WhatsApp enviado.")
    except Exception as e:
        print(f"  ERROR WhatsApp: {e}")

def procesar_acta(acta, wms):
    ot_nombre         = acta.get("title", acta.get("id"))
    pdf_url           = acta.get("act_pdf_url", "")
    tipo              = acta.get("Tipo de servicio", "")
    estado            = acta.get("electrician_status_id", "")
    or_norm           = acta.get("OR_NORM", "")
    internal_bia_code = acta.get("internal_bia_code", "")
    planner           = identificar_planner(or_norm)

    print(f"\n  -> Procesando: {ot_nombre}")
    print(f"     Tipo: {tipo} | Estado: {estado}")
    print(f"     OR: {or_norm} | Planner: {planner}")

    texto_pdf = descargar_y_leer_pdf(pdf_url)
    if not texto_pdf:
        print("     No se pudo leer el PDF. Se omite.")
        return False

    print(f"     Analizando con Groq ({config.GROQ_MODEL})...")
    resultado_qa = analizar_acta(texto_pdf, tipo, estado, internal_bia_code)
    if not resultado_qa:
        return False

    resultado_qa["planner"]           = planner
    resultado_qa["or_norm"]           = or_norm
    resultado_qa["internal_bia_code"] = internal_bia_code

    print(f"     Resultado: {resultado_qa.get('estado_ot')} | Medida: {resultado_qa.get('tipo_medida')}")
    errores = resultado_qa.get("validaciones", {}).get("errores_encontrados", [])
    if errores:
        print(f"     Errores QA: {', '.join(errores)}")

    guardar_reporte(acta, resultado_qa)
    enviar_slack(acta, resultado_qa)
    enviar_whatsapp(acta, resultado_qa)
    guardar_procesado(acta.get("id"))
    print(f"     OK: {ot_nombre} auditada.")
    return True

def main():
    modo = "PRUEBA" if config.MODO_PRUEBA else "AUTOMATICO"
    print("=" * 58)
    print("   SISTEMA QA BIA ENERGY  -  Motor: Groq / Llama")
    print("   Modo: " + modo)
    print("=" * 58)
    print("   Fecha inicio : " + config.FECHA_INICIO)
    print("   Pausa        : " + str(config.PAUSA_GROQ_SEGUNDOS) + "s entre actas")
    if config.MODO_PRUEBA:
        print("   Actas prueba : " + str(config.ACTAS_PRUEBA))
    print("=" * 58)

    print("\n  Cargando inventario WMS...")
    wms = cargar_inventario_wms()

    if config.MODO_PRUEBA:
        print("")
        actas = obtener_actas_nuevas()
        procesadas = 0
        for i, acta in enumerate(actas):
            if procesar_acta(acta, wms):
                procesadas += 1
            if i < len(actas) - 1:
                print("     Pausa " + str(config.PAUSA_GROQ_SEGUNDOS) + "s...")
                time.sleep(config.PAUSA_GROQ_SEGUNDOS)

        print("")
        print("=" * 58)
        print("   PRUEBA TERMINADA - " + str(procesadas) + " acta(s) auditada(s)")
        print("   Reportes en: " + os.path.abspath(config.CARPETA_REPORTES))
        print("=" * 58)

    else:
        actas = obtener_actas_nuevas()
        if actas:
            for i, acta in enumerate(actas):
                procesar_acta(acta, wms)
                if i < len(actas) - 1:
                    time.sleep(config.PAUSA_GROQ_SEGUNDOS)
        else:
            print("[" + ahora() + "] Sin actas nuevas.")

        if not getattr(config, 'MODO_UNICO', False):
            while True:
                time.sleep(config.INTERVALO_SEGUNDOS)
                actas = obtener_actas_nuevas()
                if actas:
                    for i, acta in enumerate(actas):
                        procesar_acta(acta, wms)
                        if i < len(actas) - 1:
                            time.sleep(config.PAUSA_GROQ_SEGUNDOS)
                else:
                    print("[" + ahora() + "] Sin actas nuevas. Revisando en " + str(config.INTERVALO_SEGUNDOS) + "s...")

if __name__ == "__main__":
    main()