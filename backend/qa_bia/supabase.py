"""Salida principal: escritura en la tabla actas_qa de Supabase, que es la
que lee el dashboard (frontend). Ver docs/contrato-supabase.md.
"""
import os
import requests

from .utils import _av, ahora_utc_iso

# PostgREST devuelve como maximo 1000 filas por consulta (configuracion por defecto de Supabase).
TAM_PAGINA = 1000


def _supabase_base_url():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-len("/rest/v1")]
    return url


def _credenciales():
    """(url_base, key) o (None, None) si Supabase no esta configurado."""
    url = _supabase_base_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
           or os.environ.get("SUPABASE_ANON_KEY", "").strip())
    return (url, key) if url and key else (None, None)


def _headers(key, prefer=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _leer_todas(url_base, key, select):
    """Lee todas las filas de actas_qa paginando de a TAM_PAGINA."""
    filas = []
    while True:
        r = requests.get(
            f"{url_base}/rest/v1/actas_qa",
            params={"select": select, "order": "ot_id", "limit": TAM_PAGINA, "offset": len(filas)},
            headers=_headers(key),
            timeout=30,
        )
        r.raise_for_status()
        pagina = r.json()
        filas.extend(pagina)
        if len(pagina) < TAM_PAGINA:
            return filas


def reconciliar_estado_app_ops(by_id, by_title):
    """Para cada acta en Supabase, recalcula estado_app_ops y estado_revision segun
    el estado actual de App Ops en question 15673. Match preferido por ot_id,
    fallback por ot_nombre/Title. NO se usa CO porque mezcla actas distintas.

    Reglas:
      CLOSURE_SUCCESSFUL → estado_app_ops='Exitosa', estado_revision='cerrada'
      CLOSURE_FAILED     → estado_app_ops='Fallida', estado_revision='cerrada'
      COMPLETED/otros    → estado_app_ops=null,     estado_revision='pendiente'
    """
    if not by_id and not by_title:
        print("  Reconciliacion: no hay estados de App Ops cargados, se omite.")
        return
    url_base, key = _credenciales()
    if not url_base:
        print("  Reconciliacion: sin Supabase, se omite.")
        return

    try:
        actas = _leer_todas(url_base, key, "ot_id,ot_nombre,internal_bia_code,estado_app_ops,estado_revision")
    except Exception as e:
        print(f"  Reconciliacion: error consultando Supabase: {e}")
        return

    cambios = 0
    fallidos = 0
    matched_by_id = 0
    matched_by_title = 0
    sin_match_list = []
    headers_patch = _headers(key, "return=minimal")
    for acta in actas:
        ot_id = acta.get("ot_id")
        ot_nombre = acta.get("ot_nombre")
        if not ot_id:
            continue
        estado_real = by_id.get(ot_id)
        if estado_real:
            matched_by_id += 1
        elif ot_nombre:
            estado_real = by_title.get(ot_nombre)
            if estado_real:
                matched_by_title += 1
            else:
                sin_match_list.append(ot_nombre)
                continue
        else:
            sin_match_list.append(ot_id)
            continue
        if estado_real == "CLOSURE_SUCCESSFUL":
            nueva_app, nueva_rev = "Exitosa", "cerrada"
        elif estado_real == "CLOSURE_FAILED":
            nueva_app, nueva_rev = "Fallida", "cerrada"
        else:
            nueva_app, nueva_rev = None, "pendiente"
        if acta.get("estado_app_ops") == nueva_app and acta.get("estado_revision") == nueva_rev:
            continue
        try:
            r = requests.patch(
                f"{url_base}/rest/v1/actas_qa",
                params={"ot_id": f"eq.{ot_id}"},
                headers=headers_patch,
                json={"estado_app_ops": nueva_app, "estado_revision": nueva_rev},
                timeout=10,
            )
            r.raise_for_status()
            cambios += 1
        except Exception:
            fallidos += 1
    print(f"  Reconciliacion App Ops: {cambios}/{len(actas)} actualizadas"
          f"{f', {fallidos} con error' if fallidos else ''}. "
          f"Match por ot_id={matched_by_id}, por Title={matched_by_title}, "
          f"sin match={len(sin_match_list)}.")
    if sin_match_list:
        muestra = sin_match_list[:5]
        print(f"  Sin match (primeras 5): {muestra}")


def enviar_supabase(acta, resultado_qa, alcance_row=None):
    """Guarda (upsert) el resultado del QA. Devuelve False solo si hubo un error;
    sin Supabase configurado (corrida local) no guarda nada y devuelve True."""
    url, key = _credenciales()
    if not url:
        return True

    med_enc  = resultado_qa.get("medidor_encontrado") or {}
    med_inst = resultado_qa.get("medidor_instalado") or {}
    tcs_enc  = resultado_qa.get("tcs_encontrados") or {}
    tps_enc  = resultado_qa.get("tps_encontrados") or {}
    val      = resultado_qa.get("validaciones") or {}
    falla    = resultado_qa.get("tipificacion_falla") or {}

    registro = {
        "procesado_en":              ahora_utc_iso(),
        "ot_nombre":                 acta.get("title"),
        "ot_id":                     acta.get("id"),
        "tipo_servicio":             acta.get("Tipo de servicio"),
        "estado_ot":                 resultado_qa.get("estado_ot"),
        "fecha_ejecucion":           acta.get("start"),
        "pdf_url":                   acta.get("act_pdf_url") or None,
        "internal_bia_code":         acta.get("internal_bia_code"),
        "contract_id":               resultado_qa.get("contract_id"),
        "or_norm":                   acta.get("OR_NORM"),
        "planner":                   resultado_qa.get("planner"),
        "empresa":                   acta.get("company_name"),
        "direccion":                 acta.get("address"),
        "tipo_medida":               resultado_qa.get("tipo_medida"),
        "factor_medida":             str(resultado_qa.get("factor_medida") or ""),
        "tecnico_nombre":            resultado_qa.get("tecnico_nombre"),
        "tecnico_empresa":           resultado_qa.get("tecnico_empresa"),
        "contratista_nombre":        resultado_qa.get("contratista_nombre"),
        "medidor_encontrado_serie":  med_enc.get("serie"),
        "medidor_encontrado_marca":  med_enc.get("marca"),
        "medidor_instalado_serie":   med_inst.get("serie"),
        "medidor_instalado_marca":   med_inst.get("marca"),
        "medidor_coincide_wms":      resultado_qa.get("medidor_coincide_wms"),
        "tcs_coinciden_wms":         resultado_qa.get("tcs_coinciden_wms"),
        "tps_coinciden_wms":         resultado_qa.get("tps_coinciden_wms"),
        "sellos_medidor_encontrado": resultado_qa.get("sellos_medidor_encontrado"),
        "sellos_medidor_instalado":  resultado_qa.get("sellos_medidor_instalado"),
        "sellos_tcs_encontrados":    resultado_qa.get("sellos_tcs_encontrados"),
        "sellos_tcs_instalados":     resultado_qa.get("sellos_tcs_instalados"),
        "tiene_tcs":                 bool(tcs_enc.get("aplica") and tcs_enc.get("tiene")),
        "tiene_tps":                 bool(tps_enc.get("aplica") and tps_enc.get("tiene")),
        "tiene_telemedida":          bool((resultado_qa.get("telemedida_encontrada") or {}).get("tiene")),
        "tiene_diagrama_unifilar":   bool((resultado_qa.get("diagrama_unifilar") or {}).get("tiene_foto")),
        "or_firma":                  resultado_qa.get("or_firma"),
        "validacion_coherente":      val.get("coherencia"),
        "errores_qa":                val.get("errores_encontrados") or [],
        "alertas_qa":                resultado_qa.get("alertas_qa") or [],
        "tipificacion_causa_raiz":   falla.get("causa_raiz"),
        "tipificacion_responsable":  falla.get("responsable"),
        "wms_asignado":              bool(resultado_qa.get("wms_asignado")),
        "wms_medidor_serial":        resultado_qa.get("medidor_wms_asignado"),
        "wms_medidor_marca":         resultado_qa.get("medidor_wms_marca"),
        "wms_completo":              resultado_qa.get("wms_completo"),
        "wms_marca_coincide_alcance": resultado_qa.get("wms_marca_coincide_alcance"),
        "serial_medidor_factura_anterior":   resultado_qa.get("serial_medidor_factura_anterior"),
        "medidor_coincide_factura_anterior": resultado_qa.get("medidor_coincide_factura_anterior"),
        "factura_anterior_express":          resultado_qa.get("factura_anterior_express"),
        "factura_anterior_estado":           resultado_qa.get("factura_anterior_estado"),
        "qa_track":                          resultado_qa.get("qa_track"),
        "estado_app_ops":                    resultado_qa.get("estado_app_ops"),
        "estado_revision":                   resultado_qa.get("estado_revision") or "pendiente",
        "tiene_alcance":             alcance_row is not None,
        "alcance_viable":            _av(alcance_row, "Viable Para Instalar") if alcance_row else None,
        "alcance_medida_instalar":   _av(alcance_row, "Tipo De Medida A Instalar") if alcance_row else None,
        "alcance_completo":          dict(alcance_row) if alcance_row else None,
        "resultado_qa_completo":     resultado_qa,
    }

    try:
        r = requests.post(
            f"{url}/rest/v1/actas_qa?on_conflict=ot_id",
            headers=_headers(key, "resolution=merge-duplicates,return=minimal"),
            json=registro,
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            print("  Supabase: registro guardado.")
            return True
        print(f"  ERROR Supabase: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Supabase: {e}")
    return False


def actualizar_supabase_alcance(co_code, alcance_row):
    """Marca con el alcance las visitas previas del CO. Devuelve False solo si hubo error."""
    url, key = _credenciales()
    if not url:
        return True

    body = {
        "tiene_alcance":           True,
        "alcance_viable":          _av(alcance_row, "Viable Para Instalar"),
        "alcance_medida_instalar": _av(alcance_row, "Tipo De Medida A Instalar"),
        "alcance_completo":        dict(alcance_row),
    }
    try:
        r = requests.patch(
            f"{url}/rest/v1/actas_qa",
            params={
                "internal_bia_code": f"eq.{co_code}",
                "tipo_servicio":     "eq.Visita previa",
            },
            headers=_headers(key, "return=minimal"),
            json=body,
            timeout=15,
        )
        if 200 <= r.status_code < 300:
            print(f"  Supabase: VIPE {co_code} marcada con alcance.")
            return True
        print(f"  ERROR Supabase alcance: {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Supabase alcance: {e}")
    return False
