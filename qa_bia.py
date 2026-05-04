# =============================================================
#  qa_bia.py  —  SISTEMA QA AUTOMATIZADO DE ACTAS BIA ENERGY
#  Motor de IA: Groq (Llama)
#  Version: 3.0 — WMS coherente + tipificacion profesional + render por seccion
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
        WMS_CSV_URL          = "https://bia.metabaseapp.com/public/question/67f6d437-6326-415a-a799-1ee34b9648b0.csv"
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
        FECHA_INICIO         = "2026-05-04"
        PAUSA_GROQ_SEGUNDOS  = 5
        INTERVALO_SEGUNDOS   = 300
        MAX_ACTAS_POR_RUN    = 10
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
            "Ervison Plata":  "U090B8YQMAM",
            "Dinovi Sanchez": "U06NVHEE9GD",
        }
else:
    import config

cliente_groq = Groq(api_key=config.GROQ_API_KEY)

# =============================================================
#  UTILIDADES
# =============================================================

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

def _normalizar_serial(s):
    if not s:
        return ""
    return re.sub(r"[\s\-_/]", "", str(s)).lstrip("0").upper()

# =============================================================
#  INVENTARIO WMS
# =============================================================

def cargar_inventario_wms():
    try:
        url = getattr(config, "WMS_CSV_URL", "https://bia.metabaseapp.com/public/question/67f6d437-6326-415a-a799-1ee34b9648b0.csv")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        lector = csv.DictReader(io.StringIO(r.content.decode('utf-8')))
        wms = {}
        for fila in lector:
            bia_code = fila.get("Bia Code", "").strip()
            tipo     = fila.get("Tipo Sku", "").strip().lower()
            estado   = fila.get("Estado", "").strip().upper()
            serial   = fila.get("Serial", "").strip()
            marca    = fila.get("Marca", "").strip()
            if not bia_code or not serial or estado not in ("ASIGNADO", "INSTALADO"):
                continue
            entry = wms.setdefault(bia_code, {"medidor": None, "tcs": [], "tps": []})
            item = {"serial": serial, "marca": marca, "estado": estado}
            if tipo == "medidor":
                entry["medidor"] = item
            elif "transformador de corriente" in tipo:
                entry["tcs"].append(item)
            elif "transformador de potencial" in tipo or "transformador de potencia" in tipo:
                entry["tps"].append(item)
        meds = sum(1 for v in wms.values() if v.get("medidor"))
        tcs  = sum(len(v.get("tcs", []))  for v in wms.values())
        tps  = sum(len(v.get("tps", []))  for v in wms.values())
        print(f"  WMS cargado: {meds} medidores, {tcs} TCs, {tps} TPs.")
        return wms
    except Exception as e:
        print(f"  ERROR WMS: {e}")
        print("  Continuando sin validacion de medidor.")
        return {}

# =============================================================
#  OBTENER ACTAS
# =============================================================

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

    cap = getattr(config, "MAX_ACTAS_POR_RUN", 0)
    if cap and len(pendientes) > cap:
        print(f"  Cap por run: tomando {cap} mas antiguas, {len(pendientes) - cap} quedan para proximos runs.")
        pendientes = pendientes[:cap]

    if config.MODO_PRUEBA and len(pendientes) > config.ACTAS_PRUEBA:
        print(f"  [MODO PRUEBA] Solo {config.ACTAS_PRUEBA} de {len(pendientes)}.")
        pendientes = pendientes[:config.ACTAS_PRUEBA]

    return pendientes

# =============================================================
#  LEER PDF
# =============================================================

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

# =============================================================
#  ANALISIS CON GROQ
# =============================================================

