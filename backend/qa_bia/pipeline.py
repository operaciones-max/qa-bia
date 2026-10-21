"""Orquestacion: procesa cada acta de punta a punta y corre el ciclo principal.
"""
import os
import time
import requests
from datetime import date

from . import config
from .utils import _normalizar_serial, ahora
from .estado import (
    _cargar_facturas_extraidas, _guardar_factura_extraida, cargar_alcances_procesados,
    cargar_visitas_previas, guardar_alcance_procesado, guardar_procesado, guardar_visita_previa,
)
from .catalogo import (
    _clasificar_qa_track, _requiere_wms_comparison, _tipo_necesita_vision_lite,
    _validar_tipificacion, identificar_planner,
)
from .metabase import (
    cargar_alcances, cargar_estado_app_ops, cargar_facturas_anteriores,
    cargar_inventario_wms, obtener_actas_nuevas,
)
from .supabase import actualizar_supabase_alcance, enviar_supabase, reconciliar_estado_app_ops
from .pdf import _renderizar_paginas_pdf, descargar_y_leer_pdf
from .facturas import extraer_serial_factura
from .ia import analizar_acta, analizar_acta_lite
from .validaciones import (
    _enforce_reglas_medida_servicio, _limpiar_errores_fantasma, _post_corregir_serie_foto,
    _simplificar_fallida, _validar_coincidencia_wms,
)
from .reportes import guardar_reporte


def verificar_nuevos_alcances(alcances, visitas_previas_dict):
    """Check alcances CSV for new entries and notify Slack."""
    procesados   = cargar_alcances_procesados()
    fecha_inicio = date.fromisoformat(getattr(config, "FECHA_INICIO_ALCANCES", "2026-05-02"))
    nuevos       = 0

    for co_code, alcance_row in alcances.items():
        alcance_id = alcance_row.get("ID", "").strip()
        if not alcance_id or alcance_id in procesados:
            continue

        fecha_str = alcance_row.get("Creado El", "").strip()
        try:
            if date.fromisoformat(fecha_str[:10]) < fecha_inicio:
                continue
        except Exception:
            continue

        visita_data = visitas_previas_dict.get(co_code)
        print(f"\n  -> Nuevo alcance: {co_code} (VP almacenada: {'Si' if visita_data else 'No'})")
        # Slack deshabilitado — solo Supabase
        actualizar_supabase_alcance(co_code, alcance_row)
        guardar_alcance_procesado(alcance_id)
        nuevos += 1
        if nuevos < 10:
            time.sleep(2)

    if nuevos == 0:
        print("  Sin nuevos alcances de ingenieria.")
    else:
        print(f"  {nuevos} alcance(s) nuevo(s) notificado(s).")


