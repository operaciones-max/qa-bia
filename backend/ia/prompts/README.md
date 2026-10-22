# Prompts de Claude

El texto de los prompts vive en esta carpeta y se embebe en el binario
(`backend/ia/prompts.go`). Para cambiar un prompt basta con editar el archivo;
no hay que tocar Go.

| Archivo | Función en Go | Uso |
|---|---|---|
| `qa_full.md` | `ia.SystemPromptFull()` | Extracción del acta: Activación y normalizaciones con WMS |
| `qa_lite.md` | `ia.SystemPromptLite()` | Extracción del acta: Retención y Energy Solutions |
| `evaluador_cierre_v1.md` | `ia.SystemPromptEvaluadorCierre()` | Veredicto independiente de cierre. **Todavía no lo usa el pipeline** |

Marcadores que se reemplazan al cargar el prompt:

- `{{CATALOGO}}`: la lista del catálogo de `backend/catalogo`;
- `{{CATALOGO_POR_RESPONSABLE}}`: las mismas causas, agrupadas por responsable.

## Evaluador de cierre v1

Viene del prompt `v1_closure_evaluator`, que fue escrito para otro backend.
Se conservaron todas sus reglas de negocio:

- los dos juicios separados (veredicto vs. acta completa);
- el estado pendiente solo para INST;
- el pago en sitio en DESX;
- los bloques exigibles de la VIPE;
- el equipo ajeno → Contratista;
- los 5 porqués y las fuentes NO DISPONIBLE.

Lo que cambió es cómo recibe los datos y cómo responde, para que encaje con
este repo.

### Equivalencias

| `v1_closure_evaluator` | Aquí |
|---|---|
| Acta normalizada (`sections` / `tables` / `fields`) | JSON que extrae `qa_full.md` / `qa_lite.md` del PDF |
| `execution_flags` | `aplica`, `se_instalo`, `tiene` de cada bloque, `pruebas_funcionamiento.se_realizaron`, `equipo_patron.se_uso` |
| `observations` | `observacion_tecnico_verbatim`. `observaciones_tecnicas` y `observacion_automatica` las escribe la IA, no el técnico |
| `visual_evidence` (`present`) | `fotos_medidor`, `fotos_tcs`, `fotos_tps`, `diagrama_unifilar.tiene_foto`, `serie_coincide_foto`, `or_firma`. No hay firma del cliente |
| `found_vs_installed` | Pares `*_encontrado(s)` / `*_instalado(s)` |
| `system_conditions` | `tipo_medida`, `factor_medida` (un solo valor, sin par encontrado/instalado) |
| `missing_form_fields` | No existe: el evaluador toma como faltantes los null de los bloques declarados ejecutados |
| `status_flags` | `ESTADO REPORTADO` = `electrician_status_id` de App Ops |
| `service_type` INST / VIPE / DESX | Texto del tipo de servicio de Metabase (`Instalación`, `Visita previa`, `Desconexión`) |
| Alcance (texto libre) | Fila del alcance de ingeniería de Metabase (`metabase.Alcances`), como pares `campo: valor` |
| Equipos (SKU asignados) | `metabase.EquiposWMS` (medidor, TCs, TPs) |
| Notas | Sin fuente: hoy siempre `(NO DISPONIBLE: …)` |
| Validaciones estructurales | `medidor_coincide_wms`, `tcs_coinciden_wms`, `tps_coinciden_wms`, `medidor_coincide_factura_anterior` (+ `factura_anterior_estado`) |
| Tool `get_work_order_reasons` (CMS) | Catálogo embebido en el prompt (`backend/catalogo`) |
| `reason` / `actor` / `reason_type` | `causa_raiz` / `responsable` (el catálogo no tiene `reason_type`) |
| Salida `AgentClosureOutput` (`app/agent/schemas.py`) | JSON en texto, que se lee con `ia.ExtraerJSON` |
| `result`: successful / failed / pending | `veredicto`: `EXITOSA` / `FALLIDA` / `PENDIENTE` |
| `scope_met` | `alcance_cumplido` |
| `acta_complete` / `missing_fields` | `acta_completa` / `campos_faltantes` |
| `pending_items` | `pendientes` (mismos textos: `Normalización Medida`, `Normalización Telemedida`, `Legalización`) |
| `findings` | `hallazgos` (incluye los límites de la evaluación) |
| `five_whys` | `tipificacion_falla.cinco_por_que` |
| `closure_comment` | `comentario_cierre` |

### Diferencias de criterio (decididas al adaptarlo)

- **Fotos:** hoy la extracción no recibe imágenes (`pdf.MaxPaginasVision = 0`).
  Las fotos se cuentan por los timestamps del texto. Un `null` se toma como
  "no se pudo determinar", nunca como evidencia en contra.
- **Legalización:** no hay un campo "¿el OR asistió?". Se usa `or_firma = "NO"`
  confirmado con la observación del técnico.
- **Requerimientos de instalación (VIPE):** no tienen campo propio. Se buscan en
  la observación del técnico.
- **Factura anterior:** es una validación propia de este repo. Una serie distinta
  en la factura se reporta "por confirmar", no basta para FALLIDA.
- **QA lite:** el JSON no trae bloques de equipos. Su ausencia no cuenta contra el
  técnico.

### Qué falta para conectarlo al pipeline

1. **Una segunda llamada a Claude** en `pipeline.ProcesarActa`, después de la
   extracción. Hay que armar el mensaje con los bloques que define el prompt
   (`TIPO DE SERVICIO`, `ESTADO REPORTADO`, `CODIGO INTERNO BIA`, `ACTA EXTRAIDA`,
   `ALCANCE`, `EQUIPOS ASIGNADOS`, `NOTAS`, `VALIDACIONES DEL BACKEND`). Sube el
   costo: una llamada más por acta.
2. **Mandarle el JSON antes de `validaciones.SimplificarFallida`**, que en las
   fallidas borra `errores_encontrados` y las alertas. Sin `estado_ot` ni
   `tipificacion_falla`, para que no los copie.
3. **Comparar con WMS también cuando el técnico reportó fallo:** hoy
   `ValidarCoincidenciaWMS` solo compara si reportó éxito.
4. **Guardar el veredicto aparte de `estado_ot`:** `estado_ot` sigue siendo el
   estado de App Ops. Por ejemplo, columnas nuevas `veredicto_ia`,
   `acta_completa`, `pendientes`, `comentario_cierre` (migración + contrato en
   `docs/contrato-supabase.md`), o dentro de `resultado_qa_completo`.
5. **Validar la tipificación:** `catalogo.ValidarTipificacion` hoy mira
   `estado_ot`. Hay que hacerlo mirar `veredicto` para corregir causas fuera del
   catálogo.
6. **Mostrarlo en el dashboard** junto al estado de App Ops y la revisión humana.
