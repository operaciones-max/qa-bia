# Subagentes de cierre por tipo de OT

Cada tipo de OT tiene su subagente: un prompt propio que dice cuál es el
objetivo de esa OT, qué tiene que traer el acta y cuándo es exitosa, fallida o
pendiente. Con eso Claude evalúa el cierre de cada visita según su tipo, en
lugar de usar un solo criterio para todas.

Cómo están armados (detalle en
[backend/ia/prompts/README.md](../backend/ia/prompts/README.md)):

- **Reglas comunes** (`agentes/comun.md`), las mismas para todos:
  - los dos juicios (¿se hizo el trabajo? / ¿el acta está bien llena?);
  - cómo leer el acta, el alcance, WMS y las validaciones;
  - los 5 porqués y el catálogo de causas;
  - el formato de respuesta.
- **Reglas de la familia** (`agentes/familias/`): 8 familias de OTs que se
  evalúan parecido (previa, ejecución, normalización, emergencia, retiro,
  verificación, cartera, gestión).
- **Reglas de la OT** (`agentes/ots/<CÓDIGO>.md`): objetivo, qué debe traer el
  acta y sus reglas propias.

El backend elige el subagente por el código con el que empieza el título de la
OT (`VIPE_44339_3986E7` → VIPE).

Son subagentes especializados, no agentes autónomos: cada uno es una sola
llamada a Claude con sus propias instrucciones. Es más barato y predecible, y
alcanza porque la evaluación de un acta no necesita herramientas ni varios
pasos.

**Estado:** conectados al QA. Las reglas de VIPE, INST y DESX vienen del
prompt `v1_closure_evaluator`; VIPE e INST suman además la verificación de
equipos acta · foto · sistema ([flujo-vipe-inst.md](flujo-vipe-inst.md)). Las
de las otras 42 OTs son un **borrador escrito a partir del nombre de cada OT**:
el dashboard las marca "reglas en borrador" hasta validarlas con operaciones.

## Qué hacen en el flujo

Después de que el QA extrae el acta y corre sus validaciones, cada acta pasa
por el subagente de su tipo de OT (`backend/cierre`, en `pipeline.ProcesarActa`):

1. **Elige el subagente** por el código con que empieza el título de la OT
   (`INST_…` → INST). Si el título no trae código, lo busca por el tipo de
   servicio.
2. **Le arma el caso** con todas las fuentes:
   - el acta extraída, antes de simplificar las fallidas;
   - el texto completo del PDF;
   - el alcance;
   - los equipos de WMS;
   - las notas (hoy no disponibles);
   - las validaciones del backend, incluida la verificación de equipos en VIPE
     e INST.
3. **El subagente responde:**
   - su veredicto (EXITOSA, FALLIDA o PENDIENTE);
   - si el acta está completa y qué falta;
   - los pendientes;
   - los hallazgos;
   - si falló, los 5 porqués con la causa del catálogo;
   - un comentario de cierre.
4. **El backend lo valida:**
   - PENDIENTE solo donde la OT lo admite;
   - la causa se ajusta al catálogo.

   Lo guarda en `resultado_qa_completo.cierre_ia`.
5. **El revisor lo ve en el detalle del acta**, junto al estado de App Ops, y
   decide. El subagente no cambia `estado_ot`: es un segundo veredicto,
   independiente.

Cuesta una llamada más a Claude por acta. Se apaga con `QA_SUBAGENTES=false`.

## Tipos de OT

### VAS / Energy Solutions (21)

