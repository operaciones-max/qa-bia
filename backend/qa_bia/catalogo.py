"""Catalogo de tipificaciones BIA y reglas de clasificacion por tipo de servicio.
"""
import re

from . import config


TIPIFICACIONES_CATALOGO = {
    # Account executive
    "Cliente abandona proceso": "Account executive",
    "Cliente no conoce alcance de la actividad": "Account executive",
    "Documentacion incompleta": "Account executive",
    "OR no conoce requerimiento descargos": "Account executive",
    "OR no tiene conocimiento de la actividad": "Account executive",
    "Propietario no conoce alcance de la actividad": "Account executive",
    "Datos de ubicación erroneo": "Account executive",
    "Permisos de ingreso": "Account executive",
    "Error en la creación de la OT": "Account executive",
    "Falta activar frontera para realizar actividad": "Account executive",
    "La OT ya fue realizada": "Account executive",
    "OT Duplicada": "Account executive",
    "OT Fuera de SLA": "Account executive",
    "No se cancelo actividad apesar de solicitud del cliente": "Account executive",
    # Operador de red
    "Falla en la red, debe normalizar OR": "Operador de red",
    "OR exige adecuaciones adicionales": "Operador de red",
    "OR no asiste o llega tarde": "Operador de red",
    "OR no cumple requerimientos de la actividad": "Operador de red",
    "Permisos del municipio": "Operador de red",
    # Safety
    "Documentacion SST": "Safety Specialist",
    # Coordinador
    "Coordinador no confirma actividad": "Coordinador",
    "Contratista/ Tecnico no llega a la hora programada": "Coordinador",
    "Información faltante/ erronea en acta": "Coordinador",
    # Technical expert
    "Confirmacion de Alcance en actividad": "Technical expert",
    "Error en alcance": "Technical expert",
    # Contratista
    "Fallas en el Alistamiento Operativo": "Contratista",
    "Contratista no asiste o llega tarde": "Contratista",
    "Configuracion del modem": "Contratista",
    # Supply
    "Certificados de equipo": "Supply",
    "Equipos en sitio": "Supply",
    "Averia de equipo pre instalacion": "Supply",
    "Sim card": "Supply",
    # Centro comercial
    "Permisos propietario": "Centro comercial",
    # Cliente
    "Falla cliente-Gestion": "Cliente",
    "Agendamiento cliente": "Cliente",
    "Demora en el acceso": "Cliente",
    "Acceso a gabinete": "Cliente",
    "Cliente retira los equipos": "Cliente",
    "Cliente en reclamación": "Cliente",
    "Cliente realizo pago": "Cliente",
    "Cliente suspendido": "Cliente",
    "Cliente fuera del mercado BIA": "Cliente",
    "Cliente en cobro juridico": "Cliente",
    "Acuerdo de pago en punto": "Cliente",
    # Factor externo
    "Animales impiden acceso a la medida": "Factor externo",
    "Riesgo electrico": "Factor externo",
    "Codigo duplicado": "Factor externo",
    "Lluvias": "Factor externo",
    "Acceso a la medida": "Factor externo",
    "Manifestaciones / bloqueos / carretera cerrada": "Factor externo",
    "Cubertura en datos moviles": "Factor externo",
    "Medidor averiado": "Factor externo",
    "No hay registro del medidor bia encontrado": "Factor externo",
    "No se encuentra medidor": "Factor externo",
    "No se encuentra modem": "Factor externo",
    "Modem averiado": "Factor externo",
    "Telemedida conecta y normalizada antes de visita": "Factor externo",
    "Equipos averiados": "Factor externo",
    "Se requiere acompañamiento policial": "Factor externo",
    "Sin acceso a la plataforma para pagar": "Factor externo",
    "Medida es compartida": "Factor externo",
    "Predio desocupado, imposibilidad de acceso a la medida": "Factor externo",
}


