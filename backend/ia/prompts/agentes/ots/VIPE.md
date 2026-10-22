Objetivo: levantar en terreno la información para armar el alcance de la instalación.

Estos bloques deben venir diligenciados (entre paréntesis, dónde están en el acta extraída):

* Transformadores encontrados (`transformador`)
* Medidor encontrado (`medidor_encontrado`)
* Totalizador encontrado (`totalizador_encontrado`)
* Cables de potencia encontrados (`cables_potencia_encontrados`)
* Diagrama unifilar (`diagrama_unifilar.tiene_foto`)
* Requerimientos de instalación (no tiene campo propio: búscalos en `observacion_tecnico_verbatim`, donde el técnico suele escribir "Se requiere para instalación: …")

`totalizador_encontrado.tiene: false` significa que no hay totalizador y el bloque está resuelto. La bandera en `tiene: true` con todos los datos del bloque en null es un bloque en blanco.