| Código | OT | Familia | Estado |
|---|---|---|---|
| [AING](../backend/ia/prompts/agentes/ots/AING.md) | Alta Ingeniería | ejecución | Borrador |
| [AMCA](../backend/ia/prompts/agentes/ots/AMCA.md) | Ejecución aumento de carga | ejecución | Borrador |
| [PREA](../backend/ia/prompts/agentes/ots/PREA.md) | Previa aumento de carga | previa | Borrador |
| [MANT](../backend/ia/prompts/agentes/ots/MANT.md) | Ejecución mantenimiento | ejecución | Borrador |
| [PREM](../backend/ia/prompts/agentes/ots/PREM.md) | Previa mantenimiento | previa | Borrador |
| [TERM](../backend/ia/prompts/agentes/ots/TERM.md) | Ejecución termografía | ejecución | Borrador |
| [PRET](../backend/ia/prompts/agentes/ots/PRET.md) | Previa termografía | previa | Borrador |
| [ISNT](../backend/ia/prompts/agentes/ots/ISNT.md) | Instalación Cambio NT | ejecución | Borrador |
| [VPNT](../backend/ia/prompts/agentes/ots/VPNT.md) | Visita Previa Cambio NT | previa | Borrador |
| [ISIC](../backend/ia/prompts/agentes/ots/ISIC.md) | Ejecución Independización Cuentas | ejecución | Borrador |
| [PVIC](../backend/ia/prompts/agentes/ots/PVIC.md) | Previa Independización Cuentas | previa | Borrador |
| [BICH](../backend/ia/prompts/agentes/ots/BICH.md) | Instalación BIA Monitor | ejecución | Borrador |
| [PREB](../backend/ia/prompts/agentes/ots/PREB.md) | Previa Bichito | previa | Borrador |
| [NOBI](../backend/ia/prompts/agentes/ots/NOBI.md) | Normalización BIA Monitor | normalización | Borrador |
| [ALBI](../backend/ia/prompts/agentes/ots/ALBI.md) | Emergencia BIA Monitor | emergencia | Borrador |
| [REBI](../backend/ia/prompts/agentes/ots/REBI.md) | Retiro BIA Monitor | retiro | Borrador |
| [COND](../backend/ia/prompts/agentes/ots/COND.md) | Instalación condensadores | ejecución | Borrador |
| [PREC](../backend/ia/prompts/agentes/ots/PREC.md) | Previa Bancos de Condensadores | previa | Borrador |
| [NOCO](../backend/ia/prompts/agentes/ots/NOCO.md) | Normalización condensadores | normalización | Borrador |
| [ALCO](../backend/ia/prompts/agentes/ots/ALCO.md) | Emergencia Banco de Condensadores | emergencia | Borrador |
| [RECO](../backend/ia/prompts/agentes/ots/RECO.md) | Retiro Banco de Condensadores | retiro | Borrador |

### Generación (1)

| Código | OT | Familia | Estado |
|---|---|---|---|
| [GVICO](../backend/ia/prompts/agentes/ots/GVICO.md) | Visita Conjunta Generación | verificación | Borrador |

### Activación (10)

| Código | OT | Familia | Estado |
|---|---|---|---|
| [VIPE](../backend/ia/prompts/agentes/ots/VIPE.md) | Visita previa | previa | Reglas del prompt v1 |
| [PREV](../backend/ia/prompts/agentes/ots/PREV.md) | Visita pre-venta | previa | Borrador |
| [INST](../backend/ia/prompts/agentes/ots/INST.md) | Instalación | ejecución | Reglas del prompt v1 · admite PENDIENTE |
| [LEGA](../backend/ia/prompts/agentes/ots/LEGA.md) | Legalización | gestión | Borrador |
| [NORM](../backend/ia/prompts/agentes/ots/NORM.md) | Normalización medida | normalización | Borrador |
| [VIAD](../backend/ia/prompts/agentes/ots/VIAD.md) | Visita Adicional | ejecución | Borrador |
| [SUCA](../backend/ia/prompts/agentes/ots/SUCA.md) | Suministro de carro canasta | gestión | Borrador |
| [REQA](../backend/ia/prompts/agentes/ots/REQA.md) | Revisión por QA | verificación | Borrador |
| [PRRU](../backend/ia/prompts/agentes/ots/PRRU.md) | Pruebas de Rutina | verificación | Borrador |
| [VEXT](../backend/ia/prompts/agentes/ots/VEXT.md) | Verificación externa | verificación | Borrador |

### Retención (13)

