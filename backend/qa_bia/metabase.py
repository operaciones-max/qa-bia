"""Fuentes de datos: lectura de Metabase (actas, inventario WMS, alcances de
ingenieria, facturas anteriores via HubSpot y estado de cierre de App Ops).
"""
import os
import csv
import io
import requests
from datetime import date

from . import config
from .utils import ahora
from .estado import cargar_procesados


METABASE_BASE = "https://bia.metabaseapp.com"


METABASE_QUESTION_FACTURAS = 71842  # hubspot-general: trae URL factura + contract_id


def _detectar_columna(columnas, candidatos):
    """Devuelve la primera columna cuyo nombre normalizado matchea algun candidato."""
    norm = {c.lower().strip().replace(" ", "_"): c for c in columnas}
    for cand in candidatos:
        if cand in norm:
            return norm[cand]
    return None


def cargar_facturas_anteriores():
    """Carga del Metabase question 71842 (hubspot-general) las URLs de facturas anteriores
    + contract_id por CO. Devuelve dict {internal_bia_code: {"url": str|None, "contract_id": str|None}}.
    Requiere METABASE_API_KEY env var."""
    api_key = os.environ.get("METABASE_API_KEY", "").strip()
    if not api_key:
        print("  WARN: METABASE_API_KEY no configurada — sin validacion factura anterior")
        return {}
    url = f"{METABASE_BASE}/api/card/{METABASE_QUESTION_FACTURAS}/query/csv"
    print(f"  POST {url} (key: {api_key[:6]}...{api_key[-4:] if len(api_key)>10 else ''})")
    try:
        r = requests.post(url, headers={"X-API-KEY": api_key}, timeout=60)
        ct = r.headers.get("content-type", "")
        print(f"  Status: {r.status_code} | Content-Type: {ct} | size: {len(r.content)} bytes")
        if r.status_code != 200:
            print(f"  Respuesta del servidor: {r.text[:300]}")
            return {}
        if "csv" not in ct and "text/plain" not in ct:
            print(f"  WARN: Content-Type inesperado. Primeros 200 chars: {r.text[:200]}")
        lector = csv.DictReader(io.StringIO(r.content.decode("utf-8")))
        result = {}
        col_code = None
        col_url = None
        col_contract = None
        filas_total = 0
        for fila in lector:
            if col_code is None:
                cols = list(fila.keys())
                print(f"  Columnas CSV: {cols}")
                col_code = _detectar_columna(cols, ["internal_bia_code", "codigo_bia", "bia_code"])
                col_url = _detectar_columna(cols, ["factura_anterior", "invoice_document_url",
                                                    "factura_url", "url_factura", "invoice_url"])
                col_contract = _detectar_columna(cols, ["contract_id", "contractid", "id_contrato"])
                print(f"  Columnas detectadas: code='{col_code}' url='{col_url}' contract_id='{col_contract}'")
                if not col_code:
                    print("  ERROR: no se detecto columna de codigo_bia/internal_bia_code")
                    return {}
            filas_total += 1
            co = (fila.get(col_code) or "").strip()
            if not co:
                continue
            inv = (fila.get(col_url) or "").strip() if col_url else ""
            cid = (fila.get(col_contract) or "").strip() if col_contract else ""
            # Metabase exporta numeros como "17657.0" -> limpiar a "17657"
            if cid.endswith(".0"):
                cid = cid[:-2]
            if co not in result:
                result[co] = {"url": None, "contract_id": None}
            if inv and not result[co]["url"]:
                result[co]["url"] = inv
            if cid and not result[co]["contract_id"]:
                result[co]["contract_id"] = cid
        con_url = sum(1 for v in result.values() if v["url"])
        con_contract = sum(1 for v in result.values() if v["contract_id"])
        print(f"  Hubspot-general: {filas_total} filas | {len(result)} CO unicos | "
              f"{con_url} con URL factura | {con_contract} con contract_id.")
        return result
    except Exception as e:
        print(f"  ERROR cargando facturas anteriores: {e}")
        return {}


METABASE_QUESTION_APP_OPS = 15673  # BD Analisis App Ops: estado de cierre real


def cargar_estado_app_ops():
    """Lee Metabase question 15673 y devuelve dos maps:
      by_id:    {ot_id: electrician_status_id}        <- 1ra opcion, unico por acta
      by_title: {ot_nombre: electrician_status_id}    <- 2da opcion, unico por acta
    NO se usa fallback por internal_bia_code porque mezcla estados de actas
    distintas con mismo CO (varias OTs en una misma cuenta)."""
    api_key = os.environ.get("METABASE_API_KEY", "").strip()
    if not api_key:
        return {}, {}
    url = f"{METABASE_BASE}/api/card/{METABASE_QUESTION_APP_OPS}/query/csv"
    print(f"  POST {url} (key: {api_key[:6]}...{api_key[-4:] if len(api_key)>10 else ''})")
    try:
        r = requests.post(url, headers={"X-API-KEY": api_key}, timeout=60)
        print(f"  Status: {r.status_code} | size: {len(r.content)} bytes")
        if r.status_code != 200:
            return {}, {}
        lector = csv.DictReader(io.StringIO(r.content.decode("utf-8")))
        by_id = {}
        by_title = {}
        col_id = None
        col_title = None
        col_status = None
        first = True
        for fila in lector:
            if first:
                cols = list(fila.keys())
                print(f"  Columnas App Ops (15673): {cols}")
                col_id = _detectar_columna(cols, ["id", "ot_id"])
                col_title = _detectar_columna(cols, ["title", "ot_nombre"])
                col_status = _detectar_columna(cols, ["electrician_status_id", "electrician_status",
                                                       "estado_electricista", "status_id"])
                print(f"  Columnas detectadas: id='{col_id}' title='{col_title}' status='{col_status}'")
                first = False
                if not col_status:
                    print("  ERROR: no se detecto columna de status en 15673")
                    return {}, {}
            status = (fila.get(col_status) or "").strip()
            if not status:
                continue
            if col_id:
                uid = (fila.get(col_id) or "").strip()
                if uid:
                    by_id[uid] = status
            if col_title:
                t = (fila.get(col_title) or "").strip()
                if t:
                    by_title[t] = status
        print(f"  App Ops cargado: {len(by_id)} OTs por ID | {len(by_title)} OTs por Title.")
        return by_id, by_title
    except Exception as e:
        print(f"  ERROR cargando estado app ops: {e}")
        return {}, {}


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

        # Aceptar TODOS los tipos de servicio — el track de QA decide la profundidad de analisis
        if not tipo:
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