def _validar_tipificacion(qa):
    """Asegura que causa_raiz este en el catalogo oficial y mapea responsable.
    Si la AI propuso un responsable combinado (con /), se respeta agregando el del catalogo."""
    if qa.get("estado_ot") != "FALLIDA":
        return
    falla = qa.get("tipificacion_falla") or {}
    causa_orig = (falla.get("causa_raiz") or "").strip()
    responsable_orig = (falla.get("responsable") or "").strip()

    # Match exacto (case-insensitive)
    causa_match = None
    causa_lower = causa_orig.lower()
    for k in TIPIFICACIONES_CATALOGO:
        if k.lower() == causa_lower:
            causa_match = k
            break

    # Fuzzy match: buscar la del catalogo con mas overlap de palabras
    if not causa_match and causa_orig:
        causa_words = set(re.findall(r"\w+", causa_lower))
        mejor_score = 0
        for k in TIPIFICACIONES_CATALOGO:
            k_words = set(re.findall(r"\w+", k.lower()))
            score = len(causa_words & k_words)
            if score > mejor_score:
                mejor_score = score
                causa_match = k
        # Si el mejor match es muy debil, mejor default
        if mejor_score < 2:
            causa_match = None

    if not causa_match:
        # Si AI invento causa sin overlap, intenta inferir desde la observacion
        observ = (qa.get("observacion_tecnico_verbatim") or "").lower()
        for keyword, causa_inferred in (
            ("reprogr", "Agendamiento cliente"),
            ("no atiende", "Agendamiento cliente"),
            ("no puede atender", "Agendamiento cliente"),
            ("ausente", "Falla cliente-Gestion"),
            ("no hay quien", "Falla cliente-Gestion"),
            ("permiso", "Permisos de ingreso"),
            ("ingreso", "Permisos de ingreso"),
            ("acceso", "Acceso a la medida"),
            ("lluvia", "Lluvias"),
            ("riesgo electrico", "Riesgo electrico"),
            ("manifestacion", "Manifestaciones / bloqueos / carretera cerrada"),
            ("bloqueo", "Manifestaciones / bloqueos / carretera cerrada"),
            ("medidor averiado", "Medidor averiado"),
            ("modem averiado", "Modem averiado"),
            ("no se encuentra medidor", "No se encuentra medidor"),
            ("no se encuentra modem", "No se encuentra modem"),
            ("or no asist", "OR no asiste o llega tarde"),
            ("or no llego", "OR no asiste o llega tarde"),
            ("operador de red no", "OR no asiste o llega tarde"),
            ("contratista no asist", "Contratista no asiste o llega tarde"),
        ):
            if keyword in observ:
                causa_match = causa_inferred
                break

    if not causa_match:
        causa_match = "Información faltante/ erronea en acta"

    responsable_cat = TIPIFICACIONES_CATALOGO[causa_match]
    # Si la AI propuso responsable combinado (con /) y al menos uno coincide
    # con el del catalogo, respetar la combinacion. Si no, usar el del catalogo.
    if "/" in responsable_orig and responsable_cat.lower() in responsable_orig.lower():
        responsable_final = responsable_orig
    else:
        responsable_final = responsable_cat

    falla["causa_raiz"]  = causa_match
    falla["responsable"] = responsable_final
    qa["tipificacion_falla"] = falla


def _clasificar_qa_track(tipo_servicio):
    """Clasifica el tipo de servicio en uno de los 3 tracks de QA."""
    t = (tipo_servicio or "").lower()
    # Energy Solutions: mantenimiento, bancos de condensadores, BIA Monitor
    if any(k in t for k in ("mantenimiento", "condensador", "banco", "bia monitor", "monitor", "carro canasta")):
        return "Energy Solutions"
    # Activacion: visitas previas + instalaciones + alta ingenieria
    if "previa" in t or "instala" in t or "alta ingenier" in t:
        return "Activacion"
    # Resto: Retencion
    return "Retencion"


def _tipo_necesita_vision_lite(tipo_servicio):
    """True si el tipo de servicio usa actas FISICAS manuscritas dentro del PDF
    (Registro Fotografico Acta). Aplica para PQR, Visita Conjunta, Emergencia."""
    t = (tipo_servicio or "").lower()
    return any(k in t for k in ("pqr", "visita conjunta", "vico", "emergencia", "alrt"))


def _requiere_wms_comparison(tipo_servicio, qa_track):
    """True si el acta debe comparar contra WMS asignado."""
    if qa_track == "Activacion":
        return True
    t = (tipo_servicio or "").strip().lower()
    # Normalizacion medida y Normalizacion Emergencias tienen equipos asignados.
    # Match EXACTO para no confundir con 'Normalizacion Telemedidas' (contiene 'medida' como substring).
    return t in ("normalizacion medida", "normalización medida",
                 "normalizacion emergencias", "normalización emergencias")


def identificar_planner(or_norm):
    for or_key, planner in config.OR_PLANNERS.items():
        if or_key.upper() in or_norm.upper():
            return planner
    return config.PLANNER_DEFAULT
