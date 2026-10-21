"""Formateo y envio de mensajes a Slack.

DESHABILITADO: hoy el sistema solo escribe en Supabase. Se conserva el codigo
por si se reactivan las notificaciones.
"""
import os
import requests

from . import config
from .utils import _av, _normalizar_serial


def _alertar_slack_cooldown(data):
    if getattr(config, "MODO_BACKFILL", False):
        return  # silenciado durante backfill — solo loguea en consola
    url = os.environ.get("SLACK_WEBHOOK_URL", "") or getattr(config, "SLACK_WEBHOOK_URL", "")
    if not url:
        return
    titulo = "QA pausado: Gemini agoto cuota diaria" if data["razon"] == "daily_quota" \
             else "QA pausado: Gemini rate-limit transitorio"
    cuerpo = f"*{titulo}*\n• Reanudacion estimada (UTC): `{data['until']}`\n• Tipo: `{data['razon']}`"
    try:
        requests.post(url, json={"text": cuerpo}, timeout=10)
    except Exception as e:
        print(f"  ERROR alerta Slack cooldown: {e}")


def _v(x, na="N/A"):
    if x is None:
        return na
    s = str(x).strip()
    return s if s and s not in ("-", "null", "None") else na


def _check(ok):
    if ok is True:
        return "✅"
    if ok is False:
        return "❌"
    return ""


def _viable_ok(s):
    """Normalize 'Sí'/'Si'/'S?' variations from CSV encoding."""
    return s.lower().strip() in ("si", "sí", "s?", "yes", "true", "1")


