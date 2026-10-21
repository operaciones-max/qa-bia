# Contrato backend ↔ frontend: tabla `actas_qa`

El backend escribe y el frontend (dashboard) lee y edita la revisión. No hay API
entre ellos: este documento es el contrato. Si se cambia una columna, hay que
actualizar los dos lados y este archivo.

Clave única: `ot_id`. El backend hace *upsert* (`on_conflict=ot_id`,
`resolution=merge-duplicates`).

## Columnas que escribe el backend

Fuente: `backend/qa_bia/supabase.py` → `enviar_supabase()`.

| Columna | Tipo | Origen |
|---|---|---|
| `ot_id` | text | id de la OT en Metabase (clave) |
| `ot_nombre` | text | `title` de la OT |
| `procesado_en` | timestamp (ISO, UTC) | Momento del análisis |
| `tipo_servicio` | text | Metabase |
| `fecha_ejecucion` | text | `start` en Metabase |
| `internal_bia_code` | text | Código CO del cliente |
| `contract_id` | text | HubSpot (vía Metabase 71842) |
| `or_norm` | text | Operador de red |
| `planner` | text | Según OR (`config.OR_PLANNERS`) |
| `empresa`, `direccion` | text | Metabase |
| `estado_ot` | `EXITOSA` \| `FALLIDA` | Estado del técnico en Metabase (no lo decide la IA) |
| `qa_track` | `Activacion` \| `Retencion` \| `Energy Solutions` | Según tipo de servicio |
| `tipo_medida`, `factor_medida` | text | IA |
| `tecnico_nombre` | text | Metabase (si viene), si no IA |
| `tecnico_empresa` | `BIA` \| `CONTRATISTA` \| null | Metabase `contractor_name` |
| `contratista_nombre` | text | Metabase `contractor_name` |
| `medidor_encontrado_serie`, `medidor_encontrado_marca` | text | IA |
| `medidor_instalado_serie`, `medidor_instalado_marca` | text | IA |
| `medidor_coincide_wms`, `tcs_coinciden_wms`, `tps_coinciden_wms` | bool \| null | Recalculado por código contra WMS |
| `sellos_medidor_encontrado`, `sellos_medidor_instalado`, `sellos_tcs_encontrados`, `sellos_tcs_instalados` | int \| null | IA (ver hallazgo #3 en hallazgos.md) |
| `tiene_tcs`, `tiene_tps`, `tiene_telemedida`, `tiene_diagrama_unifilar` | bool | IA |
| `or_firma` | `SI` \| `NO` | IA |
| `validacion_coherente` | `COHERENTE` \| `INCOHERENTE` \| `INCOMPLETO` | IA |
| `errores_qa`, `alertas_qa` | jsonb (lista de textos) | IA, filtrado por `validaciones.py` |
| `tipificacion_causa_raiz`, `tipificacion_responsable` | text | IA, ajustado al catálogo (`catalogo.py`) |
| `wms_asignado` | bool | ¿Hay medidor asignado en WMS? |
| `wms_medidor_serial`, `wms_medidor_marca` | text | WMS |
| `wms_completo` | jsonb | `{medidor, tcs[], tps[]}` de WMS |
| `wms_marca_coincide_alcance` | bool \| null | Marca WMS vs marca del alcance |
| `serial_medidor_factura_anterior` | text | Factura anterior (regex / IA) |
| `medidor_coincide_factura_anterior` | bool \| null | Serial factura vs medidor encontrado |
| `factura_anterior_express` | bool \| null | La factura dice "express" |
| `factura_anterior_estado` | `ok` \| `ok_sin_serial` \| `borrosa` \| `no_disponible` | Resultado de la extracción |
| `estado_app_ops` | `Exitosa` \| `Fallida` \| null | Cierre formal en App Ops |
| `estado_revision` | `pendiente` \| `cerrada` | Ver abajo |
| `tiene_alcance`, `alcance_viable`, `alcance_medida_instalar`, `alcance_completo` | bool / text / text / jsonb | Alcance de ingeniería |
| `resultado_qa_completo` | jsonb | Respuesta completa de la IA tras las validaciones |

## Columnas que el backend actualiza después

| Quién | Columnas | Cuándo |
|---|---|---|
| `reconciliar_estado_app_ops()` | `estado_app_ops`, `estado_revision` | Al inicio de **cada** corrida, para todas las actas |
| `actualizar_supabase_alcance()` | `tiene_alcance`, `alcance_viable`, `alcance_medida_instalar`, `alcance_completo` | Cuando aparece un alcance nuevo para una visita previa |
| `scripts/limpiar_facturas.py` | `serial_medidor_factura_anterior`, `medidor_coincide_factura_anterior`, `factura_anterior_estado` → null | Manual, antes de reprocesar |

## Lo que edita el frontend

Según los comentarios del código, el revisor puede marcar una OT como FALLIDA
desde el dashboard. **Pendiente de confirmar con el código de Lovable** qué
columnas escribe exactamente.

Hay que tener en cuenta dos cosas al definirlo:

- Si el backend reprocesa un acta (por ejemplo, con los scripts de limpieza), el
  *upsert* sobrescribe **todas** las columnas de la tabla de arriba, incluidas
  las que haya editado el revisor.
- `estado_app_ops` y `estado_revision` se recalculan en cada corrida, así que
  cualquier cambio manual en ellas se pierde.

Recomendación: que el frontend escriba solo en columnas propias (por ejemplo
`revision_estado_manual`, `revision_comentario`, `revisado_por`, `revisado_en`)
que el backend nunca toque.
