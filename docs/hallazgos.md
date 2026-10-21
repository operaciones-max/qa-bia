# Revisión del código — hallazgos (octubre 2026)

Hallazgos de la revisión completa de `qa_bia.py`, hecha al separarlo en
módulos, y su estado. Las rutas apuntan al código en `backend/qa_bia/`.

| # | Hallazgo | Prioridad | Estado |
|---|---|---|---|
| 1 | Repo público expone datos operativos | Alta | Parcial: falta una decisión |
| 2 | Si falla Supabase, el acta se pierde | Alta | Corregido |
| 3 | El QA full pide verificar fotos que no recibe | Alta | Corregido |
| 4 | Normalizaciones se analizaban como "VISITA PREVIA" | Alta | Corregido |
| 5 | Instrucciones contradictorias en los prompts | Media | Corregido |
| 6 | El backend pisaba las ediciones del revisor | Media | Corregido |
| 7 | La reconciliación no paginaba | Media | Corregido |
| 8 | El estado vive en git y los errores de push se ignoran | Media | Pendiente |
| 9 | Dependencias sin fijar | Media | Corregido |
| 10 | Detección de rate limit por texto | Baja | Corregido |
| 11 | PDF descargado dos veces | Baja | Corregido |
| 12 | Código muerto y nombres heredados | Baja | Corregido |
| 13 | `datetime.utcnow()` deprecado | Baja | Corregido |
| 14 | No había CI de pruebas | Baja | Corregido |

## 1. El repo es público y expone datos operativos — parcial

`operaciones-max/qa-bia` es **público**. Cualquiera puede ver:
- las URLs de las preguntas públicas de Metabase (`config.py`), que descargan
  actas (direcciones, empresas, técnicos, PDFs), inventario WMS y alcances;
- `state/visitas_previas.json` y `state/facturas_extraidas.json`, con
  técnicos, seriales y URLs de facturas de clientes;
- los logs de GitHub Actions, que también son públicos.

**Hecho:** el backend ya no imprime parte de la `METABASE_API_KEY` en los logs.

**Falta (decisión del dueño del repo):** hacer el repo privado y regenerar los
enlaces públicos de Metabase. Todo esto sigue en el historial de git aunque se
borre de la versión actual.

## 2. Si falla Supabase, el acta se pierde — corregido

Antes el acta se marcaba como procesada aunque la escritura en Supabase
fallara, y nunca se reintentaba. Ahora `enviar_supabase()` y
`actualizar_supabase_alcance()` devuelven si guardaron, y `pipeline.py` solo
marca el acta o el alcance cuando se guardó. Lo mismo se corrigió para los
alcances de visitas previas, que tenían el mismo problema.

## 3. El QA full pedía verificar fotos que no recibe — corregido

El prompt decía "VAS A RECIBIR ... imágenes" y pedía contar sellos
visualmente, pero solo se mandaba texto. Ahora:
- el prompt distingue los dos casos y, sin imágenes, prohíbe inventar conteos
  o verificaciones visuales (usa null);
- `serie_coincide_foto` puede ser null cuando no hay forma de verificarlo;
- el mensaje dice explícitamente "SIN IMAGENES" o "SE ADJUNTAN IMAGENES";
- si algún día se sube `pdf.MAX_PAGINAS_VISION`, las imágenes sí se mandan.
  Hoy sigue en 0 para no gastar tokens.

## 4. Normalizaciones se analizaban como "VISITA PREVIA" — corregido

Ahora Claude recibe el tipo real ("NORMALIZACIÓN MEDIDA", "ALTA INGENIERIA"…),
y el prompt tiene una regla para esos tipos: se tratan como instalación.

## 5. Instrucciones contradictorias — corregido

- Se quitó la "regla de override a FALLIDA": el código siempre la descartaba
  porque el estado lo manda App Ops. El prompt ahora pide copiar el estado de
  App Ops.
- El ejemplo "gold" usa una causa que sí está en el catálogo ("Error en alcance").
- El prompt lite ya no dice "2 páginas" cuando se mandan 4.

## 6. El backend pisaba las ediciones del revisor — corregido

Con el dashboard propio, la revisión humana vive en columnas `revision_*` que
el backend nunca escribe. El upsert solo toca las columnas que envía, así que
reprocesar un acta no borra la revisión. Esto se verificó en Postgres. Ver
[contrato-supabase.md](contrato-supabase.md).

## 7. La reconciliación no paginaba — corregido

`supabase._leer_todas()` lee de a 1000 filas hasta terminar. Además, las
actualizaciones que fallan ahora se cuentan como error en vez de como éxito.

## 8. El estado vive en git — pendiente

El bot sigue commiteando `backend/state/` en cada corrida, con `git push || true`.
La solución de fondo es sacar el estado de git y usar Supabase como fuente de
verdad (las actas ya guardadas en `actas_qa`). Es un cambio más grande: queda
para cuando se decida.

## 9–14. Resto — corregido

- **9.** `requirements.txt` con versiones exactas. Hacía falta: anthropic 2.0 y
  pymupdf 2.0 salieron esta misma semana y el QA los habría instalado solo.
- **10.** El límite de uso se detecta por código HTTP (429/529) con las
  excepciones del SDK, no buscando "rate" en el texto del error.
- **11.** El PDF se descarga una sola vez.
- **12.** Eliminado `slack.py` (~750 líneas sin uso), `_override_fallida_si_incompleto`,
  `TIPOS_SERVICIO_VALIDOS`, `MODO_BACKFILL` y los ids de Slack. Renombrado
  `PAUSA_GROQ_SEGUNDOS` → `PAUSA_ENTRE_ACTAS_SEGUNDOS` y los mensajes "Gemini".
- **13.** `utils.ahora_utc()` reemplaza a `datetime.utcnow()`.
- **14.** Workflow `CI` con las pruebas del backend y del frontend.
