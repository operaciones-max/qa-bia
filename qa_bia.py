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

import config

cliente_groq = Groq(api_key=config.GROQ_API_KEY)

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
        tipo      = fila.get("Tipo de servicio", "").strip()
        estado    = fila.get("electrician_status_id", "").strip()
        acta_id   = fila.get("id", "").strip()
        pdf_url   = fila.get("act_pdf_url", "").strip()
        fecha_str = fila.get("start", "").strip()

        if not (tipo in config.TIPOS_SERVICIO_VALIDOS
                and estado in config.ESTADOS_ANALIZAR
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

    pendientes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    print(f"  {len(pendientes)} acta(s) nueva(s) (omitidas por fecha: {omitidas})")

    if config.MODO_PRUEBA and len(pendientes) > config.ACTAS_PRUEBA:
        print(f"  [MODO PRUEBA] Solo {config.ACTAS_PRUEBA} de {len(pendientes)} (las mas recientes).")
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
    es_exitosa = estado_electricista == "CLOSURE_SUCCESSFUL"

    prompt = f"""
Eres un auditor QA experto en ordenes de trabajo de medicion electrica en Colombia para BIA Energy.

TIPO DE SERVICIO: {tipo_label}
RESULTADO EN APP: {"EXITOSA" if es_exitosa else "FALLIDA"}
CODIGO INTERNO BIA: {internal_bia_code}
MEDIDOR ASIGNADO EN SISTEMA WMS: Pendiente

Devuelve UNICAMENTE un JSON valido sin texto adicional ni bloques de codigo.

{{
  "tipo_medida": "<DIRECTA | SEMIDIRECTA | INDIRECTA>",
  "estado_ot": "<EXITOSA | FALLIDA>",
  "medidor_instalado_acta": "<serie exacta del medidor instalado en el acta>",
  "medidor_marca": "<marca del medidor>",
  "medidor_coincide_wms": null,
  "modem_serie": "<serie del modem de telemedida, null si no hay>",
  "modem_marca": "<marca del modem, null si no hay>",
  "modem_ip": "<IP del modem, null si no hay>",
  "factor_medida": "<factor de medida del primer panel>",
  "transformador": "<COMPARTIDO | EXCLUSIVO | NO APLICA>",
  "or_firma": "<SI solo si El Operador de Red asistio dice Si Y el nombre tiene datos reales. Si dice No o campos con guion escribe NO>",
  "validaciones": {{
    "tcs_ok": <true o false>,
    "tps_ok": <true o false>,
    "campos_completos": <true o false>,
    "coherencia": "<COHERENTE | INCOHERENTE | INCOMPLETO>",
    "errores_encontrados": ["errores reales, lista vacia si no hay"]
  }},
  "resumen_observaciones": "<Para INSTALACION: lee la seccion Observaciones del acta (numerada 1,2,3...) y redactala de forma tecnica y profesional en un parrafo continuo incluyendo hora de llegada, tipo de medida encontrada, equipos retirados e instalados con sus seriales, pruebas realizadas y resultado final. Para VISITA PREVIA: resume lo encontrado y el alcance de la actividad>",
  "tipificacion_falla": {{
    "causa_raiz": "<solo si FALLIDA: causa raiz en una linea>",
    "responsable": "<Cliente | Technical Expert | BIA | OR>",
    "detalle": "<descripcion tecnica especifica basada en el acta>",
    "mejora": "<accion correctiva o prerequisito antes de reprogramar>",
    "cinco_por_que": [
      "1. Por que la OT fue fallida? Porque [razon concreta]",
      "2. Por que [problema]? Porque [causa tecnica]",
      "3. Por que [causa]? Porque [razon de fondo]",
      "4. Por que esto afecta? Porque [impacto]",
      "5. Por que no se corrigio? Porque [limitacion]"
    ]
  }},
  "observacion_automatica": "<texto listo para copiar en la app>",
  "alertas_qa": ["alertas menores, lista vacia si no hay"]
}}

REGLAS:
DIRECTA: Es CORRECTO que TCs y TPs NO esten. Solo es error si ESTAN presentes.
SEMIDIRECTA: TCs pueden estar. TPs NO deben estar.
INDIRECTA: TCs y TPs DEBEN estar completos.
INSTALACION: Modem debe tener IP, Puerto, Serie, Marca e IMEI completos.
VISITA PREVIA: medidor vs factura, direccion vs marca de agua,
observaciones deben incluir alcance de la actividad.

--- TEXTO DEL ACTA ---
{texto_pdf[:9000]}
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

def enviar_slack(acta, resultado_qa):
    if not config.SLACK_WEBHOOK_URL or "REEMPLAZA" in config.SLACK_WEBHOOK_URL:
        return

    es_exitosa     = resultado_qa.get("estado_ot") == "EXITOSA"
    color          = "#2eb886" if es_exitosa else "#e01e5a"
    estado_txt     = "EXITOSA" if es_exitosa else "FALLIDA"
    planner        = resultado_qa.get("planner", "N/A")
    or_norm        = resultado_qa.get("or_norm", acta.get("OR_NORM", "N/A"))
    med_acta       = resultado_qa.get("medidor_instalado_acta", "N/A")
    bloque_medidor = f"*Medidor instalado en acta:* {med_acta}\n*Medidor WMS asignado:* Pendiente\n"

    if es_exitosa:
        cuerpo = (
            f"*Codigo interno Bia:* {resultado_qa.get('internal_bia_code', acta.get('internal_bia_code', 'N/A'))}\n"
            f"*Tipo de servicio:* {acta.get('Tipo de servicio', 'N/A')}\n"
            f"{bloque_medidor}"
            f"*IP del medidor:* {resultado_qa.get('modem_ip', 'N/A')}\n"
            f"*Modem Inst:* {resultado_qa.get('modem_serie', 'N/A')}\n"
            f"*Marca modem:* {resultado_qa.get('modem_marca', 'N/A')}\n"
            f"*Factor de medida:* {resultado_qa.get('factor_medida', 'N/A')}\n"
            f"*Transformador:* {resultado_qa.get('transformador', 'N/A')}\n"
            f"*Con OR:* {resultado_qa.get('or_firma', 'N/A')}\n"
            f"*Observaciones:* {resultado_qa.get('resumen_observaciones', 'N/A')}"
        )
    else:
        falla  = resultado_qa.get("tipificacion_falla", {})
        cuerpo = (
            f"*Tipificacion de la OT fallida*\n"
            f"*Causa raiz:* {falla.get('causa_raiz', 'N/A')}\n"
            f"*Responsable:* {falla.get('responsable', 'N/A')}\n"
            f"*Detalle:* {falla.get('detalle', 'N/A')}\n"
            f"*Mejora:* {falla.get('mejora', 'N/A')}\n\n"
            f"{bloque_medidor}"
        )
        alertas = resultado_qa.get("alertas_qa", [])
        if alertas:
            cuerpo += "\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas)

    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{estado_txt}] {acta.get('title', 'Sin titulo')}",
            "fields": [
                {"title": "Tipo",    "value": acta.get("Tipo de servicio", ""), "short": True},
                {"title": "Medida",  "value": resultado_qa.get("tipo_medida", ""), "short": True},
                {"title": "OR",      "value": or_norm,  "short": True},
                {"title": "Planner", "value": planner,  "short": True},
                {"title": "Fecha",   "value": acta.get("start", ""), "short": True},
                {"title": "Empresa", "value": acta.get("company_name", ""), "short": True},
            ],
            "text":   cuerpo,
            "footer": acta.get("address", ""),
        }]
    }

    try:
        requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        print("  Slack enviado.")
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
        print("")
        print("   Cuando todo este bien cambia en config.py:")
        print("   MODO_PRUEBA = False")

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