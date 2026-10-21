"""Pruebas de las reglas deterministicas (sin red ni IA).

Correr desde backend/:  python -m pytest
"""
from qa_bia.catalogo import _clasificar_qa_track, _requiere_wms_comparison, _validar_tipificacion
from qa_bia.facturas import extraer_serial_por_patron
from qa_bia.utils import _normalizar_serial
from qa_bia.validaciones import (
    _enforce_reglas_medida_servicio, _limpiar_errores_fantasma, _simplificar_fallida,
    _validar_coincidencia_wms,
)


def test_normalizar_serial_ignora_ceros_espacios_y_guiones():
    assert _normalizar_serial("00 123-456") == "123456"
    assert _normalizar_serial("ab_12/3") == "AB123"
    assert _normalizar_serial(None) == ""


def test_clasificar_qa_track():
    assert _clasificar_qa_track("Visita previa") == "Activacion"
    assert _clasificar_qa_track("Instalación") == "Activacion"
    assert _clasificar_qa_track("Mantenimiento preventivo") == "Energy Solutions"
    assert _clasificar_qa_track("PQR") == "Retencion"


def test_wms_solo_para_activacion_y_normalizacion_exacta():
    assert _requiere_wms_comparison("Instalación", "Activacion")
    assert _requiere_wms_comparison("Normalización medida", "Retencion")
    assert not _requiere_wms_comparison("Normalizacion Telemedidas", "Retencion")


def test_serial_factura_por_patron():
    assert extraer_serial_por_patron("No. Medidor: 8091012800") == ("8091012800", "Enel")
    texto_afinia = "Datos de la Factura\nCliente X\nMedidor\n12345678-MC983"
    assert extraer_serial_por_patron(texto_afinia) == ("12345678", "AFINIA (Datos de la Factura)")
    assert extraer_serial_por_patron("sin datos") == (None, None)


def test_tipificacion_se_ajusta_al_catalogo():
    qa = {"estado_ot": "FALLIDA",
          "tipificacion_falla": {"causa_raiz": "permisos de INGRESO", "responsable": "x"}}
    _validar_tipificacion(qa)
    assert qa["tipificacion_falla"] == {"causa_raiz": "Permisos de ingreso",
                                        "responsable": "Account executive"}


def test_tipificacion_inventada_cae_a_observacion_o_default():
    qa = {"estado_ot": "FALLIDA", "observacion_tecnico_verbatim": "Cliente pide reprogramar",
          "tipificacion_falla": {"causa_raiz": "algo inventado"}}
    _validar_tipificacion(qa)
    assert qa["tipificacion_falla"]["causa_raiz"] == "Agendamiento cliente"

    qa = {"estado_ot": "FALLIDA", "tipificacion_falla": {"causa_raiz": "zzz"}}
    _validar_tipificacion(qa)
    assert qa["tipificacion_falla"]["causa_raiz"] == "Información faltante/ erronea en acta"


def test_directa_desactiva_tcs_tps_y_visita_previa_desactiva_instalados():
    qa = {"tipo_medida": "DIRECTA", "tcs_encontrados": {"aplica": True},
          "medidor_instalado": {"aplica": True}, "fotos_tcs": 3}
    _enforce_reglas_medida_servicio(qa, "Visita previa")
    assert qa["tcs_encontrados"]["aplica"] is False
    assert qa["medidor_instalado"]["aplica"] is False
    assert qa["fotos_tcs"] is None


def test_coincidencia_wms_por_conjunto_normalizado():
    qa = {"tipo_medida": "SEMIDIRECTA",
          "medidor_instalado": {"serie": "000123456"},
          "tcs_instalados": {"seriales": ["tc 2", "TC-1", "TC-3"]}}
    _validar_coincidencia_wms(qa, "123456", ["TC-1", "TC2"], [], True)
    assert qa["medidor_coincide_wms"] is True
    assert qa["tcs_coinciden_wms"] is True
    assert qa["tps_coinciden_wms"] is None


def test_errores_fantasma_y_fallida_simplificada():
    qa = {"tipo_medida": "DIRECTA", "estado_ot": "FALLIDA", "or_firma": "NO",
          "validaciones": {"errores_encontrados": ["No se reporta lectura", "TCs sin sellos", "Error real"]},
          "alertas_qa": ["Error real", "Alerta menor"],
          "tipificacion_falla": {"cinco_por_que": ["1"]}}
    _limpiar_errores_fantasma(qa, "Instalación")
    assert qa["validaciones"]["errores_encontrados"] == ["Error real"]
    assert qa["alertas_qa"] == ["Alerta menor"]
    _simplificar_fallida(qa)
    assert qa["validaciones"]["errores_encontrados"] == []
    assert qa["alertas_qa"] == ["El Operador de Red NO firmó el acta."]
    assert qa["tipificacion_falla"]["cinco_por_que"] == []
