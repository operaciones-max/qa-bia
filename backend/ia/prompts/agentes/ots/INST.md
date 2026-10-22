Objetivo: instalar la medida de BIA en la frontera del cliente según el alcance de ingeniería y con los equipos asignados en WMS.

Esta OT admite PENDIENTE. Úsalo cuando el técnico sí ejecutó la instalación pero alguna de estas tres cosas quedó sin completar, y reporta cuál(es) en `pendientes` con el texto exacto:

* `Normalización Medida`: no se instalaron todos los equipos que exige el pedido (los equipos asignados en WMS). Si el bloque EQUIPOS ASIGNADOS no está disponible no puedes verificarlo: no lo asumas, dilo como límite de la evaluación.
* `Normalización Telemedida`: no se logró dejar la telemedida establecida/comunicando (p. ej. el módem quedó instalado pero sin comunicación, o no se pudo configurar).
* `Legalización`: el Operador de Red no asistió a la visita, por lo que el acta no queda legalizada con su representante. En el acta extraída lo ves en `or_firma` = "NO"; como "NO" también puede ser que el OR asistió sin dejar nombre, cédula y teléfono, confírmalo con la observación del técnico.

Puede quedar más de un pendiente: repórtalos todos.

Cómo elegir entre PENDIENTE y FALLIDA: si el núcleo de la instalación se ejecutó y lo que falta es una de esas tres tareas, es PENDIENTE. Si no se ejecutó la instalación, o el acta no permite verificar que se hizo, es FALLIDA.