| Código | OT | Familia | Estado |
|---|---|---|---|
| [DESX](../backend/ia/prompts/agentes/ots/DESX.md) | Desconexión | cartera | Reglas del prompt v1 |
| [RECX](../backend/ia/prompts/agentes/ots/RECX.md) | Reconexión | cartera | Borrador |
| [ALRT](../backend/ia/prompts/agentes/ots/ALRT.md) | Emergencia | emergencia | Borrador |
| [NOAL](../backend/ia/prompts/agentes/ots/NOAL.md) | Normalización Emergencias | normalización | Borrador |
| [NOTE](../backend/ia/prompts/agentes/ots/NOTE.md) | Normalización Telemedidas | normalización | Borrador |
| [PQRS](../backend/ia/prompts/agentes/ots/PQRS.md) | PQR | verificación | Borrador |
| [VERF](../backend/ia/prompts/agentes/ots/VERF.md) | Verificación consumo | verificación | Borrador |
| [VICO](../backend/ia/prompts/agentes/ots/VICO.md) | Visita conjunta | verificación | Borrador |
| [INFR](../backend/ia/prompts/agentes/ots/INFR.md) | Inspección de frontera | verificación | Borrador |
| [RDEP](../backend/ia/prompts/agentes/ots/RDEP.md) | Retiro de Equipos | retiro | Borrador |
| [INPE](../backend/ia/prompts/agentes/ots/INPE.md) | Instalación de planta eléctrica | ejecución | Borrador |
| [REPE](../backend/ia/prompts/agentes/ots/REPE.md) | Retiro de planta eléctrica | retiro | Borrador |
| [TLIS](../backend/ia/prompts/agentes/ots/TLIS.md) | Toma de Lectura In Situ | verificación | Borrador |

## Lo que necesito para terminarlos

### Por cada OT

1. **Revisar el borrador** de su archivo en `backend/ia/prompts/agentes/ots/`:
   - ¿el objetivo está bien?
   - ¿qué la hace exitosa y qué la hace fallida?
2. **Actas reales:** 2 o 3 PDF por OT, al menos una exitosa y una fallida, con
   el veredicto correcto. Sirven para:
   - ver qué trae el formulario de cada OT;
   - probar el subagente contra casos conocidos.
3. **Evidencia obligatoria:** qué fotos, mediciones y firmas tiene que traer el
   acta para que el trabajo cuente como hecho.
4. **Alcance y equipos:**
   - ¿la OT tiene un alcance o equipos asignados antes de la visita?
   - ¿de dónde salen? Hoy solo leemos el alcance de ingeniería de las
     instalaciones y los equipos de WMS.
5. **Pendiente:** ¿la OT puede quedar PENDIENTE como INST? ¿Con qué
   pendientes, en texto exacto?
6. **Causas de falla típicas:** qué causas del catálogo aplican a esa OT.
   Algunas pueden faltar en el catálogo, sobre todo para VAS y Generación.

### En general

- **Prioridad:** con qué OTs empezamos. Propongo VIPE, INST y DESX, que ya
  tienen reglas validadas, y después las de más volumen. No pude ver los
  volúmenes porque desde aquí no hay acceso a Metabase.
- **Responsables:** quién valida cada línea (VAS, Generación, Activación,
  Retención).
- **El código en el título:** ¿todas las OTs empiezan con su código? En los
  datos que tenemos sí (`VIPE_…`, `PREC_…`, `PREB_…`).
- **Clasificación de hoy:** el QA clasifica la línea por el texto del tipo de
  servicio, y no siempre coincide con la lista:
  - AING (Alta Ingeniería) hoy cuenta como Activación; en la lista es VAS.
  - SUCA (carro canasta) hoy cuenta como Energy Solutions; en la lista es Activación.
  - GVICO (Generación) hoy cae en Retención.
  - Algunas previas de VAS (PRET, VPNT, PVIC, PREA) pueden caer en Activación
    porque su nombre dice "previa".

  Con el código se puede clasificar exacto. ¿Lo cambiamos?
- **Columnas propias para el veredicto:** hoy queda dentro de
  `resultado_qa_completo` para no depender de una migración. Si se quiere
  filtrar el listado por el veredicto del subagente, hay que pasarlo a
  columnas.