def analizar_acta(texto_pdf, tipo_servicio, estado_electricista,
                  internal_bia_code="", serial_asignado_wms="", marca_asignada_wms="",
                  tcs_asignados_wms=None, tps_asignados_wms=None):
    tipo_label = "INSTALACION" if "nstala" in tipo_servicio else "VISITA PREVIA"
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    es_visita  = "previa" in tipo_servicio.lower()
    debe_comparar_wms = es_exitosa and not es_visita and bool(serial_asignado_wms)
    wms_info = serial_asignado_wms if debe_comparar_wms else "No aplica"
    marca_wms = marca_asignada_wms if debe_comparar_wms else ""
    tcs_asignados_wms = tcs_asignados_wms or []
    tps_asignados_wms = tps_asignados_wms or []
    tcs_wms_info = ", ".join(tcs_asignados_wms) if (debe_comparar_wms and tcs_asignados_wms) else "No aplica"
    tps_wms_info = ", ".join(tps_asignados_wms) if (debe_comparar_wms and tps_asignados_wms) else "No aplica"

    prompt = f"""
Eres un auditor QA SENIOR de ordenes de trabajo de medicion electrica en Colombia para BIA Energy.
Tu redaccion debe ser tecnica, profesional y estructural, NO descriptiva basica.

TIPO DE SERVICIO: {tipo_label}
RESULTADO EN APP: {"EXITOSA" if es_exitosa else "FALLIDA"}
CODIGO INTERNO BIA: {internal_bia_code}
MEDIDOR ASIGNADO EN SISTEMA WMS: {wms_info} {("(" + marca_wms + ")") if marca_wms else ""}
TCs ASIGNADOS EN WMS (semidirecta/indirecta): {tcs_wms_info}
TPs ASIGNADOS EN WMS (solo indirecta): {tps_wms_info}

INSTRUCCIONES CRITICAS:
- Devuelve UNICAMENTE un JSON valido sin texto adicional ni bloques de codigo.
- NO inventes datos. Si un campo no esta en el acta usa null.
- MARCAS: si "Marca del medidor", "Marca del modem", "Marca del totalizador" dice "Otra"/"Otro", usa el valor del siguiente campo "Ingresar marca..." como marca real. NUNCA concatenes.
- "serie_coincide_foto" SIEMPRE true o false (nunca null si hay seccion Registro fotografico):
    1. Toma la serie EXACTA del campo "Serie del medidor".
    2. En el bloque "Registro fotografico medidor, sellos y celdas" siguiente busca esa misma cadena.
    3. Si aparece -> true. Si no aparece o aparece distinta -> false.
    4. Si true: "observacion_serie_foto" = null. Si false: explica brevemente con la serie real vista.
- WMS comparacion (ignorando ceros a la izquierda y espacios):
  * "medidor_coincide_wms": Si MEDIDOR ASIGNADO arriba dice "No aplica" -> null. Si no, true/false comparando serie_instalada vs WMS.
  * "tcs_coinciden_wms": null si DIRECTA o si TCs ASIGNADOS dice "No aplica". Si no, true solo si CADA serial asignado en WMS aparece tambien en tcs_instalados.seriales (orden libre, comparacion por conjunto).
  * "tps_coinciden_wms": null si DIRECTA o SEMIDIRECTA o si TPs ASIGNADOS dice "No aplica". Si no, true solo si CADA serial asignado en WMS aparece tambien en tps_instalados.seriales.

REGLAS POR TIPO DE MEDIDA:
- DIRECTA: tcs_*, tps_*, bloque_pruebas_*, cable_control_* TODOS aplica=false.
- SEMIDIRECTA: tps_* aplica=false. Resto aplica.
- INDIRECTA: TODOS aplican.

REGLAS POR TIPO DE SERVICIO:
- INSTALACION: campos *_instalado se llenan si se instalo el equipo (se_instalo true) o false.
- VISITA PREVIA: TODOS los *_instalado tienen aplica=false.

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
    "serie_coincide_foto": <bool>,
    "observacion_serie_foto": "<o null>"
  }},

  "medidor_instalado": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "serie": "<o null>",
    "marca": "<o null>",
    "referencia": "<o null>",
    "lectura_activa_kwh": "<o null>",
    "serie_coincide_foto": <bool>,
    "observacion_serie_foto": "<o null>"
  }},

  "medidor_coincide_wms": <true | false | null>,
  "medidor_instalado_acta": "<serie del medidor instalado, conveniencia>",
  "medidor_marca": "<marca del medidor instalado, conveniencia>",

  "sellos_instalados": {{
    "aplica": <bool>,
    "total": <int>,
    "todos_completos": <bool>,
    "campos_faltantes": ["<descripcion>"]
  }},

  "medidor_respaldo_instalado": {{
    "aplica": <bool>,
    "se_instalo": <bool>,
    "serie": "<o null>",
    "marca": "<o null>"
  }},

  "telemedida_encontrada": {{
    "tiene": <bool>,
    "ip": "<o null>", "puerto": "<o null>",
    "serie": "<o null>", "marca": "<o null>", "imei": "<o null>"
  }},

  "telemedida_instalada": {{
    "aplica": <bool>, "se_instalo": <bool>,
    "ip": "<o null>", "puerto": "<o null>",
    "serie": "<o null>", "marca": "<o null>", "imei": "<o null>",
    "operador_sim": "<o null>", "serie_sim": "<o null>"
  }},

  "totalizador_encontrado": {{ "tiene": <bool>, "marca": "<o null>", "capacidad_a": "<o null>", "fases": "<o null>" }},
  "totalizador_instalado":  {{ "aplica": <bool>, "se_instalo": <bool>, "marca": "<o null>", "capacidad_a": "<o null>", "fases": "<o null>" }},

  "cables_potencia_encontrados": {{
    "tiene": <bool>,
    "calibre_parcial": "<o null>", "cables_por_fase_parcial": "<o null>",
    "calibre_acometida": "<o null>", "cables_por_fase_acometida": "<o null>"
  }},
  "cables_potencia_instalados": {{
    "aplica": <bool>, "se_instalo": <bool>,
    "calibre_parcial": "<o null>", "cables_por_fase_parcial": "<o null>",
    "calibre_acometida": "<o null>", "cables_por_fase_acometida": "<o null>"
  }},

  "tcs_encontrados":      {{ "aplica": <bool>, "tiene": <bool>, "seriales": ["<serial>"], "detalles": "<o null>" }},
  "tcs_instalados":       {{ "aplica": <bool>, "se_instalo": <bool>, "seriales": ["<serial de cada TC instalado>"], "marca": "<o null>", "detalles": "<o null>" }},
  "tps_encontrados":      {{ "aplica": <bool>, "tiene": <bool>, "seriales": ["<serial>"], "detalles": "<o null>" }},
  "tps_instalados":       {{ "aplica": <bool>, "se_instalo": <bool>, "seriales": ["<serial de cada TP instalado>"], "marca": "<o null>", "detalles": "<o null>" }},

  "tcs_coinciden_wms": <true | false | null>,
  "tps_coinciden_wms": <true | false | null>,

  "bloque_pruebas_encontrado": {{ "aplica": <bool>, "tiene": <bool>, "marca": "<o null>", "tipo": "<o null>" }},
  "bloque_pruebas_instalado":  {{ "aplica": <bool>, "se_instalo": <bool>, "marca": "<o null>", "tipo": "<o null>" }},

  "cable_control_encontrado": {{ "aplica": <bool>, "tiene": <bool>, "marca": "<o null>", "calibre_corriente": "<o null>", "calibre_tension": "<o null>", "metros": "<o null>" }},
  "cable_control_instalado":  {{ "aplica": <bool>, "se_instalo": <bool>, "marca": "<o null>", "calibre_corriente": "<o null>", "calibre_tension": "<o null>", "metros": "<o null>" }},

  "pruebas_funcionamiento": {{ "se_realizaron": <bool>, "resumen": "<o null>" }},
  "equipo_patron":          {{ "se_uso": <bool>, "resumen": "<o null>" }},
  "diagrama_unifilar":      {{ "tiene_foto": <bool> }},

  "observaciones_tecnicas": "<parrafo tecnico denso de 3-5 lineas: hora llegada, encontrado, instalado con seriales, pruebas, resultado>",
  "or_firma": "SI | NO",

  "validaciones": {{
    "campos_completos": <bool>,
    "coherencia": "COHERENTE | INCOHERENTE | INCOMPLETO",
    "errores_encontrados": ["lista de errores reales"]
  }},

  "tipificacion_falla": {{
    "causa_raiz": "<TITULO ANALITICO de 3-7 palabras. NO descriptivo. Ejemplos validos: 'Condiciones tecnicas no viables', 'Falta de viabilidad operativa en visita previa', 'Inconsistencia con Operador de Red', 'Desconocimiento del alcance por el cliente'. EJEMPLOS MALOS (no usar): 'No se pudo instalar', 'Problema con cliente'>",
    "responsable": "<rol especifico del area que debe gestionar. Puede ser combinado con / si dos areas son responsables. Opciones recomendadas: Technical Expert | Coordinador Operativo | Planeacion | Comercial | Operador de Red | Cliente | Contratista | BIA Operaciones | Externo>",
    "detalle": "<2-4 lineas. INCLUYE: cifras concretas (medidas en cm, calibres, capacidades), referencia explicita al codigo BIA ({internal_bia_code}), si la condicion estaba detectada en visita previa menciona 'aunque esta condicion ya estaba identificada en la visita previa', cita literal del acta cuando ayude>",
    "mejora": "<accion ESTRUCTURAL de proceso, no operativa. NO escribas 'reprogramar la visita'. SI escribe cambios sistemicos. Ejemplo gold: 'Implementar un control de cierre de viabilidad tecnica previo a la programacion de instalaciones, asegurando que todas las restricciones detectadas en visitas previas cuenten con solucion aprobada (diseño, materiales y permisos) antes de agendar la OT.'>",
    "cinco_por_que": [
      "1. Por que la OT fue fallida? Porque [razon concreta]",
      "2. Por que [problema]? Porque [causa tecnica]",
      "3. Por que [causa]? Porque [razon de fondo]",
      "4. Por que esto afecta? Porque [impacto]",
      "5. Por que no se corrigio? Porque [limitacion]"
    ]
  }},

  "observacion_automatica": "<texto listo para copiar en la app>",
  "alertas_qa": ["alertas menores"]
}}

EJEMPLO GOLD DE TIPIFICACION (replica este nivel):
{{
  "causa_raiz": "Condiciones tecnicas no viables",
  "responsable": "Technical Expert / Coordinador Operativo",
  "detalle": "En la OT CO0400006548, no fue posible realizar la instalacion del medidor debido a que el espacio disponible en el gabinete (25 cm x 20 cm) no permite la instalacion ni el radio de curvatura del cable 1/0. Aunque esta condicion ya estaba identificada en la visita previa, no se gestionaron soluciones tecnicas ni aprobaciones necesarias antes de la ejecucion.",
  "mejora": "Implementar un control de cierre de viabilidad tecnica previo a la programacion de instalaciones, asegurando que todas las restricciones detectadas en visitas previas cuenten con solucion aprobada (diseño, materiales y permisos) antes de agendar la OT."
}}

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

# =============================================================
#  POST-VALIDACIONES (defensivas)
# =============================================================

def _post_corregir_serie_foto(item):
    """Si modelo dice false pero la observacion contiene la misma serie, corregir."""
    if not isinstance(item, dict):
        return
    serie = (item.get("serie") or "").strip()
    obs   = (item.get("observacion_serie_foto") or "")
    if item.get("serie_coincide_foto") is False and serie:
        norm_serie = _normalizar_serial(serie)
        norm_obs   = _normalizar_serial(obs)
        if norm_serie and norm_serie in norm_obs:
            item["serie_coincide_foto"] = True
            item["observacion_serie_foto"] = None

def _enforce_reglas_medida_servicio(qa, tipo_servicio):
    """Fuerza aplica=false en secciones que no aplican segun tipo_medida y tipo_servicio.
    Defensivo contra errores del modelo."""
    tipo_medida = (qa.get("tipo_medida") or "").upper()
    es_visita   = "previa" in (tipo_servicio or "").lower()

    def _force_false(key):
        if isinstance(qa.get(key), dict):
            qa[key]["aplica"] = False

    if tipo_medida == "DIRECTA":
        for k in ("tcs_encontrados", "tcs_instalados",
                  "tps_encontrados", "tps_instalados",
                  "bloque_pruebas_encontrado", "bloque_pruebas_instalado",
                  "cable_control_encontrado", "cable_control_instalado"):
            _force_false(k)
    elif tipo_medida == "SEMIDIRECTA":
        for k in ("tps_encontrados", "tps_instalados"):
            _force_false(k)

    if es_visita:
        for k in ("medidor_instalado", "tcs_instalados", "tps_instalados",
                  "bloque_pruebas_instalado", "cable_control_instalado",
                  "telemedida_instalada", "totalizador_instalado",
                  "cables_potencia_instalados", "medidor_respaldo_instalado",
                  "sellos_instalados"):
            _force_false(k)

def _validar_coincidencia_wms(qa, serial_wms, tcs_wms, tps_wms, debe_comparar):
    # Medidor
    if debe_comparar and serial_wms:
        inst = qa.get("medidor_instalado") or {}
        serie_inst = (inst.get("serie") or "").strip() or (qa.get("medidor_instalado_acta") or "").strip()
        if serie_inst:
            qa["medidor_coincide_wms"] = _normalizar_serial(serie_inst) == _normalizar_serial(serial_wms)
        else:
            qa["medidor_coincide_wms"] = None
    else:
        qa["medidor_coincide_wms"] = None

    tipo_medida = (qa.get("tipo_medida") or "").upper()

    # TCs (aplica para SEMIDIRECTA e INDIRECTA)
    if debe_comparar and tcs_wms and tipo_medida in ("SEMIDIRECTA", "INDIRECTA"):
        tcs_inst = (qa.get("tcs_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tcs_wms if s}
        acta_set = {_normalizar_serial(s) for s in tcs_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tcs_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tcs_coinciden_wms"] = None

    # TPs (aplica solo para INDIRECTA)
    if debe_comparar and tps_wms and tipo_medida == "INDIRECTA":
        tps_inst = (qa.get("tps_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tps_wms if s}
        acta_set = {_normalizar_serial(s) for s in tps_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tps_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tps_coinciden_wms"] = None

# =============================================================
#  GUARDAR REPORTE
# =============================================================

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

# =============================================================
#  SLACK HELPERS
# =============================================================

def _v(x, na="N/A"):
    if x is None:
        return na
    s = str(x).strip()
    return s if s and s not in ("-", "null", "None") else na

def _check(ok):
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
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
    base = (
        "*Medidor encontrado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh  |  Reactiva: {_v(m.get('lectura_reactiva_kvarh'))} kVArh\n"
    )
    chk = _check(m.get("serie_coincide_foto"))
    if chk:
        obs = _v(m.get("observacion_serie_foto"), "")
        base += f"  Verificacion serie vs foto: {chk} {obs}".rstrip() + "\n"
    return base

def _seccion_medidor_instalado(m, coincide_wms=None, serial_wms=""):
    if not m or not m.get("aplica"):
        return ""
    if not m.get("se_instalo"):
        return "*Medidor instalado:* No se instalo\n"
    foto_ok = m.get("serie_coincide_foto")
    overall = True
    if foto_ok is False or coincide_wms is False:
        overall = False
    titulo_chk = _check(overall)
    base = (
        f"*Medidor instalado* {titulo_chk}".rstrip() + "\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh\n"
    )
    chk = _check(foto_ok)
    if chk:
        obs = _v(m.get("observacion_serie_foto"), "")
        base += f"  Verificacion serie vs foto: {chk} {obs}".rstrip() + "\n"
    if coincide_wms is True:
        base += f"  WMS asignado: {serial_wms} ✅ Coincide\n"
    elif coincide_wms is False:
        base += f"  WMS asignado: {serial_wms} ❌ NO coincide\n"
    return base

def _seccion_sellos(s):
    if not s or not s.get("aplica"):
        return ""
    total = s.get("total")
    chk   = _check(s.get("todos_completos"))
    falt  = s.get("campos_faltantes") or []
    if total is None or (isinstance(total, str) and not total.strip()):
        if not falt and chk == "":
            return ""
        cant = "N/A"
    else:
        cant = str(total)
    base = f"*Sellos instalados:* {cant} sello(s) {chk}".rstrip() + "\n"
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

def _seccion_aplica_simple(label, d, key_estado="tiene", txt_no="No"):
    if not d or not d.get("aplica"):
        return ""
    if not d.get(key_estado):
        return f"*{label}:* {txt_no}\n"
    return f"*{label}:* {_v(d.get('detalles'))}\n"

def _seccion_tc_tp_instalados(label, d, wms_asignados, coincide):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("se_instalo"):
        return f"*{label}:* No se instalo\n"
    seriales = d.get("seriales") or []
    titulo_chk = _check(coincide) if coincide is not None else _check(bool(seriales))
    base = f"*{label}* {titulo_chk}".rstrip() + "\n"
    if seriales:
        base += f"  Seriales acta: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if d.get("marca"):
        base += f"  Marca: {_v(d.get('marca'))}\n"
    if wms_asignados:
        base += f"  WMS asignado: {', '.join(wms_asignados)}\n"
        chk = _check(coincide)
        if chk:
            base += f"  Coincidencia WMS: {chk}\n"
    return base

def _seccion_bloque_pruebas(b, instalado=False):
    if not b or not b.get("aplica"):
        return ""
    label = "Bloque de pruebas instalado" if instalado else "Bloque de pruebas encontrado"
    estado_key = "se_instalo" if instalado else "tiene"
    if not b.get(estado_key):
        return f"*{label}:* {'No se instalo' if instalado else 'No'}\n"
    return f"*{label}*\n  Marca: {_v(b.get('marca'))}  |  Tipo: {_v(b.get('tipo'))}\n"

def _seccion_cable_control(c, instalado=False):
    if not c or not c.get("aplica"):
        return ""
    label = "Cable de control instalado" if instalado else "Cable de control encontrado"
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

def _construir_cuerpo_exitosa(acta, qa, encabezado, serial_wms_asignado=""):
    coincide_wms = qa.get("medidor_coincide_wms")
    tcs_wms = qa.get("tcs_wms_asignados") or []
    tps_wms = qa.get("tps_wms_asignados") or []
    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado")),
        _seccion_medidor_instalado(qa.get("medidor_instalado"), coincide_wms, serial_wms_asignado),
        _seccion_sellos(qa.get("sellos_instalados")),
        _seccion_medidor_respaldo(qa.get("medidor_respaldo_instalado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_telemedida_instalada(qa.get("telemedida_instalada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_totalizador_instalado(qa.get("totalizador_instalado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_cables_inst(qa.get("cables_potencia_instalados")),
        _seccion_aplica_simple("TCs encontrados", qa.get("tcs_encontrados")),
        _seccion_tc_tp_instalados("TCs instalados", qa.get("tcs_instalados"), tcs_wms, qa.get("tcs_coinciden_wms")),
        _seccion_aplica_simple("TPs encontrados", qa.get("tps_encontrados")),
        _seccion_tc_tp_instalados("TPs instalados", qa.get("tps_instalados"), tps_wms, qa.get("tps_coinciden_wms")),
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
    falla = qa.get("tipificacion_falla") or {}
    return (
        encabezado
        + f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n"
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n"
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n"
        f"*Tipificacion de la OT fallida*\n"
        f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n"
        f"*Responsable:* {_v(falla.get('responsable'))}\n"
        f"*Detalle:* {_v(falla.get('detalle'))}\n"
        f"*Mejora:* {_v(falla.get('mejora'))}\n\n"
        f"*Observaciones tecnicas:*\n{_v(qa.get('observaciones_tecnicas'))}\n"
    )

# =============================================================
#  ALERTAS
# =============================================================

def enviar_slack(acta, resultado_qa, serial_wms_asignado=""):
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

    user_ids = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id = user_ids.get(planner)
    if slack_id:
        encabezado = f"<@{slack_id}>\n\n"
    else:
        encabezado = f"*{planner}*\n\n"

    if es_exitosa:
        cuerpo = _construir_cuerpo_exitosa(acta, resultado_qa, encabezado, serial_wms_asignado)
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
    inst       = resultado_qa.get("medidor_instalado") or {}
    med_acta   = inst.get("serie") or resultado_qa.get("medidor_instalado_acta", "N/A")
    coincide   = resultado_qa.get("medidor_coincide_wms")
    alerta_wms = " | MEDIDOR NO COINCIDE WMS" if coincide is False else ""
    errores    = resultado_qa.get("validaciones", {}).get("errores_encontrados", [])
    txt_err    = (" | " + " | ".join(errores[:2])) if errores else ""
    mensaje = (
        f"{estado_txt} - {acta.get('title', 'N/A')}\n"
        f"Planner: {planner}\n"
        f"{acta.get('Tipo de servicio', '')} | {resultado_qa.get('tipo_medida', '')}\n"
        f"Medidor: {med_acta}\n"
        f"{acta.get('address', 'N/A')}"
        f"{txt_err}{alerta_wms}"
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

# =============================================================
#  PROCESAR UNA ACTA
# =============================================================

def procesar_acta(acta, wms):
    ot_nombre         = acta.get("title", acta.get("id"))
    pdf_url           = acta.get("act_pdf_url", "")
    tipo              = acta.get("Tipo de servicio", "")
    estado            = acta.get("electrician_status_id", "")
    or_norm           = acta.get("OR_NORM", "")
    internal_bia_code = acta.get("internal_bia_code", "")
    planner           = identificar_planner(or_norm)

    entry_wms       = wms.get(internal_bia_code, {})
    medidor_wms     = entry_wms.get("medidor") or {}
    serial_asignado = medidor_wms.get("serial", "")
    marca_asignada  = medidor_wms.get("marca", "")
    tcs_asignados   = [t.get("serial", "") for t in entry_wms.get("tcs", []) if t.get("serial")]
    tps_asignados   = [t.get("serial", "") for t in entry_wms.get("tps", []) if t.get("serial")]

    es_exitosa = estado in config.ESTADOS_EXITOSOS
    es_visita  = "previa" in tipo.lower()
    debe_comparar_wms = es_exitosa and not es_visita and bool(serial_asignado)

    print(f"\n  -> Procesando: {ot_nombre}")
    print(f"     Tipo: {tipo} | Estado: {estado}")
    print(f"     OR: {or_norm} | Planner: {planner}")
    if serial_asignado:
        print(f"     WMS: medidor={serial_asignado} | TCs={len(tcs_asignados)} | TPs={len(tps_asignados)} | Comparar={debe_comparar_wms}")
    else:
        print(f"     WMS: No encontrado para {internal_bia_code}")

    texto_pdf = descargar_y_leer_pdf(pdf_url)
    if not texto_pdf:
        print("     No se pudo leer el PDF. Se omite.")
        return False

    print(f"     Analizando con Groq ({config.GROQ_MODEL})...")
    resultado_qa = analizar_acta(
        texto_pdf, tipo, estado, internal_bia_code,
        serial_asignado if debe_comparar_wms else "",
        marca_asignada if debe_comparar_wms else "",
        tcs_asignados if debe_comparar_wms else [],
        tps_asignados if debe_comparar_wms else [],
    )
    if not resultado_qa:
        return False

    # Post-validaciones defensivas
    _enforce_reglas_medida_servicio(resultado_qa, tipo)
    _post_corregir_serie_foto(resultado_qa.get("medidor_encontrado"))
    _post_corregir_serie_foto(resultado_qa.get("medidor_instalado"))
    _validar_coincidencia_wms(
        resultado_qa,
        serial_asignado if debe_comparar_wms else "",
        tcs_asignados   if debe_comparar_wms else [],
        tps_asignados   if debe_comparar_wms else [],
        debe_comparar_wms,
    )

    resultado_qa["planner"]              = planner
    resultado_qa["or_norm"]              = or_norm
    resultado_qa["internal_bia_code"]    = internal_bia_code
    resultado_qa["medidor_wms_asignado"] = serial_asignado if debe_comparar_wms else "No aplica"
    resultado_qa["tcs_wms_asignados"]    = tcs_asignados if debe_comparar_wms else []
    resultado_qa["tps_wms_asignados"]    = tps_asignados if debe_comparar_wms else []

    print(f"     Resultado: {resultado_qa.get('estado_ot')} | Medida: {resultado_qa.get('tipo_medida')}")
    if resultado_qa.get("medidor_coincide_wms") is False:
        print(f"     ALERTA: Medidor instalado != WMS asignado {serial_asignado}")
    if resultado_qa.get("tcs_coinciden_wms") is False:
        print(f"     ALERTA: TCs instalados != WMS asignados")
    if resultado_qa.get("tps_coinciden_wms") is False:
        print(f"     ALERTA: TPs instalados != WMS asignados")
    errores = resultado_qa.get("validaciones", {}).get("errores_encontrados", [])
    if errores:
        print(f"     Errores QA: {', '.join(errores)}")

    guardar_reporte(acta, resultado_qa)
    enviar_slack(acta, resultado_qa, serial_asignado if debe_comparar_wms else "")
    enviar_whatsapp(acta, resultado_qa)
    guardar_procesado(acta.get("id"))
    print(f"     OK: {ot_nombre} auditada.")
    return True

# =============================================================
#  BUCLE PRINCIPAL
# =============================================================

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
                wms   = cargar_inventario_wms()
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
