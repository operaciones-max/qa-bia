# Backend — motor de QA

Programa Go que se ejecuta desde la raíz del repo con `go run ./backend/cmd/qa`
(en producción, desde GitHub Actions).

## Flujo de una corrida

1. **Carga de fuentes** (`metabase`): inventario WMS, alcances de ingeniería,
   facturas anteriores (HubSpot vía Metabase) y estado de cierre de App Ops.
2. **Reconciliación** (`supabase`): actualiza `estado_app_ops` y
   `estado_revision` de las actas ya guardadas según App Ops.
3. **Actas nuevas** (`metabase`): filtra por estado, fecha
   (`QA_FECHA_INICIO`), que tengan PDF y que no estén en `state/actas_procesadas.json`.
   Máximo `QA_MAX_ACTAS_POR_RUN` por corrida.
4. **Por cada acta** (`pipeline.ProcesarActa`):
   - lee el PDF (`pdf`, con MuPDF);
   - la analiza con Claude (`ia`): QA *full* para Activación y normalizaciones
     con WMS, QA *lite* para el resto (con visión para PQR / visita conjunta /
     emergencia);
   - aplica reglas defensivas (`validaciones`, `catalogo`): el estado de la OT
     lo manda Metabase, no la IA;
   - cruza seriales con WMS y con la factura anterior (`facturas`);
   - guarda en Supabase (`supabase`) y, solo si se guardó, marca el acta como
     procesada (`estado`). Si falla, se reintenta en la próxima corrida.
5. **Alcances nuevos** (`pipeline.VerificarNuevosAlcances`): marca en Supabase
   las visitas previas que ya tienen alcance de ingeniería.

## Paquetes

| Capa | Paquete | Qué hace |
|---|---|---|
| Programas | `cmd/qa`, `cmd/limpiar-facturas`, `cmd/limpiar-pqr-vico-emerg`, `cmd/extraccion` | Puntos de entrada |
| Configuración | `config` | Valores de producción + overrides por variables de entorno / `backend/.env` |
| Entrada | `metabase` | CSVs de Metabase (actas, WMS, alcances, facturas, App Ops) |
| Entrada | `pdf` | Texto e imágenes de los PDFs con MuPDF ([go-fitz](https://github.com/gen2brain/go-fitz)) |
| Análisis | `ia` | Prompts (texto en `ia/prompts/`) y llamadas a Claude con el SDK oficial de Go |
| Análisis | `facturas` | Serial del medidor en la factura anterior (regex, y Claude si falla) |
| Reglas | `catalogo` | Catálogo de tipificaciones, tracks de QA, planner por OR |
| Reglas | `validaciones` | Post-validaciones sobre la respuesta de la IA |
| Salida | `supabase` | Escritura en `actas_qa` (contrato con el frontend) |
| Salida | `reportes` | JSON local por acta en `backend/reportes_qa/` (no se versiona) |
| Estado | `estado` | Archivos JSON de `state/` y cooldown del LLM |
| Orquestación | `pipeline` | `ProcesarActa()` y `Main()` |
| Servicio | `extraccion` | Servicio HTTP de extracción de documentos (OCR con Claude) |
| Utilidades | `dato`, `util` | JSON libre de la IA, fechas, normalización de seriales |

La respuesta de Claude es un JSON libre que se maneja como `map[string]any`
(paquete `dato`), con la misma semántica que tenía la versión en Python.

## Claude

- SDK `github.com/anthropics/anthropic-sdk-go` **v1.78.0** (versión de API
  `2023-06-01`), modelo `claude-haiku-4-5-20251001` (configurable con `CLAUDE_MODEL`).
- System prompt cacheado 1 hora y `temperature` 0.1.
- Los prompts están en [`ia/prompts/`](ia/prompts/README.md), incluido el
  evaluador de cierre v1 (veredicto EXITOSA / FALLIDA / PENDIENTE), que todavía
  no está conectado al pipeline.
- Ante un 429 o 529 se activa un cooldown (`state/llm_cooldown.json`) y no se
  vuelve a llamar hasta que vence.
- La API `2026-10-21` (SDK v2) ya no acepta `temperature`: ver
  [docs/hallazgos.md](../docs/hallazgos.md) antes de actualizar el SDK.

## Configuración

Copiar `backend/.env.example` a `backend/.env` (no se versiona). Variables:

| Variable | Default | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (obligatoria) | Claude |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | vacío | Si faltan, no se escribe en Supabase |
| `METABASE_API_KEY` | vacío | Facturas anteriores y reconciliación con App Ops |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Modelo |
| `QA_MODO_PRUEBA` | `false` | Procesa solo `QA_ACTAS_PRUEBA` actas |
| `QA_ACTAS_PRUEBA` | `2` | |
| `QA_MODO_UNICO` | `true` | `false` = queda en bucle cada 5 min |
| `QA_FECHA_INICIO` | `2026-05-10` | Ignora actas anteriores |
| `QA_FECHA_INICIO_ALCANCES` | `2026-04-30` | Ignora alcances anteriores |
| `QA_MAX_ACTAS_POR_RUN` | `30` | Tope por corrida |
| `QA_PAUSA_ENTRE_ACTAS_SEGUNDOS` | `20` | Pausa entre llamadas a Claude |
| `QA_STATE_DIR` | `backend/state` | Carpeta de estado. En local usar `backend/state-local` para no tocar la de producción |
| `QA_CARPETA_REPORTES` | `backend/reportes_qa` | Reportes locales |
| `METABASE_BASE_URL`, `ANTHROPIC_BASE_URL` | URLs reales | Solo para pruebas contra servidores falsos |

## Correr en local sin tocar producción

```bash
cp backend/.env.example backend/.env    # trae QA_MODO_PRUEBA=true y QA_STATE_DIR=backend/state-local
# completar solo ANTHROPIC_API_KEY
go run ./backend/cmd/qa
```

Analiza 2 actas reales de Metabase, no escribe en Supabase y deja el avance en
`backend/state-local/` (ignorado por git).

## Scripts de mantenimiento

Se corren desde GitHub Actions (botón manual) o en local desde la raíz:

- `go run ./backend/cmd/limpiar-facturas`: fuerza reprocesar las visitas
  previas para volver a extraer la factura anterior.
- `go run ./backend/cmd/limpiar-pqr-vico-emerg`: fuerza reprocesar PQR,
  visita conjunta y emergencia.

Los dos modifican `state/` y Supabase.

## Servicio de extracción de documentos

`go run ./backend/cmd/extraccion` levanta un servicio HTTP aparte del QA:
recibe el link de un PDF o una imagen y el JSON esperado, y devuelve ese JSON
con los datos del documento (RUT, cámara de comercio…). Usa los mismos
paquetes `pdf`, `ia` y `supabase`. Detalle, API y configuración en
[docs/servicio-extraccion.md](../docs/servicio-extraccion.md).

## Pruebas

```bash
go test ./backend/...
```
