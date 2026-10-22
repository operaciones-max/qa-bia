# Prompts de Claude

El texto de los prompts vive en esta carpeta y se embebe en el binario
(`backend/ia/prompts.go`). Para cambiar un prompt basta con editar el archivo;
no hay que tocar Go.

| Archivo | Función en Go | Uso |
|---|---|---|
| `qa_full.md` | `ia.SystemPromptFull()` | Extracción del acta: Activación y normalizaciones con WMS |
| `qa_lite.md` | `ia.SystemPromptLite()` | Extracción del acta: Retención y Energy Solutions |
| `agentes/` | `ia.SystemPromptAgente(codigo)` | Subagentes de cierre, uno por tipo de OT: veredicto independiente (`backend/cierre`) |
| `extraccion.md` | `ia.SystemPromptExtraccion()` | Servicio de extracción de documentos (`backend/extraccion`) y OCR de la factura anterior |
| `fotos_equipos.md` | `ia.SystemPromptFotosEquipos()` | OCR de las fotos de medidores, TCs y TPs (`backend/verificacion`) |

Marcadores que se reemplazan al cargar el prompt:

- `{{CATALOGO}}`: la lista del catálogo de `backend/catalogo`;
- `{{CATALOGO_POR_RESPONSABLE}}`: las mismas causas, agrupadas por responsable;
- `{{OT_CODIGO}}`, `{{OT_NOMBRE}}`, `{{OT_LINEA}}`, `{{FAMILIA}}`, `{{OT}}`: los
  datos y las reglas del tipo de OT (subagentes).

## Subagentes de cierre por tipo de OT

Cada tipo de OT (45, en `backend/catalogo/ots.go`) tiene su subagente. Su
prompt se arma con tres capas:

```
agentes/comun.md                  reglas de todos: dos juicios, fuentes, lectura del acta,
                                  5 porqués, catálogo, formato de salida
agentes/familias/<familia>.md     reglas de su familia: previa, ejecucion, normalizacion,
                                  emergencia, retiro, verificacion, cartera, gestion
agentes/ots/<CODIGO>.md           objetivo de la OT, qué debe traer el acta y sus reglas propias
```

Si una regla de la OT choca con la general, manda la de la OT. El backend
sabe qué subagente usar por el código al inicio del título de la OT
(`VIPE_44339_3986E7` → VIPE), con `catalogo.TipoOTDeTitulo`.

Para ajustar un subagente se edita su archivo en `agentes/ots/`. Qué está en
borrador y qué falta validar con operaciones está en
[docs/agentes-ot.md](../../../docs/agentes-ot.md).

`agentes/comun.md` es el evaluador de cierre v1 (abajo) sin sus reglas
propias de VIPE, INST y DESX, que pasaron a `agentes/ots/`. Además, ahora
recibe el TEXTO DEL ACTA completo, para las OTs cuyo formulario no extrae el
QA (condensadores, BIA Monitor, termografía…).

## Origen: evaluador de cierre v1

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
| `service_type` INST / VIPE / DESX | Código al inicio del título de la OT; un subagente por código |
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

### Cómo está conectado

`backend/cierre` arma el caso con los bloques que define `agentes/comun.md`:

- `TIPO DE OT`, `ESTADO REPORTADO` y `CODIGO INTERNO BIA`;
- `ACTA EXTRAIDA`: antes de `SimplificarFallida` y sin `estado_ot` ni la
  tipificación de la extracción;
- `TEXTO DEL ACTA`, `ALCANCE`, `EQUIPOS ASIGNADOS` y `NOTAS`;
- `VALIDACIONES DEL BACKEND`: WMS, factura anterior y `verificacion_equipos`.

Con eso llama a `ia.EvaluarCierre` y valida la respuesta:

- PENDIENTE solo si la OT lo admite;
- la tipificación se ajusta con `catalogo.ValidarTipificacion`.

El resultado queda en `resultado_qa_completo.cierre_ia` y el dashboard lo
muestra en el detalle. `estado_ot` sigue siendo el estado de App Ops.

Pendiente:

- **Comparar con WMS también cuando el técnico reportó fallo**, fuera de VIPE e
  INST: hoy `ValidarCoincidenciaWMS` solo compara si reportó éxito.
- **Columnas propias** si se quiere filtrar por el veredicto del subagente.
