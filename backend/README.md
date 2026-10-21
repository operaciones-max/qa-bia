# Backend — motor de QA

Paquete Python `qa_bia`. Se ejecuta desde esta carpeta con `python -m qa_bia`.

## Flujo de una corrida

1. **Carga de fuentes** (`metabase.py`): inventario WMS, alcances de ingeniería,
   facturas anteriores (HubSpot vía Metabase) y estado de cierre de App Ops.
2. **Reconciliación** (`supabase.py`): actualiza `estado_app_ops` y
   `estado_revision` de las actas ya guardadas según App Ops.
3. **Actas nuevas** (`metabase.py`): filtra por estado, fecha
   (`QA_FECHA_INICIO`), que tengan PDF y que no estén en `state/actas_procesadas.json`.
   Máximo `QA_MAX_ACTAS_POR_RUN` por corrida.
4. **Por cada acta** (`pipeline.procesar_acta`):
   - lee el PDF (`pdf.py`);
   - la analiza con Claude (`ia.py` + `prompts.py`): QA *full* para
     Activación y normalizaciones con WMS, QA *lite* para el resto (con visión
     para PQR / visita conjunta / emergencia);
   - aplica reglas defensivas (`validaciones.py`, `catalogo.py`): el estado de
     la OT lo manda Metabase, no la IA;
   - cruza seriales con WMS y con la factura anterior (`facturas.py`);
   - guarda en Supabase (`supabase.py`) y marca el acta como procesada (`estado.py`).
5. **Alcances nuevos** (`pipeline.verificar_nuevos_alcances`): marca en Supabase
   las visitas previas que ya tienen alcance de ingeniería.

## Módulos

| Capa | Módulo | Qué hace |
|---|---|---|
| Configuración | `config.py` | Valores de producción + overrides por variables de entorno / `.env` |
| Entrada | `metabase.py` | Descarga CSVs de Metabase (actas, WMS, alcances, facturas, App Ops) |
| Entrada | `pdf.py` | Texto (pdfplumber) e imágenes (PyMuPDF) de los PDFs |
| Análisis | `prompts.py` | System prompts de Claude (lite y full) |
| Análisis | `ia.py` | Llamadas a Claude y parseo del JSON |
| Análisis | `facturas.py` | Serial del medidor en la factura anterior (regex, y Claude si falla) |
| Reglas | `catalogo.py` | Catálogo de tipificaciones, tracks de QA, planner por OR |
| Reglas | `validaciones.py` | Post-validaciones sobre la respuesta de la IA |
| Salida | `supabase.py` | Escritura en `actas_qa` (contrato con el frontend) |
| Salida | `reportes.py` | JSON local por acta en `reportes_qa/` (no se versiona) |
| Salida | `slack.py` | Mensajes de Slack — **deshabilitado**, no se llama |
| Estado | `estado.py` | Archivos JSON de `state/` y cooldown del LLM |
| Orquestación | `pipeline.py` | `procesar_acta()` y `main()` |
| Utilidades | `utils.py` | Fecha actual, normalización de seriales |

Los nombres de funciones se mantuvieron iguales al `qa_bia.py` original para
poder rastrear cambios en el historial.

## Configuración

Copiar `.env.example` a `.env` (no se versiona). Variables:

| Variable | Default | Uso |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (obligatoria) | Claude |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` | vacío | Si faltan, no se escribe en Supabase |
| `METABASE_API_KEY` | vacío | Facturas anteriores y reconciliación con App Ops |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Modelo |
| `QA_MODO_PRUEBA` | `false` | Procesa solo `QA_ACTAS_PRUEBA` actas |
| `QA_ACTAS_PRUEBA` | `2` | |
| `QA_MODO_UNICO` | `true` | `false` = queda en bucle cada 5 min |
| `QA_FECHA_INICIO` | `2026-05-10` | Ignora actas anteriores |
| `QA_FECHA_INICIO_ALCANCES` | `2026-04-30` | Ignora alcances anteriores |
| `QA_MAX_ACTAS_POR_RUN` | `30` | Tope por corrida |
| `QA_STATE_DIR` | `state` | Carpeta de estado (relativa a `backend/`). En local usar `state-local` para no tocar el de producción |

## Correr en local sin tocar producción

```bash
cp .env.example .env    # trae QA_MODO_PRUEBA=true y QA_STATE_DIR=state-local
# completar solo ANTHROPIC_API_KEY
python -m qa_bia
```

Analiza 2 actas reales de Metabase, no escribe en Supabase y deja el avance en
`state-local/` (ignorado por git).

## Scripts de mantenimiento

Se corren desde GitHub Actions (botón manual) o en local desde `backend/`:

- `python -m scripts.limpiar_facturas` — fuerza reprocesar visitas previas para
  volver a extraer la factura anterior.
- `python -m scripts.limpiar_pqr_vico_emerg` — fuerza reprocesar PQR / visita
  conjunta / emergencia.

Los dos modifican `state/` y Supabase.

## Pruebas

```bash
pip install -r requirements-dev.txt
python -m pytest
```
