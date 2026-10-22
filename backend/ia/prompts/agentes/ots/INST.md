Objetivo: instalar la medida de BIA en la frontera del cliente según el alcance de ingeniería y con los equipos asignados en WMS.

TRES FUENTES QUE TIENEN QUE CUADRAR (cruces de `verificacion_equipos`):

* Medidor instalado: la serie escrita en el acta = la que se ve en su foto = la asignada en WMS.
* TCs instalados (SEMIDIRECTA e INDIRECTA): cada serie del acta = la de su foto = una de las asignadas en WMS, y ningún TC asignado sin registrar. La relación escrita = la de la placa en la foto.
* TPs instalados (solo INDIRECTA): igual que los TCs.
* Lo encontrado: el medidor encontrado = el de la factura anterior y el de la visita previa del cliente; las relaciones de los TCs y TPs encontrados = las de sus placas.
* Factor de medida = el que dan las relaciones (TC 200/5 = 40; TC 50/5 con TP 13200/120 = 10 × 110 = 1100).

Cómo pesan:

* Serie instalada distinta a la asignada en WMS (`no_coincide`), o foto que muestra otro equipo que el escrito: se instaló o se registró un equipo que no corresponde: FALLIDA (responsable Contratista, "Fallas en el Alistamiento Operativo"), salvo que la observación explique un cambio autorizado.
* `posible_error_digitacion`: acta mal diligenciada (`acta_completa: false`).
* Factor que no corresponde a las relaciones: la medida queda mal parametrizada. Si las relaciones de la foto confirman el factor escrito, el error es de la relación escrita (`acta_completa: false`); si no, FALLIDA.
* `sin_dato` (sin foto legible, sin asignación en WMS, sin factura): límite de la evaluación, nunca en contra del técnico.

TIPO DE MEDIDA: en DIRECTA no aplican TCs, TPs, bloque de pruebas ni cable de control (de control o de señal); en SEMIDIRECTA no aplican TPs; en INDIRECTA aplica todo. TODOS los campos de lo que aplica tienen que venir llenos (`verificacion_equipos.campos_faltantes`): si falta alguno, `acta_completa: false`. Si falta el bloque completo del medidor instalado, es FALLIDA (ver reglas generales).

Esta OT admite PENDIENTE. Úsalo cuando el técnico sí ejecutó la instalación pero alguna de estas tres cosas quedó sin completar, y reporta cuál(es) en `pendientes` con el texto exacto:

* `Normalización Medida`: no se instalaron todos los equipos que exige el pedido (los equipos asignados en WMS). Si el bloque EQUIPOS ASIGNADOS no está disponible no puedes verificarlo: no lo asumas, dilo como límite de la evaluación.
* `Normalización Telemedida`: no se logró dejar la telemedida establecida/comunicando (p. ej. el módem quedó instalado pero sin comunicación, o no se pudo configurar).
* `Legalización`: el Operador de Red no asistió a la visita, por lo que el acta no queda legalizada con su representante. En el acta extraída lo ves en `or_firma` = "NO"; como "NO" también puede ser que el OR asistió sin dejar nombre, cédula y teléfono, confírmalo con la observación del técnico.

Puede quedar más de un pendiente: repórtalos todos.

Cómo elegir entre PENDIENTE y FALLIDA: si el núcleo de la instalación se ejecutó y lo que falta es una de esas tres tareas, es PENDIENTE. Si no se ejecutó la instalación, o el acta no permite verificar que se hizo, es FALLIDA.