def _seccion_transformador(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Transformador:* No reporta\n"
    return (
        "*Transformador*\n"
        f"  Numero: {_v(t.get('numero'))}  |  Capacidad: {_v(t.get('capacidad_kva'))} kVA\n"
        f"  Ubicacion: {_v(t.get('ubicacion'))}  |  Uso: {_v(t.get('tipo_uso'))}\n"
    )


def _seccion_medidor_encontrado(m, sellos=None):
    if not m:
        return ""
    base = (
        "*Medidor encontrado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh  |  Reactiva: {_v(m.get('lectura_reactiva_kvarh'))} kVArh\n"
    )
    chk = _check(m.get("serie_coincide_foto"))
    if chk:
        obs = _v(m.get("observacion_serie_foto"), "")
        base += f"  Verificacion serie vs foto: {chk} {obs}".rstrip() + "\n"
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base


def _seccion_medidor_instalado(m, coincide_wms=None, serial_wms="", fotos=None, sellos=None):
    if not m or not m.get("aplica"):
        return ""
    if not m.get("se_instalo"):
        return "*Medidor instalado:* No se instalo\n"
    foto_ok = m.get("serie_coincide_foto")
    overall = True
    if foto_ok is False or coincide_wms is False:
        overall = False
    titulo_chk = _check(overall)
    base = (
        f"*Medidor instalado* {titulo_chk}".rstrip() + "\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}  |  Ref: {_v(m.get('referencia'))}\n"
        f"  Lectura activa: {_v(m.get('lectura_activa_kwh'))} kWh\n"
    )
    chk = _check(foto_ok)
    if chk:
        obs = _v(m.get("observacion_serie_foto"), "")
        base += f"  Verificacion serie vs foto: {chk} {obs}".rstrip() + "\n"
    if coincide_wms is True:
        base += f"  WMS asignado: {serial_wms} ✅ Coincide\n"
    elif coincide_wms is False:
        base += f"  WMS asignado: {serial_wms} ❌ NO coincide\n"
    if fotos is not None:
        base += f"  Fotos cargadas: {fotos}\n"
    if sellos is not None:
        base += f"  Sellos instalados: {sellos}\n"
    return base


def _seccion_sellos(s):
    if not s or not s.get("aplica"):
        return ""
    total = s.get("total")
    chk   = _check(s.get("todos_completos"))
    falt  = s.get("campos_faltantes") or []
    if total is None or (isinstance(total, str) and not total.strip()):
        if not falt and chk == "":
            return ""
        cant = "N/A"
    else:
        cant = str(total)
    base = f"*Sellos instalados:* {cant} sello(s) {chk}".rstrip() + "\n"
    if falt:
        base += "  Campos incompletos:\n" + "\n".join(f"   - {f}" for f in falt) + "\n"
    return base


def _seccion_medidor_respaldo(m):
    if not m or not m.get("aplica"):
        return ""
    if not m.get("se_instalo"):
        return "*Medidor de respaldo:* No se instalo\n"
    return (
        "*Medidor de respaldo instalado*\n"
        f"  Serie: {_v(m.get('serie'))}  |  Marca: {_v(m.get('marca'))}\n"
    )


def _seccion_telemedida_encontrada(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Telemedida encontrada:* No\n"
    return (
        "*Telemedida encontrada*\n"
        f"  IP: {_v(t.get('ip'))}  |  Puerto: {_v(t.get('puerto'))}\n"
        f"  Serie: {_v(t.get('serie'))}  |  Marca: {_v(t.get('marca'))}  |  IMEI: {_v(t.get('imei'))}\n"
    )


def _seccion_telemedida_instalada(t):
    if not t or not t.get("aplica"):
        return ""
    if not t.get("se_instalo"):
        return "*Telemedida instalada:* No se realizaron cambios en el modem\n"
    return (
        "*Telemedida instalada*\n"
        f"  IP: {_v(t.get('ip'))}  |  Puerto: {_v(t.get('puerto'))}\n"
        f"  Serie: {_v(t.get('serie'))}  |  Marca: {_v(t.get('marca'))}  |  IMEI: {_v(t.get('imei'))}\n"
        f"  Operador SIM: {_v(t.get('operador_sim'))}  |  Serie SIM: {_v(t.get('serie_sim'))}\n"
    )


def _seccion_totalizador_encontrado(t):
    if not t:
        return ""
    if not t.get("tiene"):
        return "*Totalizador encontrado:* No\n"
    return (
        "*Totalizador encontrado*\n"
        f"  Marca: {_v(t.get('marca'))}  |  Capacidad: {_v(t.get('capacidad_a'))} A  |  Fases: {_v(t.get('fases'))}\n"
    )


def _seccion_totalizador_instalado(t):
    if not t or not t.get("aplica"):
        return ""
    if not t.get("se_instalo"):
        return "*Totalizador instalado:* No se instalo\n"
    return (
        "*Totalizador instalado*\n"
        f"  Marca: {_v(t.get('marca'))}  |  Capacidad: {_v(t.get('capacidad_a'))} A  |  Fases: {_v(t.get('fases'))}\n"
    )


def _seccion_cables_enc(c):
    if not c:
        return ""
    if not c.get("tiene"):
        return "*Cables de potencia encontrados:* No\n"
    return (
        "*Cables de potencia encontrados*\n"
        f"  Parcial: calibre {_v(c.get('calibre_parcial'))}, {_v(c.get('cables_por_fase_parcial'))} cable(s) por fase\n"
        f"  Acometida: calibre {_v(c.get('calibre_acometida'))}, {_v(c.get('cables_por_fase_acometida'))} cable(s) por fase\n"
    )


def _seccion_cables_inst(c):
    if not c or not c.get("aplica"):
        return ""
    if not c.get("se_instalo"):
        return "*Cables de potencia instalados:* No se instalo cable de potencia\n"
    return (
        "*Cables de potencia instalados*\n"
        f"  Parcial: calibre {_v(c.get('calibre_parcial'))}, {_v(c.get('cables_por_fase_parcial'))} cable(s) por fase\n"
        f"  Acometida: calibre {_v(c.get('calibre_acometida'))}, {_v(c.get('cables_por_fase_acometida'))} cable(s) por fase\n"
    )


def _seccion_aplica_simple(label, d, key_estado="tiene", txt_no="No"):
    if not d or not d.get("aplica"):
        return ""
    if not d.get(key_estado):
        return f"*{label}:* {txt_no}\n"
    return f"*{label}:* {_v(d.get('detalles'))}\n"


def _seccion_tcs_encontrados(d, sellos=None):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("tiene"):
        return "*TCs encontrados:* No\n"
    seriales = d.get("seriales") or []
    base = "*TCs encontrados*\n"
    if seriales:
        base += f"  Seriales: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base


def _seccion_tps_encontrados(d, sellos=None):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("tiene"):
        return "*TPs encontrados:* No\n"
    seriales = d.get("seriales") or []
    base = "*TPs encontrados*\n"
    if seriales:
        base += f"  Seriales: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if sellos is not None:
        base += f"  Sellos encontrados: {sellos}\n"
    return base


def _seccion_tc_tp_instalados(label, d, wms_asignados, coincide, fotos=None, sellos=None):
    if not d or not d.get("aplica"):
        return ""
    if not d.get("se_instalo"):
        return f"*{label}:* No se instalo\n"
    seriales = d.get("seriales") or []
    titulo_chk = _check(coincide) if coincide is not None else _check(bool(seriales))
    base = f"*{label}* {titulo_chk}".rstrip() + "\n"
    if seriales:
        base += f"  Seriales acta: {', '.join(seriales)}\n"
    elif d.get("detalles"):
        base += f"  {_v(d.get('detalles'))}\n"
    if d.get("marca"):
        base += f"  Marca: {_v(d.get('marca'))}\n"
    if wms_asignados:
        base += f"  WMS asignado: {', '.join(wms_asignados)}\n"
        chk = _check(coincide)
        if chk:
            base += f"  Coincidencia WMS: {chk}\n"
    if fotos is not None:
        base += f"  Fotos cargadas: {fotos}\n"
    if sellos is not None:
        base += f"  Sellos instalados: {sellos}\n"
    return base


def _seccion_bloque_pruebas(b, instalado=False):
    if not b or not b.get("aplica"):
        return ""
    label = "Bloque de pruebas instalado" if instalado else "Bloque de pruebas encontrado"
    estado_key = "se_instalo" if instalado else "tiene"
    if not b.get(estado_key):
        return f"*{label}:* {'No se instalo' if instalado else 'No'}\n"
    return f"*{label}*\n  Marca: {_v(b.get('marca'))}  |  Tipo: {_v(b.get('tipo'))}\n"


def _seccion_cable_control(c, instalado=False):
    if not c or not c.get("aplica"):
        return ""
    label = "Cable de control instalado" if instalado else "Cable de control encontrado"
    estado_key = "se_instalo" if instalado else "tiene"
    if not c.get(estado_key):
        return f"*{label}:* {'No se instalo' if instalado else 'No'}\n"
    return (
        f"*{label}*\n"
        f"  Marca: {_v(c.get('marca'))}\n"
        f"  Calibre corriente: {_v(c.get('calibre_corriente'))}  |  Tension: {_v(c.get('calibre_tension'))}  |  Metros: {_v(c.get('metros'))}\n"
    )


def _seccion_pruebas(p):
    if not p:
        return ""
    if not p.get("se_realizaron"):
        return "*Pruebas de funcionamiento:* No\n"
    return f"*Pruebas de funcionamiento*\n  {_v(p.get('resumen'))}\n"


def _seccion_equipo_patron(e):
    if not e:
        return ""
    if not e.get("se_uso"):
        return "*Equipo patron:* No\n"
    return f"*Equipo patron*\n  {_v(e.get('resumen'))}\n"


def _seccion_tecnico(qa):
    nombre = _v(qa.get("tecnico_nombre"), "")
    if not nombre:
        return ""
    empresa = (qa.get("tecnico_empresa") or "").strip()
    contratista = _v(qa.get("contratista_nombre"), "")
    if empresa == "CONTRATISTA" and contratista:
        empresa_txt = f"Contratista - {contratista}"
    elif empresa == "BIA":
        empresa_txt = "BIA Energy"
    else:
        empresa_txt = empresa or "N/A"
    return (
        "*Tecnico ejecutor*\n"
        f"  Nombre: {nombre}\n"
        f"  Empresa: {empresa_txt}\n"
    )


def _seccion_observacion_tecnico(qa):
    obs = (qa.get("observacion_tecnico_verbatim") or "").strip()
    if not obs or obs in ("null", "N/A", "-"):
        return ""
    return f"*Observacion del tecnico:*\n_{obs}_\n"


def _seccion_alcance_ingenieria(a):
    """Render full engineering alcance from CSV row."""
    if not a:
        return "*Alcance de ingenieria:* Sin alcance registrado\n"

    viable = _av(a, "Viable Para Instalar")
    viable_chk = "✅" if _viable_ok(viable) else ("❌" if viable.lower() == "no" else "")

    lines = [f"*Alcance de ingenieria* {viable_chk}\n".rstrip() + "\n"]
    lines.append(f"  Viable para instalar: {viable}\n")

    medida_inst  = _av(a, "Tipo De Medida A Instalar")
    factor_inst  = _av(a, "Factor De Medida A Instalar")
    nivel_inst   = _av(a, "Nivel De Tension A Instalar")
    cambio_eq    = _av(a, "Se Require Cambio De Equipos")

    if medida_inst != "N/A":  lines.append(f"  Medida a instalar: {medida_inst}\n")
    if factor_inst != "N/A":  lines.append(f"  Factor a instalar: {factor_inst}\n")
    if nivel_inst  != "N/A":  lines.append(f"  Nivel de tension: {nivel_inst}\n")
    if cambio_eq   != "N/A":  lines.append(f"  Cambio de equipos: {cambio_eq}\n")

    # TCs a instalar
    tipo_tc   = _av(a, "Tipo De Tc A Instalar")
    rel_tc    = _av(a, "Relacion De Transformacion Del Tc A Instalar")
    burden_tc = _av(a, "Burden Del Tc A Instalar")
    clase_tc  = _av(a, "Clase Del Tc A Instalar")
    if any(x != "N/A" for x in [tipo_tc, rel_tc, burden_tc, clase_tc]):
        parts = []
        if tipo_tc   != "N/A": parts.append(f"Tipo={tipo_tc}")
        if rel_tc    != "N/A": parts.append(f"Relacion={rel_tc}")
        if burden_tc != "N/A": parts.append(f"Burden={burden_tc} VA")
        if clase_tc  != "N/A": parts.append(f"Clase={clase_tc}")
        lines.append(f"  TCs a instalar: {' | '.join(parts)}\n")

    # TPs a instalar
    tipo_tp   = _av(a, "Tipo De Tp A Instalar")
    rel_tp    = _av(a, "Relacion De Transformacion Del Tp A Instalar")
    burden_tp = _av(a, "Burden Del Tp A Instalar")
    clase_tp  = _av(a, "Clase Del Tp A Instalar")
    if any(x != "N/A" for x in [tipo_tp, rel_tp, burden_tp, clase_tp]):
        parts = []
        if tipo_tp   != "N/A": parts.append(f"Tipo={tipo_tp}")
        if rel_tp    != "N/A": parts.append(f"Relacion={rel_tp}")
        if burden_tp != "N/A": parts.append(f"Burden={burden_tp} VA")
        if clase_tp  != "N/A": parts.append(f"Clase={clase_tp}")
        lines.append(f"  TPs a instalar: {' | '.join(parts)}\n")

    # Telemedida
    antena   = _av(a, "Requiere Antena De Alta Ganancia")
    oper     = _av(a, "Operador De Red Celular")
    ubi_ant  = _av(a, "Ubicacion De La Antena")
    if any(x != "N/A" for x in [antena, oper, ubi_ant]):
        parts = []
        if antena  != "N/A": parts.append(f"Antena alta ganancia: {antena}")
        if oper    != "N/A": parts.append(f"Operador: {oper}")
        if ubi_ant != "N/A": parts.append(f"Ubicacion: {ubi_ant}")
        lines.append(f"  {' | '.join(parts)}\n")

    # Descargos
    descargos = _av(a, "Requiere Descargos Del Or")
    if descargos != "N/A":
        afecta  = _av(a, "El Descargo Afecta A Otros Usuarios")
        cuantos = _av(a, "A Cuantos Usuarios Afecta")
        linea   = f"  Requiere descargos OR: {descargos}"
        if afecta != "N/A": linea += f" | Afecta otros: {afecta}"
        if cuantos not in ("N/A", "0", "0.0"): linea += f" ({cuantos} usuarios)"
        lines.append(linea + "\n")

    maniobra = _av(a, "Maniobra")
    tiempo   = _av(a, "Tiempo De Corte H")
    if maniobra != "N/A" or tiempo != "N/A":
        m_short = maniobra[:80] + "..." if len(maniobra) > 80 else maniobra
        lines.append(f"  Maniobra: {m_short} | Tiempo corte: {tiempo} h\n")

    # Bloque, reubicacion, frontera
    cambio_bloque = _av(a, "Requiere Cambio Bloque")
    tipo_bloque   = _av(a, "Tipo De Bloque De Pruebas A Instalar")
    if cambio_bloque != "N/A":
        lines.append(f"  Cambio bloque pruebas: {cambio_bloque}" +
                     (f" | Tipo: {tipo_bloque}" if tipo_bloque != "N/A" else "") + "\n")

    reubicacion = _av(a, "Reubicacion Equipos De Medida")
    if reubicacion != "N/A": lines.append(f"  Reubicacion equipos: {reubicacion}\n")

    frontera = _av(a, "Es Frontera Comercial")
    if frontera != "N/A": lines.append(f"  Frontera comercial: {frontera}\n")

    seccionamientos = _av(a, "Existen Seccionamientos Externos")
    if seccionamientos != "N/A": lines.append(f"  Seccionamientos externos: {seccionamientos}\n")

    # Trafo
    info_trafo = _av(a, "Info Trafo")
    if info_trafo != "N/A" and info_trafo.startswith("["):
        info_trafo = "Ver datos trafo en sistema"
    if info_trafo != "N/A": lines.append(f"  Info trafo: {info_trafo}\n")

    cap_inst = _av(a, "Capacidad Instalada")
    if cap_inst != "N/A": lines.append(f"  Capacidad instalada: {cap_inst}\n")

    equipos = _av(a, "Equipos Necesarios")
    if equipos != "N/A": lines.append(f"  Equipos necesarios: {equipos}\n")

    pb     = _av(a, "Calculo De Pb")
    pb_val = _av(a, "Valor De Pb Calculado")
    if pb != "N/A" or pb_val != "N/A":
        lines.append(f"  Calculo PB: {pb}" + (f" | Valor: {pb_val}" if pb_val != "N/A" else "") + "\n")

    enlace = _av(a, "Enlace Memoria De Calculo")
    if enlace != "N/A" and enlace.startswith("http"):
        lines.append(f"  Enlace calculo: {enlace}\n")

    obs = _av(a, "Observaciones")
    if obs != "N/A":
        obs_short = obs[:200] + "..." if len(obs) > 200 else obs
        lines.append(f"  *Observaciones ing.:* {obs_short}\n")

    reqs = _av(a, "Requerimientos")
    if reqs != "N/A":
        reqs_short = reqs[:200] + "..." if len(reqs) > 200 else reqs
        lines.append(f"  *Requerimientos:* {reqs_short}\n")

    reqs_add = _av(a, "Requerimientos Adicionales Viabilidad")
    if reqs_add != "N/A":
        lines.append(f"  *Reqs adicionales:* {reqs_add}\n")

    return "".join(lines)


def _comparar_visita_vs_alcance(qa_o_vp, alcance_row):
    """Compare visita previa PDF findings vs engineering alcance."""
    if not alcance_row:
        return ""

    lines = ["\n*Comparacion Visita Previa vs Alcance ingenieria*\n"]
    tuvo_comparacion = False

    # Tipo de medida encontrado
    tipo_vp  = (qa_o_vp.get("tipo_medida") or "").strip().upper()
    tipo_alc = (_av(alcance_row, "Tipo De Medida Encontrado") or "").strip().upper()
    if tipo_vp and tipo_alc and tipo_alc != "N/A":
        ok = tipo_vp == tipo_alc
        lines.append(f"  Tipo medida encontrada: PDF={tipo_vp} | Alcance={tipo_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Factor de medida
    factor_vp  = _v(qa_o_vp.get("factor_medida"), "")
    factor_alc = _av(alcance_row, "Factor De Medida Encontrado")
    if factor_vp and factor_vp != "N/A" and factor_alc != "N/A":
        try:
            ok = abs(float(str(factor_vp).replace(",", ".")) - float(str(factor_alc).replace(",", "."))) < 1
        except Exception:
            ok = _normalizar_serial(factor_vp) == _normalizar_serial(factor_alc)
        lines.append(f"  Factor de medida: PDF={factor_vp} | Alcance={factor_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Serie medidor encontrado
    med_enc    = qa_o_vp.get("medidor_encontrado")
    serie_vp   = ""
    if isinstance(med_enc, dict):
        serie_vp = (med_enc.get("serie") or "").strip()
    elif isinstance(qa_o_vp.get("medidor_enc_serie"), str):
        serie_vp = qa_o_vp.get("medidor_enc_serie", "")
    serie_alc = _av(alcance_row, "Serie Del Medidor")
    if serie_vp and serie_alc != "N/A":
        ok = _normalizar_serial(serie_vp) == _normalizar_serial(serie_alc)
        lines.append(f"  Serie medidor encontrado: PDF={serie_vp} | Alcance={serie_alc} {_check(ok)}\n")
        tuvo_comparacion = True

    # Alertas de alcance
    viable = _av(alcance_row, "Viable Para Instalar")
    if not _viable_ok(viable):
        lines.append(f"  ❌ Ingenieria determino: NO viable para instalar\n")
        tuvo_comparacion = True

    descargos = _av(alcance_row, "Requiere Descargos Del Or")
    if _viable_ok(descargos):
        lines.append(f"  ⚠️ Requiere descargos del OR — coordinar con operador de red\n")
        tuvo_comparacion = True

    antena = _av(alcance_row, "Requiere Antena De Alta Ganancia")
    if _viable_ok(antena):
        oper = _av(alcance_row, "Operador De Red Celular")
        lines.append(f"  ⚠️ Requiere antena de alta ganancia" +
                     (f" | Operador: {oper}" if oper != "N/A" else "") + "\n")
        tuvo_comparacion = True

    return "".join(lines) if tuvo_comparacion else ""


def _construir_cuerpo_visita_previa(acta, qa, encabezado):
    es_exitosa = qa.get("estado_ot") == "EXITOSA"
    falla = qa.get("tipificacion_falla") or {}

    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida encontrada:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n",
        _seccion_tecnico(qa),
        _seccion_observacion_tecnico(qa),
        "\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado"), qa.get("sellos_medidor_encontrado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_tcs_encontrados(qa.get("tcs_encontrados"), qa.get("sellos_tcs_encontrados")),
        _seccion_tps_encontrados(qa.get("tps_encontrados"), qa.get("sellos_tps_encontrados")),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_encontrado")),
        _seccion_cable_control(qa.get("cable_control_encontrado")),
        _seccion_pruebas(qa.get("pruebas_funcionamiento")),
        _seccion_equipo_patron(qa.get("equipo_patron")),
        f"*Diagrama unifilar:* {'Foto presente' if (qa.get('diagrama_unifilar') or {}).get('tiene_foto') else 'Sin foto'}\n",
        f"*Con OR:* {_v(qa.get('or_firma'))}\n",
    ]

    if not es_exitosa and falla.get("causa_raiz"):
        secciones += [
            f"\n*Tipificacion de la OT fallida*\n",
            f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n",
            f"*Responsable:* {_v(falla.get('responsable'))}\n",
            f"*Detalle:* {_v(falla.get('detalle'))}\n",
            f"*Mejora:* {_v(falla.get('mejora'))}\n",
        ]

    alertas = qa.get("alertas_qa") or []
    if alertas:
        secciones.append("\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas) + "\n")

    return "".join(s for s in secciones if s)


def _construir_cuerpo_exitosa(acta, qa, encabezado, serial_wms_asignado=""):
    coincide_wms = qa.get("medidor_coincide_wms")
    tcs_wms  = qa.get("tcs_wms_asignados") or []
    tps_wms  = qa.get("tps_wms_asignados") or []
    fotos_med = qa.get("fotos_medidor")
    fotos_tcs = qa.get("fotos_tcs")
    fotos_tps = qa.get("fotos_tps")
    sellos_med_enc  = qa.get("sellos_medidor_encontrado")
    sellos_med_inst = qa.get("sellos_medidor_instalado")
    sellos_tcs_enc  = qa.get("sellos_tcs_encontrados")
    sellos_tcs_inst = qa.get("sellos_tcs_instalados")
    sellos_tps_enc  = qa.get("sellos_tps_encontrados")
    sellos_tps_inst = qa.get("sellos_tps_instalados")
    secciones = [
        encabezado,
        f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n",
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n",
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n",
        _seccion_tecnico(qa),
        _seccion_observacion_tecnico(qa),
        "\n",
        _seccion_transformador(qa.get("transformador")),
        _seccion_medidor_encontrado(qa.get("medidor_encontrado"), sellos_med_enc),
        _seccion_medidor_instalado(qa.get("medidor_instalado"), coincide_wms, serial_wms_asignado, fotos_med, sellos_med_inst),
        _seccion_medidor_respaldo(qa.get("medidor_respaldo_instalado")),
        _seccion_telemedida_encontrada(qa.get("telemedida_encontrada")),
        _seccion_telemedida_instalada(qa.get("telemedida_instalada")),
        _seccion_totalizador_encontrado(qa.get("totalizador_encontrado")),
        _seccion_totalizador_instalado(qa.get("totalizador_instalado")),
        _seccion_cables_enc(qa.get("cables_potencia_encontrados")),
        _seccion_cables_inst(qa.get("cables_potencia_instalados")),
        _seccion_tcs_encontrados(qa.get("tcs_encontrados"), sellos_tcs_enc),
        _seccion_tc_tp_instalados("TCs instalados", qa.get("tcs_instalados"), tcs_wms, qa.get("tcs_coinciden_wms"), fotos_tcs, sellos_tcs_inst),
        _seccion_tps_encontrados(qa.get("tps_encontrados"), sellos_tps_enc),
        _seccion_tc_tp_instalados("TPs instalados", qa.get("tps_instalados"), tps_wms, qa.get("tps_coinciden_wms"), fotos_tps, sellos_tps_inst),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_encontrado")),
        _seccion_bloque_pruebas(qa.get("bloque_pruebas_instalado"), instalado=True),
        _seccion_cable_control(qa.get("cable_control_encontrado")),
        _seccion_cable_control(qa.get("cable_control_instalado"), instalado=True),
        _seccion_pruebas(qa.get("pruebas_funcionamiento")),
        _seccion_equipo_patron(qa.get("equipo_patron")),
        f"*Diagrama unifilar:* {'Foto presente' if (qa.get('diagrama_unifilar') or {}).get('tiene_foto') else 'Sin foto'}\n",
        f"*Con OR:* {_v(qa.get('or_firma'))}\n\n",
    ]
    alertas = qa.get("alertas_qa") or []
    if alertas:
        secciones.append("\n*Alertas QA:*\n" + "\n".join(f"- {a}" for a in alertas) + "\n")
    return "".join(s for s in secciones if s)


def _construir_cuerpo_fallida(acta, qa, encabezado):
    falla = qa.get("tipificacion_falla") or {}
    return (
        encabezado
        + f"*Codigo interno Bia:* {_v(qa.get('internal_bia_code', acta.get('internal_bia_code')))}\n"
        f"*Tipo de servicio:* {_v(acta.get('Tipo de servicio'))}\n"
        f"*Tipo de medida:* {_v(qa.get('tipo_medida'))}  |  *Factor:* {_v(qa.get('factor_medida'))}\n\n"
        + _seccion_tecnico(qa)
        + _seccion_observacion_tecnico(qa)
        + "\n"
        + f"*Tipificacion de la OT fallida*\n"
        f"*Causa raiz:* {_v(falla.get('causa_raiz'))}\n"
        f"*Responsable:* {_v(falla.get('responsable'))}\n"
        f"*Detalle:* {_v(falla.get('detalle'))}\n"
        f"*Mejora:* {_v(falla.get('mejora'))}\n"
    )


def enviar_slack(acta, resultado_qa, serial_wms_asignado=""):
    url = (config.SLACK_WEBHOOK_URL or "").strip().strip('"').strip("'")
    if not url or "REEMPLAZA" in url:
        print("  Slack: SLACK_WEBHOOK_URL vacio. Se omite envio.")
        return
    if not url.startswith("https://"):
        print(f"  Slack: URL invalida (debe empezar con https://). Se omite envio.")
        return

    es_exitosa = resultado_qa.get("estado_ot") == "EXITOSA"
    es_visita  = "previa" in (acta.get("Tipo de servicio") or "").lower()
    color      = "#2eb886" if es_exitosa else "#e01e5a"
    if es_visita:
        color = "#0066cc"
    estado_txt = "EXITOSA" if es_exitosa else "FALLIDA"
    planner    = resultado_qa.get("planner", "N/A")
    or_norm    = resultado_qa.get("or_norm", acta.get("OR_NORM", "N/A"))

    user_ids = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id = user_ids.get(planner)
    if slack_id:
        encabezado = f"<@{slack_id}>\n\n"
    else:
        encabezado = f"*{planner}*\n\n"

    if es_visita:
        cuerpo = _construir_cuerpo_visita_previa(acta, resultado_qa, encabezado)
    elif es_exitosa:
        cuerpo = _construir_cuerpo_exitosa(acta, resultado_qa, encabezado, serial_wms_asignado)
    else:
        cuerpo = _construir_cuerpo_fallida(acta, resultado_qa, encabezado)

    if len(cuerpo) > 7800:
        cuerpo = cuerpo[:7800] + "\n... (truncado)"

    tipo_titulo = "VISITA PREVIA" if es_visita else estado_txt
    payload = {
        "attachments": [{
            "color": color,
            "title": f"[{tipo_titulo}] {acta.get('title', 'Sin titulo')}",
            "fields": [
                {"title": "Tipo",    "value": _v(acta.get("Tipo de servicio")), "short": True},
                {"title": "Medida",  "value": _v(resultado_qa.get("tipo_medida")), "short": True},
                {"title": "OR",      "value": _v(or_norm),  "short": True},
                {"title": "Planner", "value": _v(planner),  "short": True},
                {"title": "Fecha",   "value": _v(acta.get("start")), "short": True},
                {"title": "Empresa", "value": _v(acta.get("company_name")), "short": True},
            ],
            "text":   cuerpo,
            "footer": _v(acta.get("address"), ""),
            "mrkdwn_in": ["text"],
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if 200 <= r.status_code < 300:
            print("  Slack enviado.")
        else:
            print(f"  ERROR Slack: HTTP {r.status_code} -> {r.text[:200]}")
    except Exception as e:
        print(f"  ERROR Slack: {e}")


def enviar_slack_alcance(co_code, alcance_row, visita_data):
    """Send Slack notification when a new engineering alcance is generated."""
    url = (config.SLACK_WEBHOOK_URL or "").strip().strip('"').strip("'")
    if not url or not url.startswith("https://"):
        return

    planner  = config.PLANNER_DEFAULT
    user_ids = getattr(config, "SLACK_USER_IDS", {}) or {}
    slack_id = user_ids.get(planner)
    encabezado = f"<@{slack_id}>\n\n" if slack_id else f"*{planner}*\n\n"

    ot_ref = (visita_data or {}).get("ot_nombre", "")

    cuerpo = (
        encabezado
        + f"*Codigo interno Bia:* {co_code}\n"
        + (f"*OT Visita Previa relacionada:* {ot_ref}\n" if ot_ref else "")
        + "\n"
        + _seccion_alcance_ingenieria(alcance_row)
        + (_comparar_visita_vs_alcance(visita_data, alcance_row) if visita_data else "")
    )

    if len(cuerpo) > 7800:
        cuerpo = cuerpo[:7800] + "\n... (truncado)"

    viable = _av(alcance_row, "Viable Para Instalar")
    medida_inst = _av(alcance_row, "Tipo De Medida A Instalar")
    fecha_alc   = _av(alcance_row, "Creado El")[:10]

    payload = {
        "attachments": [{
            "color": "#9b59b6",
            "title": f"[ALCANCE INGENIERIA] {co_code}",
            "fields": [
                {"title": "Medida a instalar", "value": medida_inst, "short": True},
                {"title": "Viable",            "value": viable,      "short": True},
                {"title": "Fecha alcance",     "value": fecha_alc,   "short": True},
                {"title": "VP registrada",     "value": "Si" if visita_data else "No", "short": True},
            ],
            "text":      cuerpo,
            "mrkdwn_in": ["text"],
        }]
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if 200 <= r.status_code < 300:
            print(f"  Slack alcance enviado: {co_code}")
        else:
            print(f"  ERROR Slack alcance: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ERROR Slack alcance: {e}")
