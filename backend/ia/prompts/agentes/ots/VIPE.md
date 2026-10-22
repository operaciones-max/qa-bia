Objetivo: levantar en terreno la información para armar el alcance de la instalación.

Estos bloques deben venir diligenciados (entre paréntesis, dónde están en el acta extraída):

* Transformadores encontrados (`transformador`)
* Medidor encontrado (`medidor_encontrado`)
* Totalizador encontrado (`totalizador_encontrado`)
* Cables de potencia encontrados (`cables_potencia_encontrados`)
* Diagrama unifilar (`diagrama_unifilar.tiene_foto`)
* Requerimientos de instalación (no tiene campo propio: búscalos en `observacion_tecnico_verbatim`, donde el técnico suele escribir "Se requiere para instalación: …")

`totalizador_encontrado.tiene: false` significa que no hay totalizador y el bloque está resuelto. La bandera en `tiene: true` con todos los datos del bloque en null es un bloque en blanco.

FACTURA ANTERIOR: el medidor encontrado en la visita previa tiene que ser el mismo de la factura anterior del cliente (cruce "Medidor encontrado" con `fuente_sistema` "factura anterior" en `verificacion_equipos`):

* `coincide`: la visita se hizo sobre la medida del cliente.
* `no_coincide`: se levantó la información de un medidor que no es el del cliente (el del vecino en un gabinete compartido, otra frontera): FALLIDA, con la lógica de "equipo ajeno" de las reglas generales (responsable Contratista, "Fallas en el Alistamiento Operativo"). La única excepción es que la observación del técnico explique que el medidor fue cambiado después de esa factura (por el OR o por otro comercializador): entonces es un hallazgo "por confirmar", no FALLIDA.
* `posible_error_digitacion`: acta mal diligenciada (`acta_completa: false`), no un equipo ajeno.
* `sin_dato` (factura no disponible o ilegible): límite de la evaluación, nunca en contra del técnico.

FOTOS Y RELACIONES: la serie escrita del medidor encontrado tiene que ser la que se ve en su foto. En SEMIDIRECTA e INDIRECTA, la relación de los TCs (y de los TPs en INDIRECTA) escrita en el acta tiene que ser la de la placa en la foto, y el factor de medida tiene que corresponder a esas relaciones (TC 200/5 = factor 40; TC 50/5 con TP 13200/120 = 10 × 110 = 1100). Si no coinciden y no es un error de digitación, la información que trajo la visita no sirve para armar el alcance: FALLIDA.

TIPO DE MEDIDA: en DIRECTA no aplican TCs, TPs, bloque de pruebas ni cable de control; en SEMIDIRECTA no aplican TPs; en INDIRECTA aplica todo. Lo que aplica tiene que venir diligenciado completo.
