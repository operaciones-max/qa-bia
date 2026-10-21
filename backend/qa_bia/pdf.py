"""Descarga y lectura de PDFs de actas (texto con pdfplumber, imagenes con PyMuPDF).
"""
import io
import requests
import pdfplumber


MAX_PAGINAS_VISION = 0   # 0 = vision global desactivada en analisis full (PQR/VICO/Emergencia usan vision lite via _renderizar_paginas_pdf, independiente)


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
        # Vision no disponible — Claude analiza solo texto del PDF
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


def _renderizar_paginas_pdf(pdf_bytes, n_paginas=2, dpi=80):
    """Renderiza primeras N paginas del PDF como JPEG bytes. Independiente
    de MAX_PAGINAS_VISION — usar cuando se necesita vision para casos
    especificos (PQR/VICO/Emergencia que tienen actas fisicas)."""
    try:
        import fitz
    except ImportError:
        return []
    imagenes = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        n = min(len(doc), n_paginas)
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            imagenes.append(pix.tobytes("jpeg"))
        doc.close()
    except Exception as e:
        print(f"  WARN: no se pudieron renderizar paginas para vision: {e}")
    return imagenes
