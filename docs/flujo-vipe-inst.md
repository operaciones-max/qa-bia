# Flujo de verificación de equipos: VIPE e INST

En las visitas previas (VIPE) y las instalaciones (INST), cada dato de los
equipos de medida se mira en tres fuentes:

1. **Acta:** lo que escribió el técnico, en el JSON que extrae el QA full.
2. **Foto:** lo que se ve en las fotos del acta, leído con OCR.
3. **Sistema:**
   - para lo encontrado, la factura anterior del cliente y la visita previa;
   - para lo instalado, lo asignado en WMS.

Además se revisa que el acta tenga llenos todos los campos que aplican según el
tipo de medida, y que el factor de medida corresponda a las relaciones de los
TCs y TPs.

## El flujo

```
Acta (PDF) ──► QA full: extrae el JSON del acta
                 │  serie y marca del medidor, seriales y relación de TCs/TPs,
                 │  tipo y factor de medida…
                 ▼
             OCR de fotos  (solo las páginas con fotos de equipos, hasta 12)
                 │  serie del medidor y serie y relación de cada TC/TP en su placa
                 ▼
Factura anterior ──► OCR de la factura: serial del medidor
                 │  (regex; si no alcanza, el OCR del servicio de extracción,
                 │   que también lee facturas escaneadas)
Visita previa ─────► lo que encontró la VIPE del mismo cliente (para la INST)
WMS ───────────────► equipos asignados al cliente (para la INST)
                 ▼
             Verificación (backend/verificacion)
                 │  cruces acta · foto · sistema
                 │  campos faltantes según el tipo de medida
                 │  factor de medida vs relaciones
                 ▼
             qa["verificacion_equipos"]  → Supabase (resultado_qa_completo)
                 │  y, si la OT se reportó exitosa, lo que no cuadra va a errores_qa
                 ▼
     Dashboard: tabla "acta · foto · sistema"     Subagente de cierre VIPE / INST
                                                  (lo recibe en VALIDACIONES DEL BACKEND)
```

## Qué se cruza

| Equipo | Dato | Acta | Foto | Sistema | VIPE | INST |
|---|---|---|---|---|---|---|
| Medidor encontrado | serie | `medidor_encontrado.serie` | foto del medidor encontrado | **factura anterior** | ✔ | ✔ |
| Medidor encontrado | serie | `medidor_encontrado.serie` | foto | **visita previa** del cliente | | ✔ |
| TCs encontrados | series y relación | `tcs_encontrados` | placas en las fotos | visita previa (en INST) | semi / ind | semi / ind |
| TPs encontrados | series y relación | `tps_encontrados` | placas en las fotos | sin fuente aún | ind | ind |
| Medidor instalado | serie | `medidor_instalado.serie` | foto del medidor instalado | **WMS asignado** | | ✔ |
| TCs instalados | series y relación | `tcs_instalados` | placas en las fotos | WMS asignado (series) | | semi / ind |
| TPs instalados | series y relación | `tps_instalados` | placas en las fotos | WMS asignado (series) | | ind |
| Factor de medida | factor | `factor_medida` | el que dan las relaciones de las fotos | el que dan las relaciones escritas | ✔ | ✔ |

El factor que dan las relaciones es la del TC por la del TP:
- TC 200/5 → factor 40;
- TC 50/5 con TP 13200/120 → 10 × 110 = 1100;
- en medida directa, el factor es 1.

Cada cruce sale con uno de estos resultados:

| Resultado | Significa |
|---|---|
| `coincide` | Igual, sin contar separadores ni ceros a la izquierda |
| `no_coincide` | Distinto |
| `posible_error_digitacion` | Difiere en 1 o 2 caracteres: acta mal diligenciada, no otro equipo |
| `falta_en_acta` | La otra fuente lo tiene y el acta no |
| `sin_dato` | La otra fuente no lo tiene (sin foto legible, sin factura, sin asignación): no cuenta en contra |

## Qué aplica según el tipo de medida

| | Medidor | TCs | TPs | Bloque de pruebas | Cable de control / señal |
|---|---|---|---|---|---|
| DIRECTA | ✔ | — | — | — | — |
| SEMIDIRECTA | ✔ | ✔ | — | ✔ | ✔ |
| INDIRECTA | ✔ | ✔ | ✔ | ✔ | ✔ |

Todos los campos de lo que aplica tienen que estar llenos. Si falta alguno,
aparece en `campos_faltantes` y el acta queda incompleta.

