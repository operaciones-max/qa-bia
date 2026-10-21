"""Utilidades compartidas sin dependencias de negocio.
"""
import re
from datetime import datetime


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
