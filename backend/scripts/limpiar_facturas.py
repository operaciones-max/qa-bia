"""
Script one-shot para limpiar caches y forzar reprocesamiento de actas
con factura anterior mal extraida.

Lo que hace:
1. Consulta Supabase para identificar actas con problema de factura:
   - factura_anterior_estado IN ('borrosa', 'ok_sin_serial')
   - O serial_medidor_factura_anterior NULL pero existe URL de factura
2. Quita esos ot_ids de actas_procesadas.json
3. Quita esos internal_bia_code de facturas_extraidas.json
4. Resetea las columnas de factura en Supabase para esas actas
5. El proximo run del cron las reprocesa con los nuevos patrones AFINIA/Enel/etc.

Ejecutar desde backend/:  python -m scripts.limpiar_facturas
"""
import json
import os
import sys
import requests

from qa_bia import config
from qa_bia.supabase import _supabase_base_url

ARCHIVO_PROCESADOS = config.ARCHIVO_PROCESADOS
ARCHIVO_FACTURAS = config.ARCHIVO_FACTURAS_EXTRAIDAS


def main():
    url_base = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    if not url_base or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY requeridos")
        sys.exit(1)

    print("Buscando todas las VIPE (visita previa) para reprocesar con nuevos patrones de factura...")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    # Todas las visitas previas — las que comparan medidor vs factura anterior
    # Filtro: tipo_servicio ilike visita previa O ot_nombre comienza con VIPE_
    filtro = "or=(tipo_servicio.ilike.*visita%20previa*,ot_nombre.ilike.VIPE_*)"
    r = requests.get(
        f"{url_base}/rest/v1/actas_qa?select=ot_id,ot_nombre,internal_bia_code,tipo_servicio,factura_anterior_estado,medidor_coincide_factura_anterior&{filtro}",
        headers=headers,
        timeout=60,
    )
    if r.status_code != 200:
        print(f"ERROR consulta: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    actas_problematicas = r.json()
    print(f"Total VIPE encontradas: {len(actas_problematicas)}")

    # Desglose por estado actual de factura
    desglose = {}
    for a in actas_problematicas:
        k = a.get("factura_anterior_estado") or "null"
        desglose[k] = desglose.get(k, 0) + 1
    for k, v in sorted(desglose.items(), key=lambda x: -x[1]):
        print(f"  - estado_factura='{k}': {v}")

    if not actas_problematicas:
        print("Nada que limpiar.")
        return

    ot_ids_remover = {a["ot_id"] for a in actas_problematicas if a.get("ot_id")}
    cos_remover = {a["internal_bia_code"] for a in actas_problematicas if a.get("internal_bia_code")}

    for a in actas_problematicas[:10]:
        print(f"  - {a.get('ot_nombre')} | CO={a.get('internal_bia_code')} | estado={a.get('factura_anterior_estado')}")
    if len(actas_problematicas) > 10:
        print(f"  ... y {len(actas_problematicas) - 10} mas")

    # 1. Limpiar actas_procesadas.json
    if os.path.exists(ARCHIVO_PROCESADOS):
        with open(ARCHIVO_PROCESADOS, "r", encoding="utf-8") as f:
            procesadas = json.load(f)
        antes = len(procesadas)
        procesadas = [x for x in procesadas if x not in ot_ids_remover]
        with open(ARCHIVO_PROCESADOS, "w", encoding="utf-8") as f:
            json.dump(procesadas, f, ensure_ascii=False, indent=2)
        print(f"actas_procesadas.json: {antes} -> {len(procesadas)} (removidas {antes - len(procesadas)})")

    # 2. Limpiar facturas_extraidas.json
    if os.path.exists(ARCHIVO_FACTURAS):
        with open(ARCHIVO_FACTURAS, "r", encoding="utf-8") as f:
            facturas_cache = json.load(f)
        antes = len(facturas_cache)
        for co in cos_remover:
            facturas_cache.pop(co, None)
        with open(ARCHIVO_FACTURAS, "w", encoding="utf-8") as f:
            json.dump(facturas_cache, f, ensure_ascii=False, indent=2)
        print(f"facturas_extraidas.json: {antes} -> {len(facturas_cache)} (removidas {antes - len(facturas_cache)})")
    else:
        print("facturas_extraidas.json no existe (nada que limpiar).")

    # 3. Resetear columnas de factura en Supabase para esas actas
    print("Reseteando columnas de factura en Supabase...")
    headers_patch = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    reset_count = 0
    for a in actas_problematicas:
        ot_id = a.get("ot_id")
        if not ot_id:
            continue
        try:
            requests.patch(
                f"{url_base}/rest/v1/actas_qa?ot_id=eq.{ot_id}",
                headers=headers_patch,
                json={
                    "serial_medidor_factura_anterior": None,
                    "medidor_coincide_factura_anterior": None,
                    "factura_anterior_estado": None,
                },
                timeout=15,
            )
            reset_count += 1
        except Exception as e:
            print(f"  Error reseteando {ot_id}: {e}")
    print(f"Supabase: {reset_count} actas reseteadas.")
    print("\nListo. Disparar workflow QA BIA Automatico para reprocesarlas.")


if __name__ == "__main__":
    main()
