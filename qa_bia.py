# =============================================================
#  qa_bia.py  —  SISTEMA QA AUTOMATIZADO DE ACTAS BIA ENERGY
#  Motor de IA: Google Gemini
#  Version: 4.0 — Alcances ingenieria + tecnico + comparacion VP
# =============================================================

import os
import json
import time
import csv
import io
import re
import requests
import pdfplumber
from google import genai
from google.genai import types as genai_types
from datetime import datetime, date, timedelta
from twilio.rest import Client as TwilioClient

# GitHub Actions: leer de variables de entorno
if os.environ.get('GEMINI_API_KEY'):
    class config:
        METABASE_CSV_URL     = "https://bia.metabaseapp.com/public/question/5ec265f5-182d-409d-bfbd-45303880da2d.csv"
        WMS_CSV_URL          = "https://bia.metabaseapp.com/public/question/67f6d437-6326-415a-a799-1ee34b9648b0.csv"
        ALCANCES_CSV_URL     = "https://bia.metabaseapp.com/public/question/52353a69-6510-405b-9bbd-754d762a2597.csv"
        GEMINI_API_KEY       = os.environ['GEMINI_API_KEY']
        GEMINI_MODEL         = "gemini-2.5-flash-lite"
        GEMINI_MODELS        = ["gemini-2.5-flash-lite", "gemini-2.0-flash"]
        SLACK_WEBHOOK_URL    = os.environ.get('SLACK_WEBHOOK_URL', '')
        TWILIO_ACCOUNT_SID   = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        TWILIO_AUTH_TOKEN    = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        TWILIO_FROM_WHATSAPP = "whatsapp:+14155238886"
        TWILIO_TO_WHATSAPP   = "whatsapp:+57TUNUMERODECELULAR"
        MODO_PRUEBA          = False
        MODO_UNICO           = True
        MODO_BACKFILL        = True   # Silencia Slack/WhatsApp mientras se repuebla Supabase. Cambiar a False cuando termine.
        ACTAS_PRUEBA         = 2
        FECHA_INICIO          = "2026-05-01"
        FECHA_INICIO_ALCANCES = "2026-04-30"
        PAUSA_GROQ_SEGUNDOS  = 10
        INTERVALO_SEGUNDOS   = 300
        MAX_ACTAS_POR_RUN    = 5
        ARCHIVO_PROCESADOS          = "actas_procesadas.json"
        ARCHIVO_VISITAS_PREVIAS     = "visitas_previas.json"
        ARCHIVO_ALCANCES_PROCESADOS = "alcances_procesados.json"
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

cliente_gemini = genai.Client(api_key=config.GEMINI_API_KEY)

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

