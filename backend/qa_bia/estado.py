"""Estado persistente en archivos JSON (actas procesadas, visitas previas,
alcances procesados, cache de facturas y cooldown del LLM).

Las rutas vienen de config.py (por defecto backend/state/).
"""
import os
import json
import re
from datetime import datetime, timedelta

from . import config
from .utils import ahora_utc


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


ARCHIVO_COOLDOWN_LLM = config.ARCHIVO_COOLDOWN_LLM


def _cargar_cooldown_llm():
    if not os.path.exists(ARCHIVO_COOLDOWN_LLM):
        return None
    try:
        with open(ARCHIVO_COOLDOWN_LLM, "r", encoding="utf-8") as f:
            data = json.load(f)
        if ahora_utc() >= datetime.fromisoformat(data["until"].replace("Z", "")):
            os.remove(ARCHIVO_COOLDOWN_LLM)
            return None
        return data
    except Exception:
        return None


def _activar_cooldown_llm(msg_error):
    print(f"  [cooldown] Error original Claude: {msg_error[:400]}")
    msg = msg_error.lower()
    es_diario = ("per day" in msg or "tokens per day" in msg or "requests per day" in msg)
    if es_diario:
        until = ahora_utc().replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)
        razon = "daily_quota"
    else:
        m = re.search(r"(?:try again in|retry.*?in|retry_delay.*?seconds:)\s*(\d+\.?\d*)", msg_error)
        segundos = int(float(m.group(1))) + 5 if m else 65
        until = ahora_utc() + timedelta(seconds=segundos)
        razon = "per_minute"
    data = {
        "until":   until.isoformat(timespec="seconds") + "Z",
        "razon":   razon,
        "activado": ahora_utc().isoformat(timespec="seconds") + "Z",
    }
    with open(ARCHIVO_COOLDOWN_LLM, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


ARCHIVO_FACTURAS_EXTRAIDAS = config.ARCHIVO_FACTURAS_EXTRAIDAS


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
