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
"""
import json
import os
import sys
import requests


def _supabase_base_url():
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")]
    return url


def main():
    url_base = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    if not url_base or not key:
        print("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY requeridos")
        sys.exit(1)

    print("Buscando actas con problema de factura anterior...")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    # Caso A: extraccion fallo (estado=borrosa o ok_sin_serial)
    filtro_a = "factura_anterior_estado=in.(borrosa,ok_sin_serial)"
    r_a = requests.get(
        f"{url_base}/rest/v1/actas_qa?select=ot_id,ot_nombre,internal_bia_code,factura_anterior_estado,medidor_coincide_factura_anterior&{filtro_a}",
        headers=headers,
        timeout=60,
    )
    if r_a.status_code != 200:
        print(f"ERROR consulta A: {r_a.status_code} {r_a.text[:200]}")
        sys.exit(1)
    actas_a = r_a.json()

    # Caso B: extraccion OK pero medidor NO coincide (probable mal-extraccion como AFINIA 7727246)
    filtro_b = "factura_anterior_estado=eq.ok&medidor_coincide_factura_anterior=eq.false"
    r_b = requests.get(
        f"{url_base}/rest/v1/actas_qa?select=ot_id,ot_nombre,internal_bia_code,factura_anterior_estado,medidor_coincide_factura_anterior&{filtro_b}",
        headers=headers,
        timeout=60,
    )
    if r_b.status_code != 200:
        print(f"ERROR consulta B: {r_b.status_code} {r_b.text[:200]}")
        sys.exit(1)
    actas_b = r_b.json()

    # Unir sin duplicar
    vistos = set()
    actas_problematicas = []
    for a in actas_a + actas_b:
        oid = a.get("ot_id")
        if oid and oid not in vistos:
            vistos.add(oid)
            actas_problematicas.append(a)

    print(f"Caso A (extraccion fallo): {len(actas_a)}")
    print(f"Caso B (extraccion OK pero no coincide): {len(actas_b)}")
    print(f"Total unicas a reprocesar: {len(actas_problematicas)}")

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
    if os.path.exists("actas_procesadas.json"):
        with open("actas_procesadas.json", "r", encoding="utf-8") as f:
            procesadas = json.load(f)
        antes = len(procesadas)
        procesadas = [x for x in procesadas if x not in ot_ids_remover]
        with open("actas_procesadas.json", "w", encoding="utf-8") as f:
            json.dump(procesadas, f, ensure_ascii=False, indent=2)
        print(f"actas_procesadas.json: {antes} -> {len(procesadas)} (removidas {antes - len(procesadas)})")

    # 2. Limpiar facturas_extraidas.json
    if os.path.exists("facturas_extraidas.json"):
        with open("facturas_extraidas.json", "r", encoding="utf-8") as f:
            facturas_cache = json.load(f)
        antes = len(facturas_cache)
        for co in cos_remover:
            facturas_cache.pop(co, None)
        with open("facturas_extraidas.json", "w", encoding="utf-8") as f:
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