def cargar_visitas_previas():
    arch = getattr(config, "ARCHIVO_VISITAS_PREVIAS", "visitas_previas.json")
    if os.path.exists(arch):
        with open(arch, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar_visita_previa(co_code, data):
    arch = getattr(config, "ARCHIVO_VISITAS_PREVIAS", "visitas_previas.json")
    vp = cargar_visitas_previas()
    vp[co_code] = data
    with open(arch, "w", encoding="utf-8") as f:
        json.dump(vp, f, ensure_ascii=False, indent=2)

def cargar_alcances_procesados():
    arch = getattr(config, "ARCHIVO_ALCANCES_PROCESADOS", "alcances_procesados.json")
    if os.path.exists(arch):
        with open(arch, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def guardar_alcance_procesado(alcance_id):
    arch = getattr(config, "ARCHIVO_ALCANCES_PROCESADOS", "alcances_procesados.json")
    procesados = cargar_alcances_procesados()
    if alcance_id not in procesados:
        procesados.append(alcance_id)
    with open(arch, "w", encoding="utf-8") as f:
        json.dump(procesados, f, ensure_ascii=False, indent=2)

ARCHIVO_COOLDOWN_LLM = "groq_cooldown.json"

def _cargar_cooldown_llm():
    if not os.path.exists(ARCHIVO_COOLDOWN_LLM):
        return None
    try:
        with open(ARCHIVO_COOLDOWN_LLM, "r", encoding="utf-8") as f:
            data = json.load(f)
        if datetime.utcnow() >= datetime.fromisoformat(data["until"].replace("Z", "")):
            os.remove(ARCHIVO_COOLDOWN_LLM)
            return None
        return data
    except Exception:
        return None

def _activar_cooldown_llm(msg_error):
    print(f"  [cooldown] Error original Gemini: {msg_error[:400]}")
    msg = msg_error.lower()
    es_diario = ("per day" in msg or "tokens per day" in msg or "requests per day" in msg)
    if es_diario:
        until = datetime.utcnow().replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)
        razon = "daily_quota"
    else:
        m = re.search(r"(?:try again in|retry.*?in|retry_delay.*?seconds:)\s*(\d+\.?\d*)", msg_error)
        segundos = int(float(m.group(1))) + 5 if m else 65
        until = datetime.utcnow() + timedelta(seconds=segundos)
        razon = "per_minute"
    data = {
        "until":   until.isoformat(timespec="seconds") + "Z",
        "razon":   razon,
        "activado": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    with open(ARCHIVO_COOLDOWN_LLM, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _alertar_slack_cooldown(data)
    return data

def _alertar_slack_cooldown(data):
    if getattr(config, "MODO_BACKFILL", False):
        return  # silenciado durante backfill — solo loguea en consola
    url = os.environ.get("SLACK_WEBHOOK_URL", "") or getattr(config, "SLACK_WEBHOOK_URL", "")
    if not url:
        return
    titulo = "QA pausado: Gemini agoto cuota diaria" if data["razon"] == "daily_quota" \
             else "QA pausado: Gemini rate-limit transitorio"
    cuerpo = f"*{titulo}*\n• Reanudacion estimada (UTC): `{data['until']}`\n• Tipo: `{data['razon']}`"
    try:
        requests.post(url, json={"text": cuerpo}, timeout=10)
    except Exception as e:
        print(f"  ERROR alerta Slack cooldown: {e}")

ARCHIVO_FACTURAS_EXTRAIDAS = "facturas_extraidas.json"
METABASE_BASE = "https://bia.metabaseapp.com"
METABASE_QUESTION_FACTURAS = 69895

def cargar_facturas_anteriores():
    """Carga del Metabase question 69895 las URLs de facturas anteriores por CO.
    Devuelve dict {internal_bia_code: invoice_document_url}.
    Requiere METABASE_API_KEY env var."""
    api_key = os.environ.get("METABASE_API_KEY", "").strip()
    if not api_key:
        print("  WARN: METABASE_API_KEY no configurada — sin validacion factura anterior")
        return {}
    url = f"{METABASE_BASE}/api/card/{METABASE_QUESTION_FACTURAS}/query/csv"
    print(f"  Pidiendo {url} (key: {api_key[:6]}...{api_key[-4:] if len(api_key)>10 else ''})")
    try:
        r = requests.get(url, headers={"X-API-KEY": api_key}, timeout=60)
        ct = r.headers.get("content-type", "")
        print(f"  Status: {r.status_code} | Content-Type: {ct} | size: {len(r.content)} bytes")
        if r.status_code != 200:
            print(f"  Respuesta del servidor: {r.text[:300]}")
            return {}
        if "csv" not in ct and "text/plain" not in ct:
            # Posible que devuelva HTML/JSON de error
            print(f"  WARN: Content-Type inesperado. Primeros 200 chars: {r.text[:200]}")
        lector = csv.DictReader(io.StringIO(r.content.decode("utf-8")))
        result = {}
        primera = None
        for fila in lector:
            if primera is None:
                primera = list(fila.keys())
                print(f"  Columnas CSV: {primera}")
            co = (fila.get("internal_bia_code") or "").strip()
            inv = (fila.get("invoice_document_url") or "").strip()
            if co and inv:
                result[co] = inv
        print(f"  Facturas anteriores cargadas: {len(result)} CO con URL de factura.")
        return result
    except Exception as e:
        print(f"  ERROR cargando facturas anteriores: {e}")
        return {}

def _cargar_facturas_extraidas():
    if not os.path.exists(ARCHIVO_FACTURAS_EXTRAIDAS):
        return {}
    try:
        with open(ARCHIVO_FACTURAS_EXTRAIDAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _guardar_factura_extraida(co_code, data):
    cache = _cargar_facturas_extraidas()
    cache[co_code] = data
    with open(ARCHIVO_FACTURAS_EXTRAIDAS, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def extraer_serial_factura(pdf_url):
    """Descarga PDF de factura y extrae el numero de medidor + flag express via Gemini.
    Devuelve (data_dict, estado) donde data_dict = {serial, express}."""
    try:
        r = requests.get(pdf_url, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        return None, f"error_descarga: {e}"

    texto = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for p in pdf.pages:
                t = p.extract_text()
                if t:
                    texto += t + "\n"
    except Exception as e:
        return None, f"error_pdf: {e}"

    if not texto.strip():
        return None, "pdf_vacio"

    # Deteccion express ANTES de Gemini — basta con buscar la palabra
    express = "express" in texto.lower()

    cd = _cargar_cooldown_llm()
    if cd:
        return {"serial": None, "express": express}, "cooldown"

    prompt = (
        "Esta es una factura de servicio electrico colombiana del comercializador anterior. "
        "Extrae UNICAMENTE el numero de serie del medidor electrico que aparece. "
        "El campo puede llamarse: 'Numero', 'Medidor', 'Dispositivo', 'Serie', "
        "'Numero del medidor', 'Serial del medidor', 'No. medidor', 'Medidor No', "
        "'Equipo', 'Aparato'. NO inventes, si no aparece serial valido devuelve null. "
        "Responde SOLO con JSON: {\"serial\": \"<numero>\" o null}\n\n"
        "--- FACTURA ---\n" + texto[:6000]
    )

    modelo = (getattr(config, "GEMINI_MODELS", None) or [config.GEMINI_MODEL])[0]
    try:
        respuesta = cliente_gemini.models.generate_content(
            model=modelo,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=200,
                response_mime_type="application/json",
            ),
        )
        texto_r = (respuesta.text or "").strip()
        data = json.loads(texto_r)
        serial = (data.get("serial") or "").strip() or None
        return {"serial": serial, "express": express}, "ok"
    except Exception as e:
        msg = str(e)
        if "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
            _activar_cooldown_llm(msg)
            return {"serial": None, "express": express}, "rate_limit"
        return {"serial": None, "express": express}, f"error_gemini: {msg[:120]}"

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
#  ALCANCES INGENIERIA
# =============================================================

def cargar_alcances():
    try:
        url = getattr(config, "ALCANCES_CSV_URL", "https://bia.metabaseapp.com/public/question/52353a69-6510-405b-9bbd-754d762a2597.csv")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        lector = csv.DictReader(io.StringIO(r.content.decode('utf-8', errors='replace')))
        alcances = {}
        for fila in lector:
            co    = fila.get("Codigo Interno Bia", "").strip()
            fecha = fila.get("Creado El", "").strip()
            tipo  = fila.get("Tipo De Alcance", "").strip().upper()
            if not co or tipo != "INST":
                continue
            existing = alcances.get(co)
            if not existing or fecha > existing.get("Creado El", ""):
                alcances[co] = dict(fila)
        print(f"  Alcances cargados: {len(alcances)} codigos.")
        return alcances
    except Exception as e:
        print(f"  ERROR alcances: {e}")
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
    om_tipo = om_estado = om_sin_acta = om_sin_pdf = om_fecha = om_ya_proc = om_fecha_invalida = 0

    for fila in lector:
        tipo       = fila.get("Tipo de servicio", "").strip()
        estado     = fila.get("electrician_status_id", "").strip()
        acta_id    = fila.get("id", "").strip()
        pdf_url    = fila.get("act_pdf_url", "").strip()
        fecha_str  = fila.get("start", "").strip()
        tiene_acta = fila.get("Tiene Acta", "").strip()

        if tipo not in config.TIPOS_SERVICIO_VALIDOS:
            om_tipo += 1; continue
        if estado not in config.ESTADOS_ANALIZAR:
            om_estado += 1; continue
        if tiene_acta != "Con Acta":
            om_sin_acta += 1; continue
        if not pdf_url:
            om_sin_pdf += 1; continue
        try:
            if date.fromisoformat(fecha_str[:10]) < fecha_inicio:
                om_fecha += 1; continue
        except Exception:
            om_fecha_invalida += 1; continue
        if acta_id in procesados:
            om_ya_proc += 1; continue
        pendientes.append(fila)

    pendientes.sort(key=lambda x: (x.get("start", ""), x.get("created_at", "")))
    print(f"  {len(pendientes)} acta(s) nueva(s) | filtradas: tipo={om_tipo} estado={om_estado} "
          f"sin_acta={om_sin_acta} sin_pdf={om_sin_pdf} fecha={om_fecha} fecha_invalida={om_fecha_invalida} "
          f"ya_procesadas={om_ya_proc}")

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

MAX_PAGINAS_VISION = 0   # 0 = vision desactivada (volver a 4-8 cuando free tier reset)
DPI_VISION         = 60  # resolucion de las imagenes — mas bajo = menos tokens

def descargar_y_leer_pdf(url):
    """Devuelve (texto, lista_de_imagenes_jpeg_bytes)."""
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        pdf_bytes = r.content

        texto = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for pagina in pdf.pages:
                try:
                    t = pagina.extract_text()
                    if t:
                        texto += t + "\n"
                except Exception:
                    continue

        imagenes = _renderizar_pdf_a_imagenes(pdf_bytes)
        texto_final = texto.strip() if texto.strip() else None
        return texto_final, imagenes
    except Exception as e:
        print(f"  ERROR leyendo PDF: {e}")
        return None, []

def _renderizar_pdf_a_imagenes(pdf_bytes):
    """Renderiza paginas del PDF como JPEG bytes. Limitado a MAX_PAGINAS_VISION."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("  WARN: PyMuPDF no instalado, sin vision (solo texto)")
        return []
    imagenes = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = min(len(doc), MAX_PAGINAS_VISION)
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=DPI_VISION)
            imagenes.append(pix.tobytes("jpeg"))
        doc.close()
    except Exception as e:
        print(f"  WARN: no se pudieron renderizar imagenes del PDF: {e}")
    return imagenes

# =============================================================
#  ANALISIS CON GEMINI
# =============================================================

def analizar_acta(texto_pdf, tipo_servicio, estado_electricista,
                  internal_bia_code="", serial_asignado_wms="", marca_asignada_wms="",
                  tcs_asignados_wms=None, tps_asignados_wms=None, imagenes_pdf=None):
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
- VAS A RECIBIR el texto del acta Y las paginas del acta como imagenes adjuntas. USA AMBAS fuentes:
  * Verifica visualmente las series, lecturas y marcas del medidor en las fotos del acta.
  * Cuenta visualmente los SELLOS presentes en cada equipo (medidor, TCs, TPs) y reporta el numero exacto que veas.
  * Si la serie escrita en el campo "Serie del medidor" NO se ve en la foto del medidor o se ve diferente, marca serie_coincide_foto=false con observacion explicita ("se ve serie XXX en foto, acta dice YYY").
  * Si la foto muestra el diagrama unifilar, marca diagrama_unifilar.tiene_foto=true.
  * Si las fotos estan borrosas, oscuras o no permiten leer, NO marques verificaciones como true; marca como false con observacion ("foto ilegible").
- MARCAS: si "Marca del medidor", "Marca del modem", "Marca del totalizador" dice "Otra"/"Otro", usa el valor del siguiente campo "Ingresar marca..." como marca real. NUNCA concatenes.
- "serie_coincide_foto" SIEMPRE true o false (nunca null si hay seccion Registro fotografico):
    1. Toma la serie EXACTA del campo "Serie del medidor".
    2. En el bloque "Registro fotografico medidor, sellos y celdas" siguiente busca esa misma cadena.
    3. Si aparece -> true. Si no aparece o aparece distinta -> false.
    4. Si true: "observacion_serie_foto" = null. Si false: explica brevemente con la serie real vista.
- CONTEO DE FOTOS: cada foto cargada en el acta tiene un timestamp con formato "Bia [fecha] [hora]" (ej: "Bia 2 may 2026 09:52:45"). Cuenta esos timestamps DENTRO de cada bloque "Registro fotografico" relevante:
  * "fotos_medidor": cuenta los timestamps en los bloques "Registro fotografico medidor, sellos y celdas" (encontrado E instalado combinados). Aplica para DIRECTA/SEMIDIRECTA/INDIRECTA.
  * "fotos_tcs": cuenta los timestamps en los bloques "Registro fotografico de TCs..." (encontrados E instalados). null si DIRECTA.
  * "fotos_tps": cuenta los timestamps en los bloques "Registro fotografico de TPs..." (encontrados E instalados). null si DIRECTA o SEMIDIRECTA.
- WMS comparacion (ignorando ceros a la izquierda y espacios):
  * "medidor_coincide_wms": Si MEDIDOR ASIGNADO arriba dice "No aplica" -> null. Si no, true/false comparando serie_instalada vs WMS.
  * "tcs_coinciden_wms": null si DIRECTA o si TCs ASIGNADOS dice "No aplica". Si no, true solo si CADA serial asignado en WMS aparece tambien en tcs_instalados.seriales (orden libre, comparacion por conjunto).
  * "tps_coinciden_wms": null si DIRECTA o SEMIDIRECTA o si TPs ASIGNADOS dice "No aplica". Si no, true solo si CADA serial asignado en WMS aparece tambien en tps_instalados.seriales.
- TECNICO EJECUTOR: Busca en el acta quien ejecuto la actividad. Reglas estrictas:
  1. Lee TODAS las firmas, sellos, encabezados y campos donde aparece "Tecnico", "Electricista", "Operario", "Ejecutor", "Empresa contratista", "Razon social".
  2. Si el acta menciona EXPLICITAMENTE que la empresa es BIA Energy o BIA Field Services o BIA SAS o solo "BIA" como empleador del tecnico, marca tecnico_empresa="BIA" y contratista_nombre=null.
  3. Si menciona cualquier OTRA razon social distinta a BIA (ej: "SOTO ALIRIO ENRIQUE", "CHADAZA SAS", "AYC INGENIERIA", "ELECTROCOSTA SAS", una persona natural con cedula como contratista, etc.), marca tecnico_empresa="CONTRATISTA" y contratista_nombre con la razon social EXACTA tal como aparece en el acta.
  4. Si el acta no es claro o no menciona empresa, NO inventes — usa contratista_nombre con el texto literal que aparezca cerca del nombre del tecnico, y elige tecnico_empresa segun lo que mejor se ajuste. Si dudas: usa "CONTRATISTA" (mas seguro asumir contratista que asumir BIA).
  5. tecnico_nombre debe ser el nombre completo de la persona que firmo o aparece como ejecutor — NO el nombre de la empresa.
  6. NUNCA inventes nombres de empresa o de tecnico. Si no aparece, usa null.
- OBSERVACION VERBATIM: Copia LETRA POR LETRA el contenido del campo "Observaciones" del acta. NO resumas, NO parafrasees, NO corrijas ortografia, NO agregues nada. Si hay varias secciones de observaciones concatena con salto de linea. Si no existe el campo usa null.
- SELLOS: Cuenta los sellos visibles/reportados en el acta para cada equipo:
  * "sellos_medidor_encontrado": sellos presentes en el medidor encontrado (int, 0 si no tiene, null si no se reporta).
  * "sellos_tcs_encontrados": sellos en TCs encontrados (null si DIRECTA).
  * "sellos_tps_encontrados": sellos en TPs encontrados (null si DIRECTA o SEMIDIRECTA).
  * "sellos_medidor_instalado": sellos colocados al medidor instalado (null si VISITA PREVIA o no se instalo).
  * "sellos_tcs_instalados": sellos colocados a TCs instalados (null si no aplica).
  * "sellos_tps_instalados": sellos colocados a TPs instalados (null si no aplica).

REGLAS POR TIPO DE MEDIDA:
- DIRECTA: tcs_*, tps_*, bloque_pruebas_*, cable_control_* TODOS aplica=false.
- SEMIDIRECTA: tps_* aplica=false. Resto aplica.
- INDIRECTA: TODOS aplican.

REGLAS POR TIPO DE SERVICIO:
- INSTALACION: campos *_instalado se llenan si se instalo el equipo (se_instalo true) o false.
- VISITA PREVIA: TODOS los *_instalado tienen aplica=false.

REGLAS ESTRICTAS PARA validaciones.errores_encontrados:
- NUNCA reportes como error el comportamiento esperado por las REGLAS POR TIPO DE MEDIDA y REGLAS POR TIPO DE SERVICIO. Por ejemplo:
  * En DIRECTA, TCs y TPs con aplica=false NO es un error — es lo correcto. NO lo listes.
  * En VISITA PREVIA, todos los *_instalado con se_instalo=false y aplica=false NO es un error — es lo correcto. NO lo listes.
  * En SEMIDIRECTA, tps_* con aplica=false NO es un error.
- Solo reporta ERRORES REALES de QA: discrepancias entre acta y foto, datos faltantes que SI deberian existir, contradicciones internas, valores fuera de rango.
- CONSISTENCIA OBLIGATORIA: si pones "serie no coincide con foto" en errores_encontrados, entonces medidor_*.serie_coincide_foto DEBE ser false. Si pones serie_coincide_foto=true, NO listes ese error. Cero contradicciones entre campos.
- Si la observacion del tecnico explica por que falta un dato (ej: "OR no permitio tomar fotos"), reportalo como ALERTA en alertas_qa, no como error en errores_encontrados.

REGLA CRITICA DE OVERRIDE A FALLIDA:
- Si RESULTADO EN APP dice EXITOSA pero el acta esta SUSTANCIALMENTE INCOMPLETA (ej: medidor encontrado sin serie ni marca ni lecturas, sin sellos reportados, sin fotos del medidor, sin pruebas, sin diagrama unifilar, todo simultaneamente), debes marcar estado_ot=FALLIDA aunque el RESULTADO EN APP diga EXITOSA. La data incompleta no permite cerrar el QA como exitoso.
- Solo manten estado_ot=EXITOSA si los datos clave del acta (medidor, lecturas, fotos al menos parciales, sellos, pruebas si aplica) estan razonablemente completos.
- Si haces este override, en tipificacion_falla.detalle empieza con: "Override automatico a FALLIDA: el acta esta cerrada como CLOSURE_SUCCESSFUL pero la informacion reportada es sustancialmente incompleta (especificar campos faltantes)." Despues sigue con el resto del detalle estandar.
- Si el override aplica, tipificacion_falla.causa_raiz debe reflejar el problema de calidad del acta (ej: "Acta cerrada exitosa con informacion sustancialmente incompleta").

JSON ESPERADO:
{{
  "tipo_medida": "DIRECTA | SEMIDIRECTA | INDIRECTA",
  "factor_medida": "<numero como string>",
  "estado_ot": "EXITOSA | FALLIDA",

  "tecnico_nombre": "<nombre completo del tecnico que ejecuto la actividad, o null>",
  "tecnico_empresa": "BIA | CONTRATISTA",
  "contratista_nombre": "<nombre empresa contratista si aplica, null si es BIA>",
  "observacion_tecnico_verbatim": "<texto EXACTO del campo observaciones del acta, null si no hay>",

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

  "sellos_medidor_encontrado": <int o null>,
  "sellos_tcs_encontrados": <int o null>,
  "sellos_tps_encontrados": <int o null>,
  "sellos_medidor_instalado": <int o null>,
  "sellos_tcs_instalados": <int o null>,
  "sellos_tps_instalados": <int o null>,

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

  "fotos_medidor": <int o null>,
  "fotos_tcs": <int o null>,
  "fotos_tps": <int o null>,

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
    "mejora": "<accion ESTRUCTURAL de proceso, no operativa. NO escribas 'reprogramar la visita'. SI escribe cambios sistemicos. Ejemplo gold: 'Implementar un control de cierre de viabilidad tecnica previo a la programacion de instalaciones, asegurando que todas las restricciones detectadas en visitas previas cuenten con solucion aprobada (diseno, materiales y permisos) antes de agendar la OT.'>",
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
  "mejora": "Implementar un control de cierre de viabilidad tecnica previo a la programacion de instalaciones, asegurando que todas las restricciones detectadas en visitas previas cuenten con solucion aprobada (diseno, materiales y permisos) antes de agendar la OT."
}}

REGLA OR_FIRMA:
- SI solo si "El Operador de Red asistio" dice "Si" Y hay nombre, cedula y telefono reales (no guiones).
- NO en cualquier otro caso.

--- TEXTO DEL ACTA ---
{texto_pdf[:20000]}
"""

    cd = _cargar_cooldown_llm()
    if cd:
        print(f"  Gemini en cooldown ({cd['razon']}) hasta {cd['until']} - se omite analisis.")
        return None

    contents = [prompt]
    for img_bytes in (imagenes_pdf or []):
        contents.append(genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    modelos = getattr(config, "GEMINI_MODELS", [config.GEMINI_MODEL])
    texto = ""
    for idx, modelo in enumerate(modelos):
        es_ultimo = (idx == len(modelos) - 1)
        try:
            respuesta = cliente_gemini.models.generate_content(
                model=modelo,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                ),
            )
            texto = (respuesta.text or "").strip()
            if "```json" in texto:
                texto = texto.split("```json")[1].split("```")[0].strip()
            elif "```" in texto:
                texto = texto.split("```")[1].split("```")[0].strip()
            inicio = texto.find("{")
            fin    = texto.rfind("}")
            if inicio != -1 and fin != -1:
                texto = texto[inicio:fin+1]
            resultado = json.loads(texto)
            if idx > 0:
                print(f"  Modelo usado: {modelo} (fallback)")
            return resultado
        except json.JSONDecodeError:
            print(f"  JSON invalido de {modelo}: {texto[:150]}")
        except Exception as e:
            msg = str(e)
            msg_lower = msg.lower()
            es_rate_limit = ("429" in msg or "rate_limit" in msg_lower or "rate limit" in msg_lower
                             or "resource_exhausted" in msg_lower or "resource exhausted" in msg_lower
                             or "quota" in msg_lower)
            if es_rate_limit:
                cd = _activar_cooldown_llm(msg)
                print(f"  Limite Gemini detectado ({cd['razon']}). Cooldown hasta {cd['until']}. Se aborta.")
                return None
            es_transitorio = "503" in msg or "unavailable" in msg_lower or "high demand" in msg_lower
            if es_transitorio:
                print(f"  {modelo} 503/transitorio.")
            else:
                print(f"  ERROR {modelo}: {e}")
        if not es_ultimo:
            print(f"  Probando siguiente modelo: {modelos[idx + 1]}...")
            time.sleep(2)
    print(f"  Todos los modelos Gemini ({len(modelos)}) fallaron.")
    return None

# =============================================================
#  POST-VALIDACIONES (defensivas)
# =============================================================

def _post_corregir_serie_foto(item):
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
        qa["fotos_tcs"] = None
        qa["fotos_tps"] = None
    elif tipo_medida == "SEMIDIRECTA":
        for k in ("tps_encontrados", "tps_instalados"):
            _force_false(k)
        qa["fotos_tps"] = None

    if es_visita:
        for k in ("medidor_instalado", "tcs_instalados", "tps_instalados",
                  "bloque_pruebas_instalado", "cable_control_instalado",
                  "telemedida_instalada", "totalizador_instalado",
                  "cables_potencia_instalados", "medidor_respaldo_instalado",
                  "sellos_instalados"):
            _force_false(k)

def _validar_coincidencia_wms(qa, serial_wms, tcs_wms, tps_wms, debe_comparar):
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

    if debe_comparar and tcs_wms and tipo_medida in ("SEMIDIRECTA", "INDIRECTA"):
        tcs_inst = (qa.get("tcs_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tcs_wms if s}
        acta_set = {_normalizar_serial(s) for s in tcs_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tcs_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tcs_coinciden_wms"] = None

    if debe_comparar and tps_wms and tipo_medida == "INDIRECTA":
        tps_inst = (qa.get("tps_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tps_wms if s}
        acta_set = {_normalizar_serial(s) for s in tps_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tps_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tps_coinciden_wms"] = None

_VALORES_BASURA = {
    "", "n/a", "na", "n.v", "nv", "no aplica", "no se reporta",
    "otra", "otro", ".0", "0.0", ".o", "0", "null", "none", "-", "—",
}

def _es_valor_basura(v):
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in _VALORES_BASURA

def _limpiar_errores_fantasma(qa, tipo_servicio):
    """Saca errores que reportan comportamiento NORMAL segun reglas de medida/servicio.
    Tambien dedupea errores vs alertas y elimina ruido."""
    val = qa.get("validaciones") or {}
    errores = val.get("errores_encontrados") or []
    alertas = qa.get("alertas_qa") or []

    tipo_medida    = (qa.get("tipo_medida") or "").upper()
    es_visita      = "previa" in (tipo_servicio or "").lower()
    es_directa     = tipo_medida == "DIRECTA"
    es_semidirecta = tipo_medida == "SEMIDIRECTA"

    def es_fantasma(item):
        s = " " + (item or "").lower() + " "
        if es_directa:
            for term in (" tc ", " tcs ", " tp ", " tps ", "bloque de pruebas",
                         "bloque pruebas", "cable de control", "cable control"):
                if term in s:
                    return True
        if es_semidirecta:
            if (" tp " in s or " tps " in s) and " tc " not in s and " tcs " not in s:
                return True
        if es_visita:
            if "instalad" in s and "telemedida instalad" not in s and "totalizador instalad" not in s:
                return True
            for term in ("pruebas de funcionamiento", "equipo patron", "equipo patrón",
                         "diagrama unifilar", "no se realizaron pruebas",
                         "no se reporta equipo", "no se reporta foto",
                         "no se reportan fotos", "no se reportan sellos",
                         "no se encontraron sellos", "no se encontro sello",
                         "no se encontraron fotos", "no se encontro foto",
                         "no se encontro telemedida", "no se encontró telemedida",
                         "no se encontro bloque", "no se encontró bloque",
                         "no se encontro cable", "no se encontró cable",
                         "medidor de respaldo", "medidor de espejo",
                         "planta de respaldo", "planta electrica",
                         "no se encontraron alertas", "no se encontraron tcs",
                         "no se encontraron tps",
                         "el acta no reporta", "no se reporta el color",
                         "no se reporta la serie del sello",
                         "no reporta la serie del sello",
                         "no reporta el color del sello",
                         "no se reporta el segundo sello", "no se reporta el tercer sello",
                         "color del sello", "serie del sello",
                         "no reporta lectura", "no se reporta lectura",
                         "operador de red", "comercializador anterior"):
                if term in s:
                    return True
        for term in ("medidor de respaldo", "medidor de espejo", "planta de respaldo",
                     "no se encontro"):
            if term in s and tipo_medida == "DIRECTA":
                return True
        # Campos del acta con valor basura: el override a FALLIDA ya tipifica eso
        for term in (": n.v", ": .o", ": .0", ": otra", ": otro",
                     "no reportada", "no reportado"):
            if term in s and ("encontrada" in s or "encontrado" in s
                              or "instalada" in s or "instalado" in s):
                return True
        return False

    errores_l = [e for e in errores if not es_fantasma(e)]
    alertas_l = [a for a in alertas if not es_fantasma(a)]
    set_err = set(errores_l)
    alertas_l = [a for a in alertas_l if a not in set_err]

    val["errores_encontrados"] = errores_l
    qa["validaciones"] = val
    qa["alertas_qa"] = alertas_l

def _simplificar_fallida(qa):
    """Cuando estado_ot=FALLIDA, vacia errores, deja solo alertas de firma OR/usuario,
    y elimina cinco_por_que de tipificacion (redundante con causa_raiz/detalle/mejora).
    La tipificacion ya explica todo — no es util listar errores tecnicos ni 5 porques."""
    if qa.get("estado_ot") != "FALLIDA":
        return
    val = qa.get("validaciones") or {}
    val["errores_encontrados"] = []
    qa["validaciones"] = val
    alertas = qa.get("alertas_qa") or []
    keep = []
    for a in alertas:
        a_low = (a or "").lower()
        if "firm" in a_low and ("operador" in a_low or " or " in a_low or "or " in a_low or "usuario" in a_low or "cliente" in a_low):
            keep.append(a)
    if (qa.get("or_firma") or "").upper() == "NO":
        already = any("operador" in (k or "").lower() and "firm" in (k or "").lower() for k in keep)
        if not already:
            keep.append("El Operador de Red NO firmó el acta.")
    qa["alertas_qa"] = keep
    falla = qa.get("tipificacion_falla") or {}
    falla["cinco_por_que"] = []
    qa["tipificacion_falla"] = falla

def _override_fallida_si_incompleto(qa):
    """Si estado_ot=EXITOSA pero los datos critically incompletos, fuerza FALLIDA
    con tipificacion auto-poblada. Tambien limpia errores ya que tipificacion
    los explica."""
    if qa.get("estado_ot") != "EXITOSA":
        return

    med = qa.get("medidor_encontrado") or {}
    diag = qa.get("diagrama_unifilar") or {}
    val  = qa.get("validaciones") or {}

    flags = [
        _es_valor_basura(med.get("serie")),
        _es_valor_basura(med.get("marca")),
        _es_valor_basura(med.get("referencia")),
        _es_valor_basura(med.get("lectura_activa_kwh")),
        _es_valor_basura(qa.get("sellos_medidor_encontrado")),
        not diag.get("tiene_foto"),
    ]
    n_basura = sum(1 for f in flags if f)
    coherencia_mala = (val.get("coherencia") or "").upper() in ("INCOHERENTE", "INCOMPLETO")

    if n_basura < 4 and not coherencia_mala:
        return

    qa["estado_ot"] = "FALLIDA"
    # Limpiar errores cuando override fire — tipificacion ya explica
    val["errores_encontrados"] = []
    val["coherencia"] = "INCOHERENTE"
    qa["validaciones"] = val
    co = qa.get("internal_bia_code", "")
    falla = qa.get("tipificacion_falla") or {}
    falla.update({
        "causa_raiz":  "Acta cerrada exitosa con informacion sustancialmente incompleta",
        "responsable": "Tecnico ejecutor / Coordinador Operativo",
        "detalle": (
            f"Override automatico a FALLIDA: la OT {co} fue cerrada como CLOSURE_SUCCESSFUL "
            f"pero la informacion reportada en el acta es sustancialmente incompleta o contiene "
            f"valores placeholder (n.v, .o, .0, Otra, etc.) en campos criticos del medidor "
            f"encontrado, sellos, lecturas y registro fotografico. La data no permite cerrar "
            f"el QA como exitoso ni validar la ejecucion."
        ),
        "mejora": (
            "Implementar validacion estricta en el formulario del acta para rechazar valores "
            "placeholder y exigir captura completa de los campos minimos del medidor (serie, "
            "marca, referencia, lecturas, sellos, foto, diagrama unifilar) antes de permitir "
            "el cierre exitoso de la OT. Agregar revision de calidad de captura previa al cierre."
        ),
        "cinco_por_que": [],
    })
    qa["tipificacion_falla"] = falla

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

def _av(fila, *cols):
    """Get first non-empty value from alcance CSV row."""
    for col in cols:
        v = (fila.get(col) or "").strip()
        if v and v not in ("-", "N/A", "n/a", "nan"):
            return v
    return "N/A"

def _check(ok):
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
    return ""

def _viable_ok(s):
    """Normalize 'Sí'/'Si'/'S?' variations from CSV encoding."""
    return s.lower().strip() in ("si", "sí", "s?", "yes", "true", "1")

# --- Secciones hallazgos tecnicos ---

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

def _seccion_medidor_encontrado(m, sellos=None):
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
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base

def _seccion_medidor_instalado(m, coincide_wms=None, serial_wms="", fotos=None, sellos=None):
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
    if fotos is not None:
        base += f"  Fotos cargadas: {fotos}\n"
    if sellos is not None:
        base += f"  Sellos instalados: {sellos}\n"
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

def _seccion_tcs_encontrados(d, sellos=None):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("tiene"):
        return "*TCs encontrados:* No\n"
    seriales = d.get("seriales") or []
    base = "*TCs encontrados*\n"
    if seriales:
        base += f"  Seriales: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base

def _seccion_tps_encontrados(d, sellos=None):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("tiene"):
        return "*TPs encontrados:* No\n"
    seriales = d.get("seriales") or []
    base = "*TPs encontrados*\n"
    if seriales:
        base += f"  Seriales: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base

def _seccion_tc_tp_instalados(label, d, wms_asignados, coincide, fotos=None, sellos=None):
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
    if fotos is not None:
        base += f"  Fotos cargadas: {fotos}\n"
    if sellos is not None:
        base += f"  Sellos instalados: {sellos}\n"
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

# --- Secciones VISITA PREVIA ---

def _seccion_tecnico(qa):
    nombre = _v(qa.get("tecnico_nombre"), "")
    if not nombre:
        return ""
    empresa = (qa.get("tecnico_empresa") or "").strip()
    contratista = _v(qa.get("contratista_nombre"), "")
    if empresa == "CONTRATISTA" and contratista:
        empresa_txt = f"Contratista - {contratista}"
    elif empresa == "BIA":
        empresa_txt = "BIA Energy"
    else:
        empresa_txt = empresa or "N/A"
    return (
        "*Tecnico ejecutor*\n"
        f"  Nombre: {nombre}\n"
        f"  Empresa: {empresa_txt}\n"
    )

def _seccion_observacion_tecnico(qa):
    obs = (qa.get("observacion_tecnico_verbatim") or "").strip()
    if not obs or obs in ("null", "N/A", "-"):
        return ""
    return f"*Observacion del tecnico:*\n_{obs}_\n"

def _seccion_alcance_ingenieria(a):
    """Render full engineering alcance from CSV row."""
    if not a:
        return "*Alcance de ingenieria:* Sin alcance registrado\n"

    viable = _av(a, "Viable Para Instalar")
    viable_chk = "✅" if _viable_ok(viable) else ("❌" if viable.lower() == "no" else "")

    lines = [f"*Alcance de ingenieria* {viable_chk}\n".rstrip() + "\n"]
    lines.append(f"  Viable para instalar: {viable}\n")

    medida_inst  = _av(a, "Tipo De Medida A Instalar")
    factor_inst  = _av(a, "Factor De Medida A Instalar")
    nivel_inst   = _av(a, "Nivel De Tension A Instalar")
    cambio_eq    = _av(a, "Se Require Cambio De Equipos")

    if medida_inst != "N/A":  lines.append(f"  Medida a instalar: {medida_inst}\n")
    if factor_inst != "N/A":  lines.append(f"  Factor a instalar: {factor_inst}\n")
    if nivel_inst  != "N/A":  lines.append(f"  Nivel de tension: {nivel_inst}\n")
    if cambio_eq   != "N/A":  lines.append(f"  Cambio de equipos: {cambio_eq}\n")

    # TCs a instalar
    tipo_tc   = _av(a, "Tipo De Tc A Instalar")
    rel_tc    = _av(a, "Relacion De Transformacion Del Tc A Instalar")
    burden_tc = _av(a, "Burden Del Tc A Instalar")
    clase_tc  = _av(a, "Clase Del Tc A Instalar")
    if any(x != "N/A" for x in [tipo_tc, rel_tc, burden_tc, clase_tc]):
        parts = []
        if tipo_tc   != "N/A": parts.append(f"Tipo={tipo_tc}")
        if rel_tc    != "N/A": parts.append(f"Relacion={rel_tc}")
        if burden_tc != "N/A": parts.append(f"Burden={burden_tc} VA")
        if clase_tc  != "N/A": parts.append(f"Clase={clase_tc}")
        lines.append(f"  TCs a instalar: {' | '.join(parts)}\n")

    # TPs a instalar
    tipo_tp   = _av(a, "Tipo De Tp A Instalar")
    rel_tp    = _av(a, "Relacion De Transformacion Del Tp A Instalar")
    burden_tp = _av(a, "Burden Del Tp A Instalar")
    clase_tp  = _av(a, "Clase Del Tp A Instalar")
    if any(x != "N/A" for x in [tipo_tp, rel_tp, burden_tp, clase_tp]):
        parts = []
        if tipo_tp   != "N/A": parts.append(f"Tipo={tipo_tp}")
        if rel_tp    != "N/A": parts.append(f"Relacion={rel_tp}")
        if burden_tp != "N/A": parts.append(f"Burden={burden_tp} VA")
        if clase_tp  != "N/A": parts.append(f"Clase={clase_tp}")
        lines.append(f"  TPs a instalar: {' | '.join(parts)}\n")

    # Telemedida
    antena   = _av(a, "Requiere Antena De Alta Ganancia")
    oper     = _av(a, "Operador De Red Celular")
    ubi_ant  = _av(a, "Ubicacion De La Antena")
    if any(x != "N/A" for x in [antena, oper, ubi_ant]):
        parts = []
        if antena  != "N/A": parts.append(f"Antena alta ganancia: {antena}")
        if oper    != "N/A": parts.append(f"Operador: {oper}")
        if ubi_ant != "N/A": parts.append(f"Ubicacion: {ubi_ant}")
        lines.append(f"  {' | '.join(parts)}\n")

    # Descargos
    descargos = _av(a, "Requiere Descargos Del Or")
    if descargos != "N/A":
        afecta  = _av(a, "El Descargo Afecta A Otros Usuarios")
        cuantos = _av(a, "A Cuantos Usuarios Afecta")
        linea   = f"  Requiere descargos OR: {descargos}"
        if afecta != "N/A": linea += f" | Afecta otros: {afecta}"
        if cuantos not in ("N/A", "0", "0.0"): linea += f" ({cuantos} usuarios)"
        lines.append(linea + "\n")

    maniobra = _av(a, "Maniobra")
    tiempo   = _av(a, "Tiempo De Corte H")
    if maniobra != "N/A" or tiempo != "N/A":
        m_short = maniobra[:80] + "..." if len(maniobra) > 80 else maniobra
        lines.append(f"  Maniobra: {m_short} | Tiempo corte: {tiempo} h\n")

    # Bloque, reubicacion, frontera
    cambio_bloque = _av(a, "Requiere Cambio Bloque")
    tipo_bloque   = _av(a, "Tipo De Bloque De Pruebas A Instalar")
    if cambio_bloque != "N/A":
        lines.append(f"  Cambio bloque pruebas: {cambio_bloque}" +
                     (f" | Tipo: {tipo_bloque}" if tipo_bloque != "N/A" else "") + "\n")

    reubicacion = _av(a, "Reubicacion Equipos De Medida")
    if reubicacion != "N/A": lines.append(f"  Reubicacion equipos: {reubicacion}\n")

    frontera = _av(a, "Es Frontera Comercial")
    if frontera != "N/A": lines.append(f"  Frontera comercial: {frontera}\n")

    seccionamientos = _av(a, "Existen Seccionamientos Externos")
    if seccionamientos != "N/A": lines.append(f"  Seccionamientos externos: {seccionamientos}\n")

    # Trafo
    info_trafo = _av(a, "Info Trafo")
    if info_trafo != "N/A" and info_trafo.startswith("["):
        info_trafo = "Ver datos trafo en sistema"
    if info_trafo != "N/A": lines.append(f"  Info trafo: {info_trafo}\n")

    cap_inst = _av(a, "Capacidad Instalada")
    if cap_inst != "N/A": lines.append(f"  Capacidad instalada: {cap_inst}\n")

    equipos = _av(a, "Equipos Necesarios")
    if equipos != "N/A": lines.append(f"  Equipos necesarios: {equipos}\n")

    pb     = _av(a, "Calculo De Pb")
    pb_val = _av(a, "Valor De Pb Calculado")
    if pb != "N/A" or pb_val != "N/A":
        lines.append(f"  Calculo PB: {pb}" + (f" | Valor: {pb_val}" if pb_val != "N/A" else "") + "\n")

    enlace = _av(a, "Enlace Memoria De Calculo")
    if enlace != "N/A" and enlace.startswith("http"):
        lines.append(f"  Enlace calculo: {enlace}\n")

    obs = _av(a, "Observaciones")
    if obs != "N/A":
        obs_short = obs[:200] + "..." if len(obs) > 200 else obs
        lines.append(f"  *Observaciones ing.:* {obs_short}\n")

    reqs = _av(a, "Requerimientos")
    if reqs != "N/A":
        reqs_short = reqs[:200] + "..." if len(reqs) > 200 else reqs
        lines.append(f"  *Requerimientos:* {reqs_short}\n")

    reqs_add = _av(a, "Requerimientos Adicionales Viabilidad")
    if reqs_add != "N/A":
        lines.append(f"  *Reqs adicionales:* {reqs_add}\n")

    return "".join(lines)

def _comparar_visita_vs_alcance(qa_o_vp, alcance_row):
    """Compare visita previa PDF findings vs engineering alcance."""
    if not alcance_row:
        return ""

    lines = ["\n*Comparacion Visita Previa vs Alcance ingenieria*\n"]
    tuvo_comparacion = False

    # Tipo de medida encontrado
    tipo_vp  = (qa_o_vp.get("tipo_medida") or "").strip().upper()
    tipo_alc = (_av(alcance_row, "Tipo De Medida Encontrado") or "").strip().upper()
    if tipo_vp and tipo_alc and tipo_alc != "N/A":
        ok = tipo_vp == tipo_alc
        lines.append(f"  Tipo medida encontrada: PDF={tipo_vp} | Alcance={tipo_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Factor de medida
    factor_vp  = _v(qa_o_vp.get("factor_medida"), "")
    factor_alc = _av(alcance_row, "Factor De Medida Encontrado")
    if factor_vp and factor_vp != "N/A" and factor_alc != "N/A":
        try:
            ok = abs(float(str(factor_vp).replace(",", ".")) - float(str(factor_alc).replace(",", "."))) < 1
        except Exception:
            ok = _normalizar_serial(factor_vp) == _normalizar_serial(factor_alc)
        lines.append(f"  Factor de medida: PDF={factor_vp} | Alcance={factor_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Serie medidor encontrado
    med_enc    = qa_o_vp.get("medidor_encontrado")
    serie_vp   = ""
    if isinstance(med_enc, dict):
        serie_vp = (med_enc.get("serie") or "").strip()
    elif isinstance(qa_o_vp.get("medidor_enc_serie"), str):
        serie_vp = qa_o_vp.get("medidor_enc_serie", "")
    serie_alc = _av(alcance_row, "Serie Del Medidor")
    if serie_vp and serie_alc != "N/A":
        ok = _normalizar_serial(serie_vp) == _normalizar_serial(serie_alc)
        lines.append(f"  Serie medidor encontrado: PDF={serie_vp} | Alcance={serie_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Alertas de alcance
    viable = _av(alcance_row, "Viable Para Instalar")
    if not _viable_ok(viable):
        lines.append(f"  ❌ Ingenieria determino: NO viable para instalar\n")
        tuvo_comparacion = True

    descargos = _av(alcance_row, "Requiere Descargos Del Or")
    if _viable_ok(descargos):
        lines.append(f"  ⚠️ Requiere descargos del OR — coordinar con operador de red\n")
        tuvo_comparacion = True

    antena = _av(alcance_row, "Requiere Antena De Alta Ganancia")
    if _viable_ok(antena):
        oper = _av(alcance_row, "Operador De Red Celular")
        lines.append(f"  ⚠️ Requiere antena de alta ganancia" +
                     (f" | Operador: {oper}" if oper != "N/A" else "") + "\n")
        tuvo_comparacion = True

    return "".join(lines) if tuvo_comparacion else ""

# --- Constructores de cuerpo Slack ---

def _construir_cuerpo_visita_previa(acta, qa, encabezado):
    es_exitosa = qa.get("estado_ot") == "EXITOSA"
    falla = qa.get("tipificacion_falla") or {}

    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida encontrada:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n",
        _seccion_tecnico(qa),
        _seccion_observacion_tecnico(qa),
        "\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado"), qa.get("sellos_medidor_encontrado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_tcs_encontrados(qa.get("tcs_encontrados"), qa.get("sellos_tcs_encontrados")),
        _seccion_tps_encontrados(qa.get("tps_encontrados"), qa.get("sellos_tps_encontrados")),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_encontrado")),
        _seccion_cable_control(qa.get("cable_control_encontrado")),
        _seccion_pruebas(qa.get("pruebas_funcionamiento")),
        _seccion_equipo_patron(qa.get("equipo_patron")),
        f"*Diagrama unifilar:* {'Foto presente' if (qa.get('diagrama_unifilar') or {}).get('tiene_foto') else 'Sin foto'}\n",
        f"*Con OR:* {_v(qa.get('or_firma'))}\n",
    ]

    if not es_exitosa and falla.get("causa_raiz"):
        secciones += [
            f"\n*Tipificacion de la OT fallida*\n",
            f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n",
            f"*Responsable:* {_v(falla.get('responsable'))}\n",
            f"*Detalle:* {_v(falla.get('detalle'))}\n",
            f"*Mejora:* {_v(falla.get('mejora'))}\n",
        ]

    alertas = qa.get("alertas_qa") or []
    if alertas:
        secciones.append("\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas) + "\n")

    return "".join(s for s in secciones if s)

def _construir_cuerpo_exitosa(acta, qa, encabezado, serial_wms_asignado=""):
    coincide_wms = qa.get("medidor_coincide_wms")
    tcs_wms  = qa.get("tcs_wms_asignados") or []
    tps_wms  = qa.get("tps_wms_asignados") or []
    fotos_med = qa.get("fotos_medidor")
    fotos_tcs = qa.get("fotos_tcs")
    fotos_tps = qa.get("fotos_tps")
    sellos_med_enc  = qa.get("sellos_medidor_encontrado")
    sellos_med_inst = qa.get("sellos_medidor_instalado")
    sellos_tcs_enc  = qa.get("sellos_tcs_encontrados")
    sellos_tcs_inst = qa.get("sellos_tcs_instalados")
    sellos_tps_enc  = qa.get("sellos_tps_encontrados")
    sellos_tps_inst = qa.get("sellos_tps_instalados")
    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n",
        _seccion_tecnico(qa),
        _seccion_observacion_tecnico(qa),
        "\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado"), sellos_med_enc),
        _seccion_medidor_instalado(qa.get("medidor_instalado"), coincide_wms, serial_wms_asignado, fotos_med, sellos_med_inst),
        _seccion_medidor_respaldo(qa.get("medidor_respaldo_instalado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_telemedida_instalada(qa.get("telemedida_instalada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_totalizador_instalado(qa.get("totalizador_instalado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_cables_inst(qa.get("cables_potencia_instalados")),
        _seccion_tcs_encontrados(qa.get("tcs_encontrados"), sellos_tcs_enc),
        _seccion_tc_tp_instalados("TCs instalados", qa.get("tcs_instalados"), tcs_wms, qa.get("tcs_coinciden_wms"), fotos_tcs, sellos_tcs_inst),
        _seccion_tps_encontrados(qa.get("tps_encontrados"), sellos_tps_enc),
        _seccion_tc_tp_instalados("TPs instalados", qa.get("tps_instalados"), tps_wms, qa.get("tps_coinciden_wms"), fotos_tps, sellos_tps_inst),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_encontrado")),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_instalado"), instalado=True),
        _seccion_cable_control(qa.get("cable_control_encontrado")),
        _seccion_cable_control(qa.get("cable_control_instalado"), instalado=True),
        _seccion_pruebas(qa.get("pruebas_funcionamiento")),
        _seccion_equipo_patron(qa.get("equipo_patron")),
        f"*Diagrama unifilar:* {'Foto presente' if (qa.get('diagrama_unifilar') or {}).get('tiene_foto') else 'Sin foto'}\n",
        f"*Con OR:* {_v(qa.get('or_firma'))}\n\n",
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
        + _seccion_tecnico(qa)
        + _seccion_observacion_tecnico(qa)
        + "\n"
        + f"*Tipificacion de la OT fallida*\n"
        f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n"
        f"*Responsable:* {_v(falla.get('responsable'))}\n"
        f"*Detalle:* {_v(falla.get('detalle'))}\n"
        f"*Mejora:* {_v(falla.get('mejora'))}\n"
    )

# =============================================================
#  SLACK ENVIOS
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
    es_visita  = "previa" in (acta.get("Tipo de servicio") or "").lower()
    color      = "#2eb886" if es_exitosa else "#e01e5a"
    if es_visita:
        color = "#0066cc"
    estado_txt = "EXITOSA" if es_exitosa else "FALLIDA"
    planner    = resultado_qa.get("planner", "N/A")
    or_norm    = resultado_qa.get("or_norm", acta.get("OR_NORM", "N/A"))

    user_ids = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id = user_ids.get(planner)
    if slack_id:
        encabezado = f"<@{slack_id}>\n\n"
    else:
        encabezado = f"*{planner}*\n\n"

    if es_visita:
        cuerpo = _construir_cuerpo_visita_previa(acta, resultado_qa, encabezado)
    elif es_exitosa:
        cuerpo = _construir_cuerpo_exitosa(acta, resultado_qa, encabezado, serial_wms_asignado)
    else:
        cuerpo = _construir_cuerpo_fallida(acta, resultado_qa, encabezado)

    if len(cuerpo) > 7800:
        cuerpo = cuerpo[:7800] + "\n... (truncado)"

    tipo_titulo = "VISITA PREVIA" if es_visita else estado_txt
    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{tipo_titulo}] {acta.get('title', 'Sin titulo')}",
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

def enviar_slack_alcance(co_code, alcance_row, visita_data):
    """Send Slack notification when a new engineering alcance is generated."""
    url = (config.SLACK_WEBHOOK_URL or "").strip().strip('"').strip("'")
    if not url or not url.startswith("https://"):
        return

    planner  = config.PLANNER_DEFAULT
    user_ids = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id = user_ids.get(planner)
    encabezado = f"<@{slack_id}>\n\n" if slack_id else f"*{planner}*\n\n"

    ot_ref = (visita_data or {}).get("ot_nombre", "")

    cuerpo = (
        encabezado
        + f"*Codigo interno Bia:* {co_code}\n"
        + (f"*OT Visita Previa relacionada:* {ot_ref}\n" if ot_ref else "")
        + "\n"
        + _seccion_alcance_ingenieria(alcance_row)
        + (_comparar_visita_vs_alcance(visita_data, alcance_row) if visita_data else "")
    )

    if len(cuerpo) > 7800:
        cuerpo = cuerpo[:7800] + "\n... (truncado)"

    viable = _av(alcance_row, "Viable Para Instalar")
    medida_inst = _av(alcance_row, "Tipo De Medida A Instalar")
    fecha_alc   = _av(alcance_row, "Creado El")[:10]

    payload = {
        "attachments": [{
            "color": "#9b59b6",
            "title": f"[ALCANCE INGENIERIA] {co_code}",
            "fields": [
                {"title": "Medida a instalar", "value": medida_inst, "short": True},
                {"title": "Viable",            "value": viable,      "short": True},
                {"title": "Fecha alcance",     "value": fecha_alc,   "short": True},
                {"title": "VP registrada",     "value": "Si" if visita_data else "No", "short": True},
            ],
            "text":      cuerpo,
            "mrkdwn_in": ["text"],
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"  Slack alcance enviado: {co_code}")
        else:
            print(f"  ERROR Slack alcance: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ERROR Slack alcance: {e}")

def verificar_nuevos_alcances(alcances, visitas_previas_dict):
    """Check alcances CSV for new entries and notify Slack."""
    procesados   = cargar_alcances_procesados()
    fecha_inicio = date.fromisoformat(getattr(config, "FECHA_INICIO_ALCANCES", "2026-05-02"))
    nuevos       = 0

    for co_code, alcance_row in alcances.items():
        alcance_id = alcance_row.get("ID", "").strip()
        if not alcance_id or alcance_id in procesados:
            continue

        fecha_str = alcance_row.get("Creado El", "").strip()
        try:
            if date.fromisoformat(fecha_str[:10]) < fecha_inicio:
                continue
        except Exception:
            continue

        visita_data = visitas_previas_dict.get(co_code)
        print(f"\n  -> Nuevo alcance: {co_code} (VP almacenada: {'Si' if visita_data else 'No'})")
        if not getattr(config, "MODO_BACKFILL", False):
            enviar_slack_alcance(co_code, alcance_row, visita_data)
        actualizar_supabase_alcance(co_code, alcance_row)
        guardar_alcance_procesado(alcance_id)
        nuevos += 1
        if nuevos < 10:
            time.sleep(2)

    if nuevos == 0:
        print("  Sin nuevos alcances de ingenieria.")
    else:
        print(f"  {nuevos} alcance(s) nuevo(s) notificado(s).")

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

def _supabase_base_url():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")]
    return url

def enviar_supabase(acta, resultado_qa, alcance_row=None):
    url = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    if not url or not key:
        return

    med_enc  = resultado_qa.get("medidor_encontrado") or {}
    med_inst = resultado_qa.get("medidor_instalado") or {}
    tcs_enc  = resultado_qa.get("tcs_encontrados") or {}
    tps_enc  = resultado_qa.get("tps_encontrados") or {}
    val      = resultado_qa.get("validaciones") or {}
    falla    = resultado_qa.get("tipificacion_falla") or {}

    registro = {
        "procesado_en":              datetime.utcnow().isoformat() + "Z",
        "ot_nombre":                 acta.get("title"),
        "ot_id":                     acta.get("id"),
        "tipo_servicio":             acta.get("Tipo de servicio"),
        "estado_ot":                 resultado_qa.get("estado_ot"),
        "fecha_ejecucion":           acta.get("start"),
        "internal_bia_code":         acta.get("internal_bia_code"),
        "or_norm":                   acta.get("OR_NORM"),
        "planner":                   resultado_qa.get("planner"),
        "empresa":                   acta.get("company_name"),
        "direccion":                 acta.get("address"),
        "tipo_medida":               resultado_qa.get("tipo_medida"),
        "factor_medida":             str(resultado_qa.get("factor_medida") or ""),
        "tecnico_nombre":            resultado_qa.get("tecnico_nombre"),
        "tecnico_empresa":           resultado_qa.get("tecnico_empresa"),
        "contratista_nombre":        resultado_qa.get("contratista_nombre"),
        "medidor_encontrado_serie":  med_enc.get("serie"),
        "medidor_encontrado_marca":  med_enc.get("marca"),
        "medidor_instalado_serie":   med_inst.get("serie"),
        "medidor_instalado_marca":   med_inst.get("marca"),
        "medidor_coincide_wms":      resultado_qa.get("medidor_coincide_wms"),
        "tcs_coinciden_wms":         resultado_qa.get("tcs_coinciden_wms"),
        "tps_coinciden_wms":         resultado_qa.get("tps_coinciden_wms"),
        "sellos_medidor_encontrado": resultado_qa.get("sellos_medidor_encontrado"),
        "sellos_medidor_instalado":  resultado_qa.get("sellos_medidor_instalado"),
        "sellos_tcs_encontrados":    resultado_qa.get("sellos_tcs_encontrados"),
        "sellos_tcs_instalados":     resultado_qa.get("sellos_tcs_instalados"),
        "tiene_tcs":                 bool(tcs_enc.get("aplica") and tcs_enc.get("tiene")),
        "tiene_tps":                 bool(tps_enc.get("aplica") and tps_enc.get("tiene")),
        "tiene_telemedida":          bool((resultado_qa.get("telemedida_encontrada") or {}).get("tiene")),
        "tiene_diagrama_unifilar":   bool((resultado_qa.get("diagrama_unifilar") or {}).get("tiene_foto")),
        "or_firma":                  resultado_qa.get("or_firma"),
        "validacion_coherente":      val.get("coherencia"),
        "errores_qa":                val.get("errores_encontrados") or [],
        "alertas_qa":                resultado_qa.get("alertas_qa") or [],
        "tipificacion_causa_raiz":   falla.get("causa_raiz"),
        "tipificacion_responsable":  falla.get("responsable"),
        "wms_asignado":              bool(resultado_qa.get("wms_asignado")),
        "wms_medidor_serial":        resultado_qa.get("medidor_wms_asignado"),
        "wms_medidor_marca":         resultado_qa.get("medidor_wms_marca"),
        "wms_completo":              resultado_qa.get("wms_completo"),
        "wms_marca_coincide_alcance": resultado_qa.get("wms_marca_coincide_alcance"),
        "serial_medidor_factura_anterior":   resultado_qa.get("serial_medidor_factura_anterior"),
        "medidor_coincide_factura_anterior": resultado_qa.get("medidor_coincide_factura_anterior"),
        "factura_anterior_express":          resultado_qa.get("factura_anterior_express"),
        "tiene_alcance":             alcance_row is not None,
        "alcance_viable":            _av(alcance_row, "Viable Para Instalar") if alcance_row else None,
        "alcance_medida_instalar":   _av(alcance_row, "Tipo De Medida A Instalar") if alcance_row else None,
        "alcance_completo":          dict(alcance_row) if alcance_row else None,
        "resultado_qa_completo":     resultado_qa,
    }

    try:
        r = requests.post(
            f"{url}/rest/v1/actas_qa?on_conflict=ot_id",
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "resolution=merge-duplicates,return=minimal",
            },
            json=registro,
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            print("  Supabase: registro guardado.")
        else:
            print(f"  ERROR Supabase: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Supabase: {e}")

def actualizar_supabase_alcance(co_code, alcance_row):
    url = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    if not url or not key:
        return

    body = {
        "tiene_alcance":           True,
        "alcance_viable":          _av(alcance_row, "Viable Para Instalar"),
        "alcance_medida_instalar": _av(alcance_row, "Tipo De Medida A Instalar"),
        "alcance_completo":        dict(alcance_row),
    }
    try:
        r = requests.patch(
            f"{url}/rest/v1/actas_qa",
            params={
                "internal_bia_code": f"eq.{co_code}",
                "tipo_servicio":     "eq.Visita previa",
            },
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/json",
                "Prefer":        "return=minimal",
            },
            json=body,
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            print(f"  Supabase: VIPE {co_code} marcada con alcance.")
        else:
            print(f"  ERROR Supabase alcance: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Supabase alcance: {e}")

# =============================================================
#  PROCESAR UNA ACTA
# =============================================================

def procesar_acta(acta, wms, alcances=None, facturas=None):
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

    texto_pdf, imagenes_pdf = descargar_y_leer_pdf(pdf_url)
    if not texto_pdf:
        print("     No se pudo leer el PDF. Se omite.")
        return False

    modelos_log = ", ".join(getattr(config, "GEMINI_MODELS", [config.GEMINI_MODEL]))
    print(f"     Analizando con Gemini (chain: {modelos_log}) | imagenes: {len(imagenes_pdf)}")
    resultado_qa = analizar_acta(
        texto_pdf, tipo, estado, internal_bia_code,
        serial_asignado if debe_comparar_wms else "",
        marca_asignada if debe_comparar_wms else "",
        tcs_asignados if debe_comparar_wms else [],
        tps_asignados if debe_comparar_wms else [],
        imagenes_pdf=imagenes_pdf,
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
    _limpiar_errores_fantasma(resultado_qa, tipo)
    _override_fallida_si_incompleto(resultado_qa)
    _simplificar_fallida(resultado_qa)

    resultado_qa["planner"]              = planner
    resultado_qa["or_norm"]              = or_norm
    resultado_qa["internal_bia_code"]    = internal_bia_code
    # WMS: serial + marca + objeto completo para que el dashboard muestre todo
    resultado_qa["medidor_wms_asignado"] = serial_asignado or None
    resultado_qa["medidor_wms_marca"]    = marca_asignada or None
    resultado_qa["tcs_wms_asignados"]    = tcs_asignados or []
    resultado_qa["tps_wms_asignados"]    = tps_asignados or []
    resultado_qa["wms_asignado"]         = bool(serial_asignado)
    resultado_qa["wms_completo"]         = entry_wms or None  # dict con medidor/tcs/tps completo

    # Tecnico y contratista: fuente de verdad es el CSV de Metabase, no la IA.
    # contractor_name = "BIA" (literal) -> empleado BIA Energy.
    # contractor_name = otro valor       -> contratista, nombre = ese valor.
    # contractor_name = vacio            -> desconocido (NO mentir que es BIA).
    csv_tecnico     = (acta.get("Electrician Visits__name") or "").strip()
    csv_contratista = (acta.get("contractor_name") or "").strip()
    if csv_tecnico:
        resultado_qa["tecnico_nombre"] = csv_tecnico
    if not csv_contratista:
        resultado_qa["tecnico_empresa"]    = None
        resultado_qa["contratista_nombre"] = None
    elif csv_contratista.upper() == "BIA":
        resultado_qa["tecnico_empresa"]    = "BIA"
        resultado_qa["contratista_nombre"] = None
    else:
        resultado_qa["tecnico_empresa"]    = "CONTRATISTA"
        resultado_qa["contratista_nombre"] = csv_contratista

    # Comparacion WMS marca vs alcance marca (si ambos disponibles)
    alc = (alcances or {}).get(internal_bia_code)
    alc_marca = ((alc or {}).get("Marca Del Medidor") or "").strip()
    if marca_asignada and alc_marca and alc_marca.upper() not in ("N/A", "-"):
        resultado_qa["wms_marca_coincide_alcance"] = (
            marca_asignada.strip().upper() == alc_marca.upper()
        )
    else:
        resultado_qa["wms_marca_coincide_alcance"] = None

    # Factura anterior: extraer serial + flag express del comercializador previo
    serial_factura  = None
    factura_express = None
    factura_url     = (facturas or {}).get(internal_bia_code)
    if factura_url:
        cache = _cargar_facturas_extraidas()
        if internal_bia_code in cache:
            entry = cache[internal_bia_code] or {}
            serial_factura  = entry.get("serial")
            factura_express = entry.get("express")
        else:
            print(f"     Extrayendo medidor de factura anterior para {internal_bia_code}...")
            data, estado = extraer_serial_factura(factura_url)
            if data:
                serial_factura  = data.get("serial")
                factura_express = data.get("express")
            _guardar_factura_extraida(internal_bia_code, {
                "serial":  serial_factura,
                "express": factura_express,
                "url":     factura_url,
                "estado":  estado,
                "fecha":   ahora(),
            })
            print(f"     Factura anterior: serial={serial_factura} express={factura_express} ({estado})")
    resultado_qa["serial_medidor_factura_anterior"] = serial_factura
    resultado_qa["factura_anterior_express"]        = factura_express
    serial_acta = ((resultado_qa.get("medidor_encontrado") or {}).get("serie") or "").strip()
    if serial_factura and serial_acta:
        resultado_qa["medidor_coincide_factura_anterior"] = (
            _normalizar_serial(serial_factura) == _normalizar_serial(serial_acta)
        )
    else:
        resultado_qa["medidor_coincide_factura_anterior"] = None


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

    # Guardar hallazgos de visita previa para comparacion futura con alcance
    if es_visita and internal_bia_code:
        vp_data = {
            "ot_nombre":                   ot_nombre,
            "fecha_procesada":             ahora(),
            "tipo_medida":                 resultado_qa.get("tipo_medida"),
            "factor_medida":               resultado_qa.get("factor_medida"),
            "medidor_encontrado":          resultado_qa.get("medidor_encontrado"),
            "medidor_enc_serie":           (resultado_qa.get("medidor_encontrado") or {}).get("serie"),
            "tcs_encontrados":             resultado_qa.get("tcs_encontrados"),
            "tps_encontrados":             resultado_qa.get("tps_encontrados"),
            "tecnico_nombre":              resultado_qa.get("tecnico_nombre"),
            "tecnico_empresa":             resultado_qa.get("tecnico_empresa"),
            "contratista_nombre":          resultado_qa.get("contratista_nombre"),
            "observacion_tecnico_verbatim": resultado_qa.get("observacion_tecnico_verbatim"),
        }
        guardar_visita_previa(internal_bia_code, vp_data)

        # Si ya existe un alcance para este CO, enviarlo inmediatamente
        if alcances:
            alcance_row = alcances.get(internal_bia_code)
            if alcance_row:
                alcance_id = alcance_row.get("ID", "").strip()
                procesados_alc = cargar_alcances_procesados()
                if alcance_id and alcance_id not in procesados_alc:
                    print(f"     Alcance encontrado para {internal_bia_code} — enviando al Slack...")
                    if not getattr(config, "MODO_BACKFILL", False):
                        enviar_slack_alcance(internal_bia_code, alcance_row, vp_data)
                    guardar_alcance_procesado(alcance_id)

    backfill = getattr(config, "MODO_BACKFILL", False)
    guardar_reporte(acta, resultado_qa)
    if not backfill:
        enviar_slack(acta, resultado_qa, serial_asignado if debe_comparar_wms else "")
    enviar_supabase(acta, resultado_qa, alcances.get(internal_bia_code) if alcances else None)
    if not backfill:
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
    print("   SISTEMA QA BIA ENERGY  -  Motor: Google Gemini")
    print("   Modo: " + modo)
    print("=" * 58)
    print("   Fecha inicio : " + config.FECHA_INICIO)
    print("   Pausa        : " + str(config.PAUSA_GROQ_SEGUNDOS) + "s entre actas")
    if config.MODO_PRUEBA:
        print("   Actas prueba : " + str(config.ACTAS_PRUEBA))
    print("=" * 58)

    print("\n  Cargando inventario WMS...")
    wms = cargar_inventario_wms()

    print("\n  Cargando alcances de ingenieria...")
    alcances = cargar_alcances()

    print("\n  Cargando facturas anteriores (HubSpot vía Metabase)...")
    facturas = cargar_facturas_anteriores()

    if config.MODO_PRUEBA:
        print("")
        actas = obtener_actas_nuevas()
        procesadas = 0
        for i, acta in enumerate(actas):
            if procesar_acta(acta, wms, alcances, facturas):
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
                procesar_acta(acta, wms, alcances, facturas)
                if i < len(actas) - 1:
                    time.sleep(config.PAUSA_GROQ_SEGUNDOS)
        else:
            print("[" + ahora() + "] Sin actas nuevas.")

        print(f"\n[{ahora()}] Verificando nuevos alcances de ingenieria...")
        visitas_previas_dict = cargar_visitas_previas()
        verificar_nuevos_alcances(alcances, visitas_previas_dict)

        if not getattr(config, 'MODO_UNICO', False):
            while True:
                time.sleep(config.INTERVALO_SEGUNDOS)
                wms      = cargar_inventario_wms()
                alcances = cargar_alcances()
                facturas = cargar_facturas_anteriores()
                actas    = obtener_actas_nuevas()
                if actas:
                    for i, acta in enumerate(actas):
                        procesar_acta(acta, wms, alcances, facturas)
                        if i < len(actas) - 1:
                            time.sleep(config.PAUSA_GROQ_SEGUNDOS)
                else:
                    print("[" + ahora() + "] Sin actas nuevas. Revisando en " + str(config.INTERVALO_SEGUNDOS) + "s...")
                visitas_previas_dict = cargar_visitas_previas()
                verificar_nuevos_alcances(alcances, visitas_previas_dict)

if __name__ == "__main__":
    main()
