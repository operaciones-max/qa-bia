"""Extraccion del serial del medidor desde la factura anterior (regex + Claude).
"""
import io
import re
import requests
import pdfplumber

from . import config
from .estado import _activar_cooldown_llm, _cargar_cooldown_llm
from .ia import cliente_claude, es_limite_de_uso, extraer_json


# Patrones de extraccion de serial de medidor por OR/comercializador.
# Aprendidos del usuario el 2026-05-15. Se prueban en orden — la primera
# coincidencia gana. Captura grupos: \1 = serial (alfanumerico 4-20 chars).
SERIAL_PATTERNS = [
    (r'No\.\s*Medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'Enel'),
    (r'N[úu]mero\s+de\s+Medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'Air-e/Aire'),
    (r'Medidor\s+No\.?\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'Enel X'),
    (r'C[óo]digo\s+(?:del\s+)?medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'ERCO'),
    (r'Medidor\s+Activa\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'CENS'),
    (r'\bMedidor\s*\n\s*([0-9][0-9A-Z\-]{3,19})', 'Celsia (cuadro naranja)'),
    (r'\bMedidor\s*:\s*([0-9A-Z][0-9A-Z\-]{3,19})', 'EPM/generico'),
]


def _limpiar_serial_extraido(s):
    """Quita sufijos tipo '-MC983', '-MCA01', '-V2' que son codigos de
    version/modelo, no parte del serial real del medidor."""
    if not s:
        return s
    return re.sub(r'-[A-Z][A-Z0-9]*$', '', s).strip()


def _extraer_serial_contextual(texto, ancla_regex, serial_regex, ventana=800):
    """Busca un ancla en el texto (ej. 'Datos de la Factura') y luego busca
    el serial dentro de los siguientes 'ventana' caracteres. Devuelve serial o None."""
    m = re.search(ancla_regex, texto, re.IGNORECASE)
    if not m:
        return None
    seccion = texto[m.end():m.end() + ventana]
    m2 = re.search(serial_regex, seccion, re.IGNORECASE)
    if m2:
        s = _limpiar_serial_extraido(m2.group(1).strip().upper())
        if s and any(c.isdigit() for c in s):
            return s
    return None


def extraer_serial_por_patron(texto):
    """Intenta extraer el serial del medidor con patrones segun OR/comercializador.
    1ro intenta patrones CONTEXTUALES (ancla + serial cerca).
    Luego cae a patrones LINEALES (regex en todo el texto).
    Devuelve (serial, patron_usado) o (None, None)."""
    if not texto:
        return None, None

    # Patrones contextuales (anchor-based) — ganan sobre los lineales
    # AFINIA: el serial esta dentro del recuadro 'Datos de la Factura'
    afinia_serial = _extraer_serial_contextual(
        texto,
        ancla_regex=r'Datos\s+de\s+la\s+Factura',
        serial_regex=r'Medidor\s*[:\n]?\s*([0-9][0-9A-Z\-]{3,19})',
        ventana=800,
    )
    if afinia_serial:
        return afinia_serial, 'AFINIA (Datos de la Factura)'

    # Patrones lineales por comercializador
    for pattern, nombre_or in SERIAL_PATTERNS:
        m = re.search(pattern, texto, re.IGNORECASE)
        if m:
            serial = _limpiar_serial_extraido(m.group(1).strip().upper())
            if serial and any(c.isdigit() for c in serial):
                return serial, nombre_or
    return None, None


def extraer_serial_factura(pdf_url):
    """Descarga PDF de factura y extrae el numero de medidor + flag express.
    Primero intenta regex por patron de OR (Enel/Aire/Celsia/etc). Si falla,
    cae al LLM. Devuelve (data_dict, estado) donde data_dict={serial, express}."""
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

    # Deteccion express ANTES de Claude — basta con buscar la palabra
    express = "express" in texto.lower()

    # 1er intento: regex por patron de OR (gratis, sin tokens)
    serial_regex, patron = extraer_serial_por_patron(texto)
    if serial_regex:
        print(f"     Serial extraido por regex ({patron}): {serial_regex}")
        return {"serial": serial_regex, "express": express}, f"regex_{patron}"

    # 2do intento: Claude (si regex falla)
    cd = _cargar_cooldown_llm()
    if cd:
        return {"serial": None, "express": express}, "cooldown"

    prompt = (
        "Factura electrica colombiana. Extrae el serial del medidor.\n\n"
        "Patrones conocidos por comercializador:\n"
        "- Enel: 'No. Medidor: XXXX'\n"
        "- Air-e/Aire: 'Número de Medidor: XXXX'\n"
        "- Enel X: 'Medidor No: XXXX'\n"
        "- ERCO: 'Código medidor: XXXX'\n"
        "- Celsia: cuadro 'Medidor' con numero abajo\n"
        "- EPM: 'medidor' junto al cuadro de consumos\n"
        "- CENS: 'Medidor Activa: XXXX'\n\n"
        "Si no aparece serial reconocible, devuelve null.\n"
        "JSON estricto: {\"serial\": \"<num>\" o null}\n\n"
        + texto[:3500]
    )

    try:
        respuesta = cliente_claude().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=80,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        texto_r = "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()
        data = extraer_json(texto_r)
        serial = (data.get("serial") or "").strip() or None
        return {"serial": serial, "express": express}, "ok"
    except Exception as e:
        msg = str(e)
        if es_limite_de_uso(e):
            _activar_cooldown_llm(msg)
            return {"serial": None, "express": express}, "rate_limit"
        return {"serial": None, "express": express}, f"error_claude: {msg[:120]}"
