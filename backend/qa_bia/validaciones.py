"""Post-validaciones defensivas sobre la respuesta de la IA: reglas por tipo
de medida/servicio, comparacion con WMS y limpieza de errores falsos.
"""
from .utils import _normalizar_serial


def _post_corregir_serie_foto(item):
    if not isinstance(item, dict):
        return
    serie = (item.get("serie") or "").strip()
    obs   = (item.get("observacion_serie_foto") or "")
    if item.get("serie_coincide_foto") is False and serie:
        norm_serie = _normalizar_serial(serie)
        norm_obs   = _normalizar_serial(obs)
        if norm_serie and norm_serie in norm_obs:
            item["serie_coincide_foto"] = True
            item["observacion_serie_foto"] = None


def _enforce_reglas_medida_servicio(qa, tipo_servicio):
    tipo_medida = (qa.get("tipo_medida") or "").upper()
    es_visita   = "previa" in (tipo_servicio or "").lower()

    def _force_false(key):
        if isinstance(qa.get(key), dict):
            qa[key]["aplica"] = False

    if tipo_medida == "DIRECTA":
        for k in ("tcs_encontrados", "tcs_instalados",
                  "tps_encontrados", "tps_instalados",
                  "bloque_pruebas_encontrado", "bloque_pruebas_instalado",
                  "cable_control_encontrado", "cable_control_instalado"):
            _force_false(k)
        qa["fotos_tcs"] = None
        qa["fotos_tps"] = None
    elif tipo_medida == "SEMIDIRECTA":
        for k in ("tps_encontrados", "tps_instalados"):
            _force_false(k)
        qa["fotos_tps"] = None

    if es_visita:
        for k in ("medidor_instalado", "tcs_instalados", "tps_instalados",
                  "bloque_pruebas_instalado", "cable_control_instalado",
                  "telemedida_instalada", "totalizador_instalado",
                  "cables_potencia_instalados", "medidor_respaldo_instalado",
                  "sellos_instalados"):
            _force_false(k)