def procesar_acta(acta, wms, alcances=None, facturas=None):
    ot_nombre         = acta.get("title", acta.get("id"))
    pdf_url           = acta.get("act_pdf_url", "")
    tipo              = acta.get("Tipo de servicio", "")
    estado            = acta.get("electrician_status_id", "")
    or_norm           = acta.get("OR_NORM", "")
    internal_bia_code = acta.get("internal_bia_code", "")
    planner           = identificar_planner(or_norm)

    entry_wms       = wms.get(internal_bia_code, {})
    medidor_wms     = entry_wms.get("medidor") or {}
    serial_asignado = medidor_wms.get("serial", "")
    marca_asignada  = medidor_wms.get("marca", "")
    tcs_asignados   = [t.get("serial", "") for t in entry_wms.get("tcs", []) if t.get("serial")]
    tps_asignados   = [t.get("serial", "") for t in entry_wms.get("tps", []) if t.get("serial")]

    es_exitosa = estado in config.ESTADOS_EXITOSOS
    es_visita  = "previa" in tipo.lower()
    debe_comparar_wms = es_exitosa and not es_visita and bool(serial_asignado)

    qa_track    = _clasificar_qa_track(tipo)
    requiere_wms_track = _requiere_wms_comparison(tipo, qa_track)
    usa_full_qa = (qa_track == "Activacion") or requiere_wms_track

    print(f"\n  -> Procesando: {ot_nombre}")
    print(f"     Tipo: {tipo} | Estado: {estado} | Track: {qa_track} | QA: {'full' if usa_full_qa else 'lite'}")
    print(f"     OR: {or_norm} | Planner: {planner}")
    if serial_asignado:
        print(f"     WMS: medidor={serial_asignado} | TCs={len(tcs_asignados)} | TPs={len(tps_asignados)} | Comparar={debe_comparar_wms}")
    else:
        print(f"     WMS: No encontrado para {internal_bia_code}")

    texto_pdf, imagenes_pdf = descargar_y_leer_pdf(pdf_url)
    if not texto_pdf:
        print("     No se pudo leer el PDF. Se omite.")
        return False

    if usa_full_qa:
        print(f"     Analizando con Claude full ({config.CLAUDE_MODEL}) | imagenes: {len(imagenes_pdf)}")
        resultado_qa = analizar_acta(
            texto_pdf, tipo, estado, internal_bia_code,
            serial_asignado if debe_comparar_wms else "",
            marca_asignada if debe_comparar_wms else "",
            tcs_asignados if debe_comparar_wms else [],
            tps_asignados if debe_comparar_wms else [],
            imagenes_pdf=imagenes_pdf,
        )
    else:
        # PQR / VICO / Emergencia tienen acta fisica manuscrita en el PDF.
        # Renderizamos las primeras 4 paginas como imagenes a dpi=150 para que
        # Claude lea con vision el texto manuscrito del "Registro Fotografico Acta".
        imagenes_para_lite = None
        if _tipo_necesita_vision_lite(tipo):
            try:
                r_pdf = requests.get(pdf_url, timeout=30)
                if r_pdf.ok:
                    imagenes_para_lite = _renderizar_paginas_pdf(r_pdf.content, n_paginas=4, dpi=150)
                    print(f"     Vision lite habilitada ({tipo}): {len(imagenes_para_lite)} paginas a dpi=150")
            except Exception as e:
                print(f"     WARN: no se pudo descargar PDF para vision lite: {e}")
        print(f"     Analizando con Claude lite ({config.CLAUDE_MODEL}) — track {qa_track}")
        resultado_qa = analizar_acta_lite(
            texto_pdf, tipo, estado, internal_bia_code,
            imagenes_pdf=imagenes_para_lite,
        )

    if not resultado_qa:
        return False

    # FUENTE DE VERDAD del estado: electrician_status_id de Metabase, no la AI.
    # Si el tecnico cerro CLOSURE_SUCCESSFUL/COMPLETED -> EXITOSA. Si CLOSURE_FAILED/ELECTRICIAN_FAILED_VISIT -> FALLIDA.
    # La AI puede sugerir errores/alertas pero NO puede cambiar el estado_ot.
    resultado_qa["estado_ot"] = "EXITOSA" if es_exitosa else "FALLIDA"

    # Si el tecnico cerro EXITOSA, limpiamos tipificacion_falla porque no aplica.
    if es_exitosa:
        resultado_qa["tipificacion_falla"] = None

    resultado_qa["qa_track"]        = qa_track
    # Auto-cierre de gestion: SOLO si la OT esta formalmente cerrada en App Ops.
    # COMPLETED = tecnico termino pero NO cerrada → estado_revision = pendiente.
    if estado in ("CLOSURE_SUCCESSFUL", "CLOSURE_FAILED"):
        resultado_qa["estado_revision"] = "cerrada"
    else:
        resultado_qa["estado_revision"] = "pendiente"
    # estado_app_ops: refleja el cierre formal en App Ops, NO el resultado del tecnico.
    # COMPLETED no es cierre formal — la OT sigue pendiente de cerrar.
    if estado == "CLOSURE_SUCCESSFUL":
        resultado_qa["estado_app_ops"] = "Exitosa"
    elif estado == "CLOSURE_FAILED":
        resultado_qa["estado_app_ops"] = "Fallida"
    else:
        resultado_qa["estado_app_ops"] = None

    # Post-validaciones defensivas
    _enforce_reglas_medida_servicio(resultado_qa, tipo)
    _post_corregir_serie_foto(resultado_qa.get("medidor_encontrado"))
    _post_corregir_serie_foto(resultado_qa.get("medidor_instalado"))
    _validar_coincidencia_wms(
        resultado_qa,
        serial_asignado if debe_comparar_wms else "",
        tcs_asignados   if debe_comparar_wms else [],
        tps_asignados   if debe_comparar_wms else [],
        debe_comparar_wms,
    )
    _limpiar_errores_fantasma(resultado_qa, tipo)
    # _override_fallida_si_incompleto: DESACTIVADO. Respetamos el estado del tecnico.
    # El reviewer humano puede marcar como FALLIDA desde el dashboard (frontend/).
    _simplificar_fallida(resultado_qa)
    _validar_tipificacion(resultado_qa)

    resultado_qa["planner"]              = planner
    resultado_qa["or_norm"]              = or_norm
    resultado_qa["internal_bia_code"]    = internal_bia_code
    # WMS: serial + marca + objeto completo para que el dashboard muestre todo
    resultado_qa["medidor_wms_asignado"] = serial_asignado or None
    resultado_qa["medidor_wms_marca"]    = marca_asignada or None
    resultado_qa["tcs_wms_asignados"]    = tcs_asignados or []
    resultado_qa["tps_wms_asignados"]    = tps_asignados or []
    resultado_qa["wms_asignado"]         = bool(serial_asignado)
    resultado_qa["wms_completo"]         = entry_wms or None  # dict con medidor/tcs/tps completo

    # Tecnico y contratista: fuente de verdad es el CSV de Metabase, no la IA.
    # contractor_name = "BIA" (literal) -> empleado BIA Energy.
    # contractor_name = otro valor       -> contratista, nombre = ese valor.
    # contractor_name = vacio            -> desconocido (NO mentir que es BIA).
    csv_tecnico     = (acta.get("Electrician Visits__name") or "").strip()
    csv_contratista = (acta.get("contractor_name") or "").strip()
    if csv_tecnico:
        resultado_qa["tecnico_nombre"] = csv_tecnico
    if not csv_contratista:
        resultado_qa["tecnico_empresa"]    = None
        resultado_qa["contratista_nombre"] = None
    elif csv_contratista.upper() == "BIA":
        resultado_qa["tecnico_empresa"]    = "BIA"
        resultado_qa["contratista_nombre"] = None
    else:
        resultado_qa["tecnico_empresa"]    = "CONTRATISTA"
        resultado_qa["contratista_nombre"] = csv_contratista

    # Comparacion WMS marca vs alcance marca (si ambos disponibles)
    alc = (alcances or {}).get(internal_bia_code)
    alc_marca = ((alc or {}).get("Marca Del Medidor") or "").strip()
    if marca_asignada and alc_marca and alc_marca.upper() not in ("N/A", "-"):
        resultado_qa["wms_marca_coincide_alcance"] = (
            marca_asignada.strip().upper() == alc_marca.upper()
        )
    else:
        resultado_qa["wms_marca_coincide_alcance"] = None

    # Factura anterior: extraer serial + flag express del comercializador previo
    serial_factura  = None
    factura_express = None
    factura_estado  = "no_disponible"  # default: CO no tiene factura URL en hubspot
    factura_entry   = (facturas or {}).get(internal_bia_code) or {}
    factura_url     = factura_entry.get("url") if isinstance(factura_entry, dict) else factura_entry
    contract_id     = factura_entry.get("contract_id") if isinstance(factura_entry, dict) else None
    resultado_qa["contract_id"] = contract_id
    if factura_url:
        factura_estado = "borrosa"  # default si llegamos aca pero falla extraccion
        cache = _cargar_facturas_extraidas()
        cache_entry = cache.get(internal_bia_code) or {}
        # Invalidar cache si:
        #   - la URL cambio (ej. switch de pregunta 69895 -> 71842)
        #   - el cache no tiene serial (reintentar con patrones nuevos)
        #   - el estado guardado no fue 'ok' (reintentar tras mejoras de extraccion)
        cache_url_distinta = cache_entry and cache_entry.get("url") and cache_entry.get("url") != factura_url
        cache_sin_serial = cache_entry and not cache_entry.get("serial")
        cache_estado_no_ok = cache_entry and cache_entry.get("estado") not in ("ok",) and bool(cache_entry.get("estado"))
        cache_invalido = cache_url_distinta or cache_sin_serial or cache_estado_no_ok
        if internal_bia_code in cache and not cache_invalido:
            entry = cache_entry
            serial_factura  = entry.get("serial")
            factura_express = entry.get("express")
            estado_cache    = entry.get("estado", "")
            if serial_factura:
                factura_estado = "ok"
            elif estado_cache == "ok":
                factura_estado = "ok_sin_serial"  # extrajo pero serial no aparecio en PDF
            else:
                factura_estado = "borrosa"
        else:
            print(f"     Extrayendo medidor de factura anterior para {internal_bia_code}...")
            data, estado = extraer_serial_factura(factura_url)
            if data:
                serial_factura  = data.get("serial")
                factura_express = data.get("express")
            _guardar_factura_extraida(internal_bia_code, {
                "serial":  serial_factura,
                "express": factura_express,
                "url":     factura_url,
                "estado":  estado,
                "fecha":   ahora(),
            })
            if serial_factura:
                factura_estado = "ok"
            elif estado == "ok":
                factura_estado = "ok_sin_serial"
            else:
                factura_estado = "borrosa"
            print(f"     Factura anterior: serial={serial_factura} express={factura_express} ({estado})")
    resultado_qa["serial_medidor_factura_anterior"] = serial_factura
    resultado_qa["factura_anterior_express"]        = factura_express
    resultado_qa["factura_anterior_estado"]         = factura_estado
    serial_acta = ((resultado_qa.get("medidor_encontrado") or {}).get("serie") or "").strip()
    if serial_factura and serial_acta:
        resultado_qa["medidor_coincide_factura_anterior"] = (
            _normalizar_serial(serial_factura) == _normalizar_serial(serial_acta)
        )
    else:
        resultado_qa["medidor_coincide_factura_anterior"] = None


    print(f"     Resultado: {resultado_qa.get('estado_ot')} | Medida: {resultado_qa.get('tipo_medida')}")
    if resultado_qa.get("medidor_coincide_wms") is False:
        print(f"     ALERTA: Medidor instalado != WMS asignado {serial_asignado}")
    if resultado_qa.get("tcs_coinciden_wms") is False:
        print(f"     ALERTA: TCs instalados != WMS asignados")
    if resultado_qa.get("tps_coinciden_wms") is False:
        print(f"     ALERTA: TPs instalados != WMS asignados")
    errores = resultado_qa.get("validaciones", {}).get("errores_encontrados", [])
    if errores:
        print(f"     Errores QA: {', '.join(errores)}")

    # Guardar hallazgos de visita previa para comparacion futura con alcance
    if es_visita and internal_bia_code:
        vp_data = {
            "ot_nombre":                   ot_nombre,
            "fecha_procesada":             ahora(),
            "tipo_medida":                 resultado_qa.get("tipo_medida"),
            "factor_medida":               resultado_qa.get("factor_medida"),
            "medidor_encontrado":          resultado_qa.get("medidor_encontrado"),
            "medidor_enc_serie":           (resultado_qa.get("medidor_encontrado") or {}).get("serie"),
            "tcs_encontrados":             resultado_qa.get("tcs_encontrados"),
            "tps_encontrados":             resultado_qa.get("tps_encontrados"),
            "tecnico_nombre":              resultado_qa.get("tecnico_nombre"),
            "tecnico_empresa":             resultado_qa.get("tecnico_empresa"),
            "contratista_nombre":          resultado_qa.get("contratista_nombre"),
            "observacion_tecnico_verbatim": resultado_qa.get("observacion_tecnico_verbatim"),
        }
        guardar_visita_previa(internal_bia_code, vp_data)

        # Si ya existe un alcance para este CO, enviarlo inmediatamente
        if alcances:
            alcance_row = alcances.get(internal_bia_code)
            if alcance_row:
                alcance_id = alcance_row.get("ID", "").strip()
                procesados_alc = cargar_alcances_procesados()
                if alcance_id and alcance_id not in procesados_alc:
                    print(f"     Alcance encontrado para {internal_bia_code} — registrado en Supabase.")
                    # Slack deshabilitado — solo Supabase
                    guardar_alcance_procesado(alcance_id)

    guardar_reporte(acta, resultado_qa)
    # Slack y WhatsApp deshabilitados — solo escritura a Supabase.
    enviar_supabase(acta, resultado_qa, alcances.get(internal_bia_code) if alcances else None)
    guardar_procesado(acta.get("id"))
    print(f"     OK: {ot_nombre} auditada.")
    return True


