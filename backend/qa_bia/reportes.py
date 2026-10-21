"""Reportes JSON locales por acta (carpeta reportes_qa/, no se versiona).
"""
import os
import json
from datetime import datetime

from . import config


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
