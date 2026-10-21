"""Analisis de actas con Claude (Anthropic).
"""
import json
from anthropic import Anthropic

from . import config
from .estado import _activar_cooldown_llm, _cargar_cooldown_llm
from .prompts import _system_prompt_full, _system_prompt_lite

_cliente = None


def cliente_claude():
    """Cliente de Anthropic, creado la primera vez que se usa."""
    global _cliente
    if _cliente is None:
        _cliente = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _cliente


def analizar_acta_lite(texto_pdf, tipo_servicio, estado_electricista,
                       internal_bia_code="", imagenes_pdf=None):
    """QA lite para Retencion/Energy Solutions. Si imagenes_pdf tiene contenido,
    incluye vision (para PQR/VICO/Emergencia que tienen actas fisicas)."""
    import base64
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    sistema = _system_prompt_lite()
    texto_msg = (
        f"TIPO DE SERVICIO: {tipo_servicio}\n"
        f"RESULTADO EN APP: {'EXITOSA' if es_exitosa else 'FALLIDA'}\n"
        f"CODIGO INTERNO BIA: {internal_bia_code}\n\n"
        f"--- TEXTO DEL ACTA ---\n{texto_pdf[:8000]}"
    )

    # Construir content: si hay imagenes, va multimodal; si no, solo texto.
    if imagenes_pdf:
        content = []
        for i, img_bytes in enumerate(imagenes_pdf[:4]):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(img_bytes).decode("ascii"),
                },
            })
        content.append({"type": "text", "text": texto_msg})
        user_content = content
    else:
        user_content = texto_msg

    cd = _cargar_cooldown_llm()
    if cd:
        print(f"  Claude en cooldown ({cd['razon']}) - se omite analisis lite.")
        return None

    try:
        respuesta = cliente_claude().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=2000 if imagenes_pdf else 1500,
            temperature=0.1,
            system=[{
                "type": "text",
                "text": sistema,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }],
            messages=[{"role": "user", "content": user_content}],
        )
        try:
            u = respuesta.usage
            cw = getattr(u, "cache_creation_input_tokens", 0) or 0
            cr = getattr(u, "cache_read_input_tokens", 0) or 0
            print(f"  Claude lite tokens: in={u.input_tokens} out={u.output_tokens} cache_w={cw} cache_r={cr}")
        except Exception:
            pass
        texto_r = "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()
        if "```json" in texto_r:
            texto_r = texto_r.split("```json")[1].split("```")[0].strip()
        elif "```" in texto_r:
            texto_r = texto_r.split("```")[1].split("```")[0].strip()
        inicio = texto_r.find("{"); fin = texto_r.rfind("}")
        if inicio != -1 and fin != -1:
            texto_r = texto_r[inicio:fin+1]
        return json.loads(texto_r)
    except json.JSONDecodeError:
        print(f"  JSON invalido lite de {config.CLAUDE_MODEL}")
        return None
    except Exception as e:
        msg = str(e); msg_lower = msg.lower()
        if "429" in msg or "rate" in msg_lower or "rate_limit" in msg_lower or "overloaded" in msg_lower:
            _activar_cooldown_llm(msg)
            return None
        print(f"  ERROR Claude lite: {e}")
        return None


def analizar_acta(texto_pdf, tipo_servicio, estado_electricista,
                  internal_bia_code="", serial_asignado_wms="", marca_asignada_wms="",
                  tcs_asignados_wms=None, tps_asignados_wms=None, imagenes_pdf=None):
    tipo_label = "INSTALACION" if "nstala" in tipo_servicio else "VISITA PREVIA"
    es_exitosa = estado_electricista in config.ESTADOS_EXITOSOS
    es_visita  = "previa" in tipo_servicio.lower()
    debe_comparar_wms = es_exitosa and not es_visita and bool(serial_asignado_wms)
    wms_info = serial_asignado_wms if debe_comparar_wms else "No aplica"
    marca_wms = marca_asignada_wms if debe_comparar_wms else ""
    tcs_asignados_wms = tcs_asignados_wms or []
    tps_asignados_wms = tps_asignados_wms or []
    tcs_wms_info = ", ".join(tcs_asignados_wms) if (debe_comparar_wms and tcs_asignados_wms) else "No aplica"
    tps_wms_info = ", ".join(tps_asignados_wms) if (debe_comparar_wms and tps_asignados_wms) else "No aplica"

    sistema = _system_prompt_full()
    user_msg = (
        f"TIPO DE SERVICIO: {tipo_label}\n"
        f"RESULTADO EN APP: {'EXITOSA' if es_exitosa else 'FALLIDA'}\n"
        f"CODIGO INTERNO BIA: {internal_bia_code}\n"
        f"MEDIDOR ASIGNADO EN SISTEMA WMS: {wms_info} {('(' + marca_wms + ')') if marca_wms else ''}\n"
        f"TCs ASIGNADOS EN WMS (semidirecta/indirecta): {tcs_wms_info}\n"
        f"TPs ASIGNADOS EN WMS (solo indirecta): {tps_wms_info}\n\n"
        f"--- TEXTO DEL ACTA ---\n{texto_pdf[:12000]}"
    )

    cd = _cargar_cooldown_llm()
    if cd:
        print(f"  Claude en cooldown ({cd['razon']}) hasta {cd['until']} - se omite analisis.")
        return None

    texto = ""
    try:
        respuesta = cliente_claude().messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            temperature=0.1,
            system=[{
                "type": "text",
                "text": sistema,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }],
            messages=[{"role": "user", "content": user_msg}],
        )
        try:
            u = respuesta.usage
            cw = getattr(u, "cache_creation_input_tokens", 0) or 0
            cr = getattr(u, "cache_read_input_tokens", 0) or 0
            print(f"  Claude full tokens: in={u.input_tokens} out={u.output_tokens} cache_w={cw} cache_r={cr}")
        except Exception:
            pass
        texto = "".join(b.text for b in respuesta.content if hasattr(b, "text")).strip()
        if "```json" in texto:
            texto = texto.split("```json")[1].split("```")[0].strip()
        elif "```" in texto:
            texto = texto.split("```")[1].split("```")[0].strip()
        inicio = texto.find("{")
        fin    = texto.rfind("}")
        if inicio != -1 and fin != -1:
            texto = texto[inicio:fin+1]
        return json.loads(texto)
    except json.JSONDecodeError:
        print(f"  JSON invalido de Claude: {texto[:150]}")
        return None
    except Exception as e:
        msg = str(e)
        msg_lower = msg.lower()
        es_rate_limit = ("429" in msg or "rate_limit" in msg_lower or "rate limit" in msg_lower
                         or "overloaded" in msg_lower or "quota" in msg_lower)
        if es_rate_limit:
            cd = _activar_cooldown_llm(msg)
            print(f"  Limite Claude detectado ({cd['razon']}). Cooldown hasta {cd['until']}. Se aborta.")
            return None
        print(f"  ERROR Claude: {e}")
        return None
