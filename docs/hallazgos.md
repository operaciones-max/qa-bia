# Revisión del código — hallazgos (octubre 2026)

Revisión completa de `qa_bia.py` hecha al separarlo en módulos. **La
reestructuración no corrigió nada de esto**: el comportamiento quedó idéntico
al original, verificado corriendo las dos versiones con los mismos datos
simulados. Cada punto se puede atacar por separado.

Las rutas apuntan al código nuevo en `backend/qa_bia/`.

## Prioridad alta

### 1. El repo es público y expone datos operativos
`operaciones-max/qa-bia` es **público**. Hoy cualquiera puede ver:
- las URLs de las preguntas públicas de Metabase (`config.py`), que descargan
  el CSV de actas (direcciones, empresas, técnicos, PDFs), el inventario WMS y
  los alcances;
- `state/visitas_previas.json` (nombres de técnicos, seriales, observaciones) y
  `state/facturas_extraidas.json` (URLs de facturas de clientes; si esas URLs
  son públicas, cualquiera puede bajarlas);
- los logs de GitHub Actions, que también son públicos e imprimen 10
  caracteres de la `METABASE_API_KEY` (`metabase.py:39`, `metabase.py:105`).

**Propuesta:** hacer el repo privado, regenerar los enlaces públicos de
Metabase y quitar el print de la key.

### 2. Si falla Supabase, el acta se pierde
`pipeline.py:321-322`: `enviar_supabase()` no devuelve si funcionó, y
`guardar_procesado()` marca el acta como procesada de todas formas. Con
Supabase caído o un error 4xx, el acta no llega al dashboard y nunca se
reintenta.

**Propuesta:** que `enviar_supabase()` devuelva `True/False` y marcar procesada
solo si guardó.

### 3. El QA full pide verificar fotos que nunca recibe
`prompts.py:86` dice "VAS A RECIBIR ... las paginas del acta como imagenes" y
pide contar sellos "visualmente" y comparar series contra la foto. Pero
`ia.analizar_acta()` no usa su parámetro `imagenes_pdf` (`ia.py:138` manda solo
texto) y además `pdf.MAX_PAGINAS_VISION = 0`. Claude responde `sellos_*`,
`serie_coincide_foto` y `fotos_*` sin ver nada, y esos valores llegan al
dashboard.

**Propuesta:** o mandar las imágenes (cuesta más tokens) o quitar esas
instrucciones del prompt y dejar esos campos en null.

### 4. Normalizaciones y Alta ingeniería se analizan como "VISITA PREVIA"
`ia.py:100`: `tipo_label = "INSTALACION" if "nstala" in tipo else "VISITA PREVIA"`.
"Normalización medida", "Normalización emergencias" y "Alta ingeniería" usan
QA full pero llegan a Claude como VISITA PREVIA, cuyo prompt dice que nada se
instala, al mismo tiempo que se le pasan equipos WMS para comparar.
Confirmado en la prueba de equivalencia.

**Propuesta:** pasar el tipo real, o un `tipo_label` por categoría.

## Prioridad media

### 5. Instrucciones contradictorias en los prompts
- `prompts.py:140` pide a Claude cambiar EXITOSA → FALLIDA si el acta está
  incompleta, pero `pipeline.procesar_acta()` sobrescribe `estado_ot` con el
  dato de Metabase. Son tokens pagados por algo que se descarta.
- El ejemplo "gold" (`prompts.py:289`) usa la causa "Condiciones tecnicas no
  viables", que no existe en el catálogo.
- El prompt lite (`prompts.py:41`) dice "primeras 2 paginas" y el código manda 4.

### 6. El backend pisa las ediciones del revisor
El *upsert* reescribe la fila completa al reprocesar, y
`reconciliar_estado_app_ops()` recalcula `estado_app_ops` y `estado_revision`
en cada corrida. Ver [contrato-supabase.md](contrato-supabase.md).

### 7. La reconciliación no pagina
`supabase.py:33` lee `actas_qa` sin paginar. Supabase devuelve como máximo
1000 filas por defecto: cuando haya más de 1000 actas (hoy hay ~344), las demás
dejan de reconciliarse sin ningún aviso.

### 8. El estado vive en git y los errores se ignoran
El bot commitea `state/` en cada corrida con `git pull --rebase || true` y
`git push || true`. Si el push falla, el avance se pierde sin aviso y se
reprocesan actas (más tokens). El estado podría salir de Supabase (las actas
ya guardadas en `actas_qa`) y eliminar estos commits.

### 9. Dependencias sin fijar
`requirements.txt` tiene `anthropic>=0.40.0` y `pymupdf>=1.24.0`. Hoy instala
anthropic 2.x y pymupdf 2.0 (que ya avisa que `import fitz` se va a eliminar).
Una versión nueva puede romper una corrida sin que nadie cambie nada.

**Propuesta:** fijar versiones exactas probadas.

## Prioridad baja

10. **Detección de rate limit por texto** (`ia.py:90`, `facturas.py:154`):
    busca `"rate"` en el mensaje de error, que también aparece en palabras como
    "generate". Mejor usar las excepciones del SDK (`anthropic.RateLimitError`).
11. **PDF descargado dos veces** en PQR / visita conjunta / emergencia
    (`pipeline.py:120`).
12. **Código muerto y nombres heredados:**
    - `slack.py`, unas 750 líneas que hoy no se llaman;
    - `_override_fallida_si_incompleto`, `TIPOS_SERVICIO_VALIDOS` y `MODO_BACKFILL`, sin uso;
    - restos de la migración desde Groq/Gemini: `PAUSA_GROQ_SEGUNDOS` y los
      mensajes "Gemini" (`estado.py:80`, `slack.py:19`).
13. **`datetime.utcnow()`** está deprecado desde Python 3.12 (`estado.py`, `supabase.py`).
14. **No hay CI de pruebas:** ya existe `backend/tests/`, pero ningún workflow
    lo corre en los PRs.
