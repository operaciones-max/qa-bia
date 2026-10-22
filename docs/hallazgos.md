# Revisión del código — hallazgos (octubre 2026)

Hallazgos de la revisión completa del QA (originalmente `qa_bia.py`, hoy en Go)
y su estado. Las rutas apuntan a los paquetes Go de `backend/` y `frontend/`.

| # | Hallazgo | Prioridad | Estado |
|---|---|---|---|
| 1 | Repo público expone datos operativos | Alta | Parcial: falta una decisión |
| 2 | Si falla Supabase, el acta se perdía | Alta | Corregido |
| 3 | El QA full pedía verificar fotos que no recibe | Alta | Corregido |
| 4 | Normalizaciones se analizaban como "VISITA PREVIA" | Alta | Corregido |
| 5 | Instrucciones contradictorias en los prompts | Media | Corregido |
| 6 | El backend pisaba las ediciones del revisor | Media | Corregido |
| 7 | La reconciliación no paginaba | Media | Corregido |
| 8 | El estado vive en git y los errores de push se ignoran | Media | Pendiente |
| 9 | Dependencias sin fijar | Media | Corregido |
| 10 | Detección de rate limit por texto | Baja | Corregido |
| 11 | PDF descargado dos veces | Baja | Corregido |
| 12 | Código muerto y nombres heredados | Baja | Corregido |
| 13 | `datetime.utcnow()` deprecado | Baja | Resuelto con el paso a Go |
| 14 | No había CI de pruebas | Baja | Corregido |
| 15 | El QA en Python dejó de funcionar con el SDK de Anthropic 1.x | Alta | Resuelto con el paso a Go |
| 16 | La API de Claude `2026-10-21` ya no acepta `temperature` | Media | **Decisión pendiente** |

## Pendientes

### 1. El repo es público y expone datos operativos — parcial

`operaciones-max/qa-bia` es **público**. Cualquiera puede ver:
- las URLs de las preguntas públicas de Metabase (`backend/config`), que
  descargan actas (direcciones, empresas, técnicos, PDFs), inventario WMS y alcances;
- `backend/state/visitas_previas.json` y `backend/state/facturas_extraidas.json`,
  con técnicos, seriales y URLs de facturas de clientes;
- los logs de GitHub Actions, que también son públicos.

**Hecho:** el backend ya no imprime parte de la `METABASE_API_KEY` en los logs.

**Falta (decisión del dueño del repo):** hacer el repo privado y regenerar los
enlaces públicos de Metabase. Todo esto sigue en el historial de git aunque se
borre de la versión actual.

### 8. El estado vive en git — pendiente

El bot commitea `backend/state/` en cada corrida con `git push || true`. Si el
push falla, el avance se pierde sin aviso y se reprocesan actas (más tokens).
La solución de fondo es usar Supabase como fuente de verdad (las actas ya
guardadas en `actas_qa`) y dejar de commitear estado.

### 16. La API `2026-10-21` ya no acepta `temperature` — decisión pendiente

Desde el 2026-10-21, la API de Claude en su versión nueva rechaza (error 400)
cualquier request con `temperature`, `top_p` o `top_k`. El QA manda
`temperature: 0.1` en todas sus llamadas para que las respuestas sean más
consistentes.

**Hoy:** el backend usa el SDK de Go **v1.78.0**, que sigue en la versión de
API `2023-06-01` y acepta `temperature`. Funciona igual que antes.

**La decisión** (para cuando se quiera pasar al SDK v2):
1. **Quitar `temperature`** (recomendado si el resultado sigue siendo bueno):
   Claude Haiku 4.5 pasa a muestrear con el valor por defecto (1.0). Conviene
   comparar el resultado sobre un grupo de actas reales antes de decidir.
2. **Quedarse en el SDK v1 / API `2023-06-01`** mientras no se valide el punto 1.

Para pasar al SDK v2 hay que cambiar el import a
`github.com/anthropics/anthropic-sdk-go/v2` y quitar `Temperature` en
`backend/ia/claude.go`. Guía: https://platform.claude.com/docs/en/api/migration-2026-10-21

