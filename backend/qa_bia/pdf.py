"""Descarga y lectura de PDFs de actas (texto con pdfplumber, imagenes con PyMuPDF).
"""
import io
import requests
import pdfplumber


# Paginas que se mandan como imagen en el QA full. 0 = solo texto (ahorra tokens).
# PQR/VICO/Emergencia usan su propia vision en el QA lite (_renderizar_paginas_pdf).
MAX_PAGINAS_VISION = 0
DPI_VISION         = 60  # resolucion de las imagenes — mas bajo = menos tokens


def descargar_y_leer_pdf(url):
    """Devuelve (texto, lista_de_imagenes_jpeg_bytes, pdf_bytes).
    Si falla: (None, [], None)."""
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

        imagenes = _renderizar_paginas_pdf(pdf_bytes, n_paginas=MAX_PAGINAS_VISION, dpi=DPI_VISION)
        texto_final = texto.strip() if texto.strip() else None
        return texto_final, imagenes, pdf_bytes
    except Exception as e:
        print(f"  ERROR leyendo PDF: {e}")
        return None, [], None


def _renderizar_paginas_pdf(pdf_bytes, n_paginas=2, dpi=80):
    """Renderiza las primeras N paginas del PDF como JPEG bytes."""
    if not n_paginas:
        return []
    try:
        import pymupdf
    except ImportError:
        # Vision no disponible — Claude analiza solo texto del PDF
        return []
    imagenes = []
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        n = min(len(doc), n_paginas)
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            imagenes.append(pix.tobytes("jpeg"))
        doc.close()
    except Exception as e:
        print(f"  WARN: no se pudieron renderizar paginas para vision: {e}")
    return imagenes
