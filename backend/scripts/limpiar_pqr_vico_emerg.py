"""
Script one-shot para reprocesar PQR, VICO y EMERGENCIA con vision habilitada.

Saca esos ot_ids de actas_procesadas.json para que el cron los re-analize con
las primeras 4 paginas del PDF renderizadas como imagenes (vision habilitada
solo para estos tipos en analizar_acta_lite).

Ejecutar desde backend/:  python -m scripts.limpiar_pqr_vico_emerg
"""
import json
import os
import sys
import requests

from qa_bia import config
from qa_bia.supabase import _supabase_base_url

ARCHIVO_PROCESADOS = config.ARCHIVO_PROCESADOS


def main():
    url_base = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    if not url_base or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY requeridos")
        sys.exit(1)

    print("Buscando PQR/VICO/Emergencia para reprocesar con vision...")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    # Tipos que ahora usan vision en lite
    filtro = "tipo_servicio=in.(PQR,Emergencia,Visita%20conjunta)"
    r = requests.get(
        f"{url_base}/rest/v1/actas_qa?select=ot_id,ot_nombre,internal_bia_code,tipo_servicio,procesado_en&{filtro}",
        headers=headers,
        timeout=60,
    )
    if r.status_code != 200:
        print(f"ERROR consulta: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    actas = r.json()
    print(f"Total PQR/VICO/Emergencia encontradas: {len(actas)}")

    desglose = {}
    for a in actas:
        k = a.get("tipo_servicio") or "null"
        desglose[k] = desglose.get(k, 0) + 1
    for k, v in sorted(desglose.items(), key=lambda x: -x[1]):
        print(f"  - tipo='{k}': {v}")

    if not actas:
        print("Nada que limpiar.")
        return

    ot_ids_remover = {a["ot_id"] for a in actas if a.get("ot_id")}

    # Limpiar actas_procesadas.json
    if os.path.exists(ARCHIVO_PROCESADOS):
        with open(ARCHIVO_PROCESADOS, "r", encoding="utf-8") as f:
            procesadas = json.load(f)
        antes = len(procesadas)
        procesadas = [x for x in procesadas if x not in ot_ids_remover]
        with open(ARCHIVO_PROCESADOS, "w", encoding="utf-8") as f:
            json.dump(procesadas, f, ensure_ascii=False, indent=2)
        print(f"actas_procesadas.json: {antes} -> {len(procesadas)} (removidas {antes - len(procesadas)})")

    print("\nListo. Disparar workflow QA BIA Automatico para reprocesar con vision.")


if __name__ == "__main__":
    main()