| Bloque | Campos obligatorios | Cuándo |
|---|---|---|
| General | tipo de medida, factor de medida | VIPE e INST |
| Medidor encontrado | serie, marca, referencia, lectura activa, lectura reactiva | VIPE e INST |
| TCs encontrados | seriales, relación | VIPE e INST · semi / ind |
| TPs encontrados | seriales, relación | VIPE e INST · ind |
| Bloque de pruebas encontrado | marca, tipo | VIPE e INST · semi / ind, si se encontró |
| Cable de control encontrado | calibre de corriente, calibre de tensión | VIPE e INST · semi / ind, si se encontró |
| Transformador | capacidad kVA, tipo de uso | VIPE, si se encontró |
| Totalizador encontrado | marca, capacidad | VIPE, si se encontró |
| Cables de potencia encontrados | calibre de acometida, cables por fase | VIPE, si se encontraron |
| Medidor instalado | serie, marca, referencia, lectura activa, sellos | INST, si se instaló |
| Telemedida instalada | IP, puerto, serie del módem, marca, IMEI, operador SIM, serie SIM | INST, si se instaló |
| TCs instalados | seriales, marca, relación, sellos | INST · semi / ind, si se instalaron |
| TPs instalados | seriales, marca, relación, sellos | INST · ind, si se instalaron |
| Bloque de pruebas instalado | marca, tipo | INST · semi / ind, si se instaló |
| Cable de control instalado | marca, calibre de corriente, calibre de tensión, metros | INST · semi / ind, si se instaló |
| Pruebas de funcionamiento | que se hayan hecho | INST |

## Cómo pesa en el veredicto (subagentes VIPE e INST)

- **VIPE:**
  - El medidor encontrado tiene que ser el de la factura anterior. Si no
    coincide, se levantó la información de otro medidor: es FALLIDA (responsable
    Contratista). La excepción es que el técnico explique que el medidor se
    cambió después de esa factura.
  - Si las relaciones o el factor no cuadran con las placas, la información no
    sirve para armar el alcance.
- **INST:**
  - Si la serie instalada no es la asignada en WMS, o la foto muestra otro
    equipo que el escrito, es FALLIDA.
  - Un error de 1 o 2 caracteres solo deja el acta incompleta.
  - Si falta un campo, el acta queda incompleta.
- **En los dos:** `sin_dato` nunca cuenta en contra del técnico. Se reporta como
  límite de la evaluación.

Las reglas completas están en `backend/ia/prompts/agentes/ots/VIPE.md` e `INST.md`.

## Dónde está en el código

| Pieza | Dónde |
|---|---|
| Cruces, campos obligatorios, relaciones y factor | `backend/verificacion` |
| Elegir las páginas con fotos y mandarlas al OCR | `backend/verificacion/fotos.go` (interfaz `LectorFotos`) |
| OCR de fotos (hoy Claude) | `ia.LeerFotosEquipos` + `backend/ia/prompts/fotos_equipos.md` |
| OCR de la factura | `facturas.ExtraerSerial`: regex y, si no alcanza, `extraccion.PrepararDocumento` + `ia.LeerSerialDeFactura` |
| Relación escrita en el acta | campo `relacion` de `tcs_*` / `tps_*` en `backend/ia/prompts/qa_full.md` |
| Cuándo corre | `pipeline.verificarEquipos`: en VIPE e INST con QA full; el OCR de fotos se apaga con `QA_OCR_FOTOS=false` |
| Dashboard | Detalle del acta, sección "Verificación de equipos" |

### Conectar el OCR propio

El OCR del repo privado se conecta en dos puntos, sin cambiar el resto:

- **Fotos:** con una implementación de `verificacion.LectorFotos`, que recibe
  las páginas con fotos y devuelve el JSON de `fotos_equipos.md`.
- **Factura:** dentro de `facturas.ExtraerSerial`, en lugar de
  `ia.LeerSerialDeFactura`.

## Lo que falta

- **Sistema para lo encontrado:** hoy solo hay factura anterior (serial del
  medidor) y visita previa. Para las relaciones de TCs y TPs encontrados falta
  saber dónde están registradas: ¿hoja de vida de la frontera, XM, el OR?
- **Relación en WMS:** el inventario de WMS trae serie y marca, pero no la
  relación de los TCs y TPs asignados. ¿Está en el nombre del SKU o en otra
  columna?
- **Costo:** el OCR de fotos es una llamada más a Claude por cada VIPE e INST,
  con hasta 12 páginas en imagen.
- **Prueba con actas reales:** los nombres de los bloques de fotos y el sello
  "Bia [fecha] [hora]" salen del prompt actual. Hay que confirmarlos con PDFs
  reales para que se elijan bien las páginas.
