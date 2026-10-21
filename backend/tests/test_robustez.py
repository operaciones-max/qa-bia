"""Pruebas de las correcciones de la revision (docs/hallazgos.md)."""
import anthropic
import pytest

from qa_bia import supabase
from qa_bia.ia import _etiqueta_tipo, es_limite_de_uso, extraer_json


class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data
        self.text = ""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _ErrorApi(anthropic.APIStatusError):
    def __init__(self, status_code):  # sin response real de la API
        self.status_code = status_code


@pytest.fixture
def con_supabase(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/rest/v1/")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")


def test_etiqueta_tipo_no_convierte_todo_en_visita_previa():
    assert _etiqueta_tipo("Visita previa") == "VISITA PREVIA"
    assert _etiqueta_tipo("Instalación") == "INSTALACION"
    assert _etiqueta_tipo("Normalización medida") == "NORMALIZACIÓN MEDIDA"
    assert _etiqueta_tipo("Alta ingenieria") == "ALTA INGENIERIA"


def test_extraer_json_tolera_bloques_y_texto_alrededor():
    assert extraer_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extraer_json('Aqui va: {"a": {"b": 2}} fin') == {"a": {"b": 2}}


def test_limite_de_uso_solo_por_429_y_529():
    assert es_limite_de_uso(_ErrorApi(429))
    assert es_limite_de_uso(_ErrorApi(529))
    assert not es_limite_de_uso(_ErrorApi(500))
    assert not es_limite_de_uso(ValueError("could not generate rate"))


def test_enviar_supabase_informa_si_guardo(monkeypatch, con_supabase):
    acta = {"id": "ot-1", "title": "INST_1"}
    monkeypatch.setattr(supabase.requests, "post", lambda *a, **k: _Resp(201))
    assert supabase.enviar_supabase(acta, {}) is True
    monkeypatch.setattr(supabase.requests, "post", lambda *a, **k: _Resp(500))
    assert supabase.enviar_supabase(acta, {}) is False


def test_enviar_supabase_sin_configurar_no_bloquea(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert supabase.enviar_supabase({"id": "ot-1"}, {}) is True


def test_reconciliacion_lee_todas_las_paginas(monkeypatch, con_supabase):
    total = supabase.TAM_PAGINA + 3
    offsets = []

    def get(url, params, **kw):
        offsets.append(params["offset"])
        n = min(supabase.TAM_PAGINA, total - params["offset"])
        return _Resp(200, [{"ot_id": f"ot-{params['offset'] + i}"} for i in range(n)])

    monkeypatch.setattr(supabase.requests, "get", get)
    filas = supabase._leer_todas("https://x.supabase.co", "k", "ot_id")
    assert len(filas) == total
    assert offsets == [0, supabase.TAM_PAGINA]