def _validar_coincidencia_wms(qa, serial_wms, tcs_wms, tps_wms, debe_comparar):
    if debe_comparar and serial_wms:
        inst = qa.get("medidor_instalado") or {}
        serie_inst = (inst.get("serie") or "").strip() or (qa.get("medidor_instalado_acta") or "").strip()
        if serie_inst:
            qa["medidor_coincide_wms"] = _normalizar_serial(serie_inst) == _normalizar_serial(serial_wms)
        else:
            qa["medidor_coincide_wms"] = None
    else:
        qa["medidor_coincide_wms"] = None

    tipo_medida = (qa.get("tipo_medida") or "").upper()

    if debe_comparar and tcs_wms and tipo_medida in ("SEMIDIRECTA", "INDIRECTA"):
        tcs_inst = (qa.get("tcs_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tcs_wms if s}
        acta_set = {_normalizar_serial(s) for s in tcs_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tcs_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tcs_coinciden_wms"] = None

    if debe_comparar and tps_wms and tipo_medida == "INDIRECTA":
        tps_inst = (qa.get("tps_instalados") or {}).get("seriales") or []
        wms_set  = {_normalizar_serial(s) for s in tps_wms if s}
        acta_set = {_normalizar_serial(s) for s in tps_inst if s}
        wms_set.discard(""); acta_set.discard("")
        qa["tps_coinciden_wms"] = bool(wms_set) and wms_set.issubset(acta_set)
    else:
        qa["tps_coinciden_wms"] = None


def _limpiar_errores_fantasma(qa, tipo_servicio):
    """Saca errores que reportan comportamiento NORMAL segun reglas de medida/servicio.
    Tambien dedupea errores vs alertas y elimina ruido."""
    val = qa.get("validaciones") or {}
    errores = val.get("errores_encontrados") or []
    alertas = qa.get("alertas_qa") or []

    tipo_medida    = (qa.get("tipo_medida") or "").upper()
    es_visita      = "previa" in (tipo_servicio or "").lower()
    es_directa     = tipo_medida == "DIRECTA"
    es_semidirecta = tipo_medida == "SEMIDIRECTA"

    def es_fantasma(item):
        s = " " + (item or "").lower() + " "
        # REGLA UNIVERSAL: cualquier "no se reporta(n)" es un dump de fields vacios,
        # no un error real. Si un campo falta y es realmente critico, el reviewer
        # marca FALLIDA manual desde el dashboard (frontend/).
        if " no se reporta " in s or " no se reportan " in s:
            return True
        if " no se encontraron " in s or " no se encontro " in s or " no se encontró " in s:
            return True
        # Patterns adicionales que tambien filtramos siempre
        for term in (
            "no coincide con la serie visible en foto",
            "no coincide con la foto",
            "serie visible en foto",
            "no se realizaron pruebas",
            "el acta no reporta",
        ):
            if term in s:
                return True
        if es_directa:
            for term in (" tc ", " tcs ", " tp ", " tps ", "bloque de pruebas",
                         "bloque pruebas", "cable de control", "cable control"):
                if term in s:
                    return True
        if es_semidirecta:
            if (" tp " in s or " tps " in s) and " tc " not in s and " tcs " not in s:
                return True
        if es_visita:
            if "instalad" in s and "telemedida instalad" not in s and "totalizador instalad" not in s:
                return True
            for term in ("pruebas de funcionamiento", "equipo patron", "equipo patrón",
                         "diagrama unifilar", "no se realizaron pruebas",
                         "no se reporta equipo", "no se reporta foto",
                         "no se reportan fotos", "no se reportan sellos",
                         "no se encontraron sellos", "no se encontro sello",
                         "no se encontraron fotos", "no se encontro foto",
                         "no se encontro telemedida", "no se encontró telemedida",
                         "no se encontro bloque", "no se encontró bloque",
                         "no se encontro cable", "no se encontró cable",
                         "medidor de respaldo", "medidor de espejo",
                         "planta de respaldo", "planta electrica",
                         "no se encontraron alertas", "no se encontraron tcs",
                         "no se encontraron tps",
                         "el acta no reporta", "no se reporta el color",
                         "no se reporta la serie del sello",
                         "no reporta la serie del sello",
                         "no reporta el color del sello",
                         "no se reporta el segundo sello", "no se reporta el tercer sello",
                         "color del sello", "serie del sello",
                         "no reporta lectura", "no se reporta lectura",
                         "operador de red", "comercializador anterior"):
                if term in s:
                    return True
        for term in ("medidor de respaldo", "medidor de espejo", "planta de respaldo",
                     "no se encontro"):
            if term in s and tipo_medida == "DIRECTA":
                return True
        # Campos del acta con valor basura: el override a FALLIDA ya tipifica eso
        for term in (": n.v", ": .o", ": .0", ": otra", ": otro",
                     "no reportada", "no reportado"):
            if term in s and ("encontrada" in s or "encontrado" in s
                              or "instalada" in s or "instalado" in s):
                return True
        return False

    errores_l = [e for e in errores if not es_fantasma(e)]
    alertas_l = [a for a in alertas if not es_fantasma(a)]
    set_err = set(errores_l)
    alertas_l = [a for a in alertas_l if a not in set_err]

    val["errores_encontrados"] = errores_l
    qa["validaciones"] = val
    qa["alertas_qa"] = alertas_l


def _simplificar_fallida(qa):
    """Cuando estado_ot=FALLIDA, vacia errores, deja solo alertas de firma OR/usuario,
    y elimina cinco_por_que de tipificacion (redundante con causa_raiz/detalle/mejora).
    La tipificacion ya explica todo — no es util listar errores tecnicos ni 5 porques."""
    if qa.get("estado_ot") != "FALLIDA":
        return
    val = qa.get("validaciones") or {}
    val["errores_encontrados"] = []
    qa["validaciones"] = val
    alertas = qa.get("alertas_qa") or []
    keep = []
    for a in alertas:
        a_low = (a or "").lower()
        if "firm" in a_low and ("operador" in a_low or " or " in a_low or "or " in a_low or "usuario" in a_low or "cliente" in a_low):
            keep.append(a)
    if (qa.get("or_firma") or "").upper() == "NO":
        already = any("operador" in (k or "").lower() and "firm" in (k or "").lower() for k in keep)
        if not already:
            keep.append("El Operador de Red NO firmó el acta.")
    qa["alertas_qa"] = keep
    falla = qa.get("tipificacion_falla") or {}
    falla["cinco_por_que"] = []
    qa["tipificacion_falla"] = falla
