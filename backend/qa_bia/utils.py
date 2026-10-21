"""Utilidades compartidas sin dependencias de negocio.
"""
import re
from datetime import datetime, timezone


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ahora_utc():
    """Hora UTC sin zona (reemplaza a datetime.utcnow(), deprecado en Python 3.12)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ahora_utc_iso():
    """Hora UTC en ISO con sufijo Z, ej. 2026-05-21T10:00:00.123456Z."""
    return ahora_utc().isoformat() + "Z"


def _normalizar_serial(s):
    if not s:
        return ""
    return re.sub(r"[\s\-_/]", "", str(s)).lstrip("0").upper()


def _av(fila, *cols):
    """Get first non-empty value from alcance CSV row."""
    for col in cols:
        v = (fila.get(col) or "").strip()
        if v and v not in ("-", "N/A", "n/a", "nan"):
            return v
    return "N/A"