## Corregidos

### 2. Si falla Supabase, el acta se perdía

`supabase.Guardar()` y `supabase.ActualizarAlcance()` devuelven si guardaron, y
`pipeline.ProcesarActa()` solo marca el acta (y su alcance) como procesada
cuando se guardó; si no, se reintenta en la próxima corrida.

### 3. El QA full pedía verificar fotos que no recibe

El prompt decía que siempre recibía imágenes, pero solo se mandaba texto. Ahora:
- distingue los dos casos y, sin imágenes, prohíbe inventar sellos, lecturas
  o verificaciones (usa null);
- el mensaje dice explícitamente "SIN IMAGENES" o "SE ADJUNTAN IMAGENES";
- si se sube `pdf.MaxPaginasVision`, las imágenes sí se mandan. Hoy está en 0
  para no gastar tokens.

### 4. Normalizaciones se analizaban como "VISITA PREVIA"

`ia.EtiquetaTipo()` manda el tipo real ("NORMALIZACIÓN MEDIDA",
"ALTA INGENIERIA"…), y el prompt tiene una regla para esos tipos.

### 5. Instrucciones contradictorias en los prompts

- Se quitó la regla de "override a FALLIDA", que el código siempre descartaba.
- El ejemplo del prompt usa una causa que sí está en el catálogo.
- El prompt lite ya no dice "2 páginas" cuando se mandan 4.

### 6. El backend pisaba las ediciones del revisor

La revisión humana vive en columnas `revision_*` que el backend nunca
escribe, y el upsert solo toca las columnas que envía. Verificado en Postgres.

### 7, 9–14

- **7.** `supabase.LeerTodas()` lee de a 1000 filas hasta terminar, y los PATCH
  que fallan se cuentan como error.
- **9.** Versiones exactas en `go.mod`/`go.sum` (anthropic-sdk-go v1.78.0, go-fitz v1.28.2).
- **10.** El límite de uso se detecta por código HTTP 429/529 (`ia.EsLimiteDeUso`).
- **11.** El PDF se descarga una sola vez.
- **12.** Eliminado el código de Slack y otro código muerto; nombres de Groq/Gemini actualizados.
- **13.** Ya no aplica (era de Python).
- **14.** Workflow `CI` con `gofmt`, `go vet`, pruebas y build.

### 15. El QA en Python dejó de funcionar con el SDK de Anthropic 1.x

El SDK de Python `anthropic` 1.0 (agosto 2026) eliminó el parámetro
`temperature` de `messages.create()`. Con la dependencia sin fijar
(`anthropic>=0.40.0` en `main`), cualquier corrida nueva instala la 2.x y
**todas** las llamadas a Claude fallan. Las actas no se pierden (quedan
pendientes), pero el QA no audita nada. La versión en Go no tiene este problema.

## Migración a Go: cómo se verificó

Antes de borrar el Python se corrieron las dos versiones contra el mismo
servidor falso (Metabase, PDFs, Supabase y API de Claude), con los mismos datos
y el mismo estado inicial, incluyendo un escenario con fallas de Supabase:

- **Idénticos:**
  - las 34 requests (rutas, parámetros y cuerpos);
  - las 7 llamadas a Claude (mismo system prompt byte a byte, modelo,
    `max_tokens`, `temperature`, caché de 1 hora y versión de API);
  - los 6 reportes;
  - `actas_procesadas.json`, `alcances_procesados.json` y `facturas_extraidas.json`;
  - la salida de los scripts de limpieza.
- **Diferencias conocidas:**
  - **Texto de los PDFs:** pdfplumber y MuPDF pueden cortar líneas distinto. En
    las pruebas el texto fue igual salvo espacios; con actas reales puede haber
    pequeñas diferencias de formato en lo que recibe Claude.
  - **Orden de claves en `visitas_previas.json`:** en las entradas nuevas,
    las claves anidadas que vienen de la IA quedan en orden alfabético. El
    contenido es el mismo.
