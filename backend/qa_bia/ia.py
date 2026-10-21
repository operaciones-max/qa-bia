"""Analisis de actas con Claude (Anthropic).
"""
import base64
import json

import anthropic

from . import config
from .estado import _activar_cooldown_llm, _cargar_cooldown_llm
from .prompts import _system_prompt_full, _system_prompt_lite

_cliente = None


def cliente_claude():
    """Cliente de Anthropic, creado la primera vez que se usa."""
    global _cliente
    if _cliente is None:
        _cliente = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _cliente


def es_limite_de_uso(error):
    """True si la API respondio 429 (rate limit) o 529 (sobrecargada)."""
    return isinstance(error, anthropic.APIStatusError) and error.status_code in (429, 529)


def extraer_json(texto):
    """Parsea el JSON de la respuesta aunque venga envuelto en ```json o con texto alrededor."""
    if "```json" in texto:
        texto = texto.split("```json")[1].split("```")[0].strip()
    elif "```" in texto:
        texto = texto.split("```")[1].split("```")[0].strip()
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio != -1 and fin != -1:
        texto = texto[inicio:fin + 1]
    return json.loads(texto)


def _bloques_imagen(imagenes):
    return [{
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(img).decode("ascii"),
        },
    } for img in imagenes]


def _etiqueta_tipo(tipo_servicio):
    """Tipo de servicio para el prompt full. Antes todo lo que no era instalacion
    se mandaba como VISITA PREVIA (ej. Normalizacion medida)."""
    t = (tipo_servicio or "").strip()
    if "previa" in t.lower():
        return "VISITA PREVIA"
    if "nstala" in t:
        return "INSTALACION"
    return t.upper() or "SIN TIPO"


def _llamar_claude(etiqueta, sistema, contenido, max_tokens):
    """Llama a Claude con el system prompt cacheado. Devuelve el texto de la respuesta."""
    respuesta = cliente_claude().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        temperature=0.1,
        system=[{
            "type": "text",
            "text": sistema,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }],
        messages=[{"role": "user", "content": contenido}],
    )
    try:
        u = respuesta.usage
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        print(f"  Claude {etiqueta} tokens: in={u.input_tokens} out={u.output_tokens} cache_w={cw} cache_r={cr}")
    except Exception:
        pass
    return "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()


def analizar_acta_lite(texto_pdf, tipo_servicio, estado_electricista,
                       internal_bia_code="", imagenes_pdf=None):
    """QA lite para Retencion/Energy Solutions. Si imagenes_pdf tiene contenido,
    incluye vision (para PQR/VICO/Emergencia que tienen actas fisicas)."""
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    texto_msg = (
        f"TIPO DE SERVICIO: {tipo_servicio}\n"
        f"RESULTADO EN APP: {'EXITOSA' if es_exitosa else 'FALLIDA'}\n"
        f"CODIGO INTERNO BIA: {internal_bia_code}\n\n"
        f"--- TEXTO DEL ACTA ---\n{texto_pdf[:8000]}"
    )
    imagenes = (imagenes_pdf or [])[:4]
    contenido = _bloques_imagen(imagenes) + [{"type": "text", "text": texto_msg}] if imagenes else texto_msg

    cd = _cargar_cooldown_llm()
    if cd:
        print(f"  Claude en cooldown ({cd['razon']}) - se omite analisis lite.")
        return None

    try:
        texto = _llamar_claude("lite", _system_prompt_lite(), contenido, 2000 if imagenes else 1500)
        return extraer_json(texto)
    except json.JSONDecodeError:
        print(f"  JSON invalido lite de {config.CLAUDE_MODEL}")
        return None
    except Exception as e:
        if es_limite_de_uso(e):
            _activar_cooldown_llm(str(e))
            return None
        print(f"  ERROR Claude lite: {e}")
        return None


def analizar_acta(texto_pdf, tipo_servicio, estado_electricista,
                  internal_bia_code="", serial_asignado_wms="", marca_asignada_wms="",
                  tcs_asignados_wms=None, tps_asignados_wms=None, imagenes_pdf=None):
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    es_visita  = "previa" in tipo_servicio.lower()
    debe_comparar_wms = es_exitosa and not es_visita and bool(serial_asignado_wms)
    wms_info = serial_asignado_wms if debe_comparar_wms else "No aplica"
    marca_wms = marca_asignada_wms if debe_comparar_wms else ""
    tcs_asignados_wms = tcs_asignados_wms or []
    tps_asignados_wms = tps_asignados_wms or []
    tcs_wms_info = ", ".join(tcs_asignados_wms) if (debe_comparar_wms and tcs_asignados_wms) else "No aplica"
    tps_wms_info = ", ".join(tps_asignados_wms) if (debe_comparar_wms and tps_asignados_wms) else "No aplica"
    imagenes = imagenes_pdf or []

    user_msg = (
        f"TIPO DE SERVICIO: {_etiqueta_tipo(tipo_servicio)}\n"
        f"RESULTADO EN APP: {'EXITOSA' if es_exitosa else 'FALLIDA'}\n"
        f"CODIGO INTERNO BIA: {internal_bia_code}\n"
        f"MEDIDOR ASIGNADO EN SISTEMA WMS: {wms_info} {('(' + marca_wms + ')') if marca_wms else ''}\n"
        f"TCs ASIGNADOS EN WMS (semidirecta/indirecta): {tcs_wms_info}\n"
        f"TPs ASIGNADOS EN WMS (solo indirecta): {tps_wms_info}\n"
        + (f"SE ADJUNTAN IMAGENES: {len(imagenes)} pagina(s) del acta.\n" if imagenes
           else "SIN IMAGENES: solo el texto del acta.\n")
        + f"\n--- TEXTO DEL ACTA ---\n{texto_pdf[:12000]}"
    )
    contenido = _bloques_imagen(imagenes) + [{"type": "text", "text": user_msg}] if imagenes else user_msg

    cd = _cargar_cooldown_llm()
    if cd:
        print(f"  Claude en cooldown ({cd['razon']}) hasta {cd['until']} - se omite analisis.")
        return None

    texto = ""
    try:
        texto = _llamar_claude("full", _system_prompt_full(), contenido, 4096)
        return extraer_json(texto)
    except json.JSONDecodeError:
        print(f"  JSON invalido de Claude: {texto[:150]}")
        return None
    except Exception as e:
        if es_limite_de_uso(e):
            cd = _activar_cooldown_llm(str(e))
            print(f"  Limite Claude detectado ({cd['razon']}). Cooldown hasta {cd['until']}. Se aborta.")
            return None
        print(f"  ERROR Claude: {e}")
        return None