def main():
    modo = "PRUEBA" if config.MODO_PRUEBA else "AUTOMATICO"
    print("=" * 58)
    print("   SISTEMA QA BIA ENERGY  -  Motor: Anthropic Claude")
    print("   Modo: " + modo)
    print("=" * 58)
    print("   Fecha inicio : " + config.FECHA_INICIO)
    print("   Pausa        : " + str(config.PAUSA_GROQ_SEGUNDOS) + "s entre actas")
    if config.MODO_PRUEBA:
        print("   Actas prueba : " + str(config.ACTAS_PRUEBA))
    print("=" * 58)

    print("\n  Cargando inventario WMS...")
    wms = cargar_inventario_wms()

    print("\n  Cargando alcances de ingenieria...")
    alcances = cargar_alcances()

    print("\n  Cargando facturas anteriores (HubSpot vía Metabase)...")
    facturas = cargar_facturas_anteriores()

    print("\n  Reconciliando estado_app_ops desde Metabase (question 15673)...")
    estados_by_id, estados_by_title = cargar_estado_app_ops()
    reconciliar_estado_app_ops(estados_by_id, estados_by_title)

    if config.MODO_PRUEBA:
        print("")
        actas = obtener_actas_nuevas()
        procesadas = 0
        for i, acta in enumerate(actas):
            if procesar_acta(acta, wms, alcances, facturas):
                procesadas += 1
            if i < len(actas) - 1:
                print("     Pausa " + str(config.PAUSA_GROQ_SEGUNDOS) + "s...")
                time.sleep(config.PAUSA_GROQ_SEGUNDOS)
        print("")
        print("=" * 58)
        print("   PRUEBA TERMINADA - " + str(procesadas) + " acta(s) auditada(s)")
        print("   Reportes en: " + os.path.abspath(config.CARPETA_REPORTES))
        print("=" * 58)
    else:
        actas = obtener_actas_nuevas()
        if actas:
            for i, acta in enumerate(actas):
                procesar_acta(acta, wms, alcances, facturas)
                if i < len(actas) - 1:
                    time.sleep(config.PAUSA_GROQ_SEGUNDOS)
        else:
            print("[" + ahora() + "] Sin actas nuevas.")

        print(f"\n[{ahora()}] Verificando nuevos alcances de ingenieria...")
        visitas_previas_dict = cargar_visitas_previas()
        verificar_nuevos_alcances(alcances, visitas_previas_dict)

        if not getattr(config, 'MODO_UNICO', False):
            while True:
                time.sleep(config.INTERVALO_SEGUNDOS)
                wms      = cargar_inventario_wms()
                alcances = cargar_alcances()
                facturas = cargar_facturas_anteriores()
                actas    = obtener_actas_nuevas()
                if actas:
                    for i, acta in enumerate(actas):
                        procesar_acta(acta, wms, alcances, facturas)
                        if i < len(actas) - 1:
                            time.sleep(config.PAUSA_GROQ_SEGUNDOS)
                else:
                    print("[" + ahora() + "] Sin actas nuevas. Revisando en " + str(config.INTERVALO_SEGUNDOS) + "s...")
                visitas_previas_dict = cargar_visitas_previas()
                verificar_nuevos_alcances(alcances, visitas_previas_dict)
