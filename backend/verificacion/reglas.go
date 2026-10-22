package verificacion

import (
	"strings"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

// Aplica dice que equipos corresponden al tipo de medida:
//   - DIRECTA: solo medidor. No aplican TCs, TPs, bloque de pruebas ni cable de control.
//   - SEMIDIRECTA: medidor, TCs, bloque de pruebas y cable de control. No aplican TPs.
//   - INDIRECTA: todo.
type Aplica struct {
	Conocida      bool `json:"tipo_medida_conocido"`
	TCs           bool `json:"tcs"`
	TPs           bool `json:"tps"`
	BloquePruebas bool `json:"bloque_pruebas"`
	CableControl  bool `json:"cable_control"`
}

// AplicaPara devuelve lo que aplica segun el tipo de medida del acta.
func AplicaPara(tipoMedida string) Aplica {
	switch strings.ToUpper(strings.TrimSpace(tipoMedida)) {
	case "DIRECTA":
		return Aplica{Conocida: true}
	case "SEMIDIRECTA":
		return Aplica{Conocida: true, TCs: true, BloquePruebas: true, CableControl: true}
	case "INDIRECTA":
		return Aplica{Conocida: true, TCs: true, TPs: true, BloquePruebas: true, CableControl: true}
	}
	return Aplica{}
}

// campo es un dato obligatorio del acta: bloque.clave y su nombre para mostrar.
type campo struct{ clave, nombre string }

// camposFaltantes lista los campos obligatorios vacios, segun el tipo de OT y
// el tipo de medida. En el acta todos los campos que aplican deben estar llenos.
func camposFaltantes(tipoOT string, acta dato.Objeto, aplica Aplica) []string {
	var faltan []string
	exigir := func(bloque, nombreBloque string, campos ...campo) {
		b := dato.Hijo(acta, bloque)
		for _, c := range campos {
			if vacio(b[c.clave]) {
				faltan = append(faltan, nombreBloque+": "+c.nombre)
			}
		}
	}
	tiene := func(bloque, bandera string) bool { return dato.EsTrue(dato.Hijo(acta, bloque)[bandera]) }

	if vacio(acta["tipo_medida"]) {
		faltan = append(faltan, "Tipo de medida")
	}
	if vacio(acta["factor_medida"]) {
		faltan = append(faltan, "Factor de medida")
	}

	// Lo encontrado: en VIPE y en INST.
	exigir("medidor_encontrado", "Medidor encontrado",
		campo{"serie", "serie"}, campo{"marca", "marca"}, campo{"referencia", "referencia"},
		campo{"lectura_activa_kwh", "lectura activa"}, campo{"lectura_reactiva_kvarh", "lectura reactiva"})
	if aplica.TCs {
		exigir("tcs_encontrados", "TCs encontrados", campo{"seriales", "seriales"}, campo{"relacion", "relación"})
	}
	if aplica.TPs {
		exigir("tps_encontrados", "TPs encontrados", campo{"seriales", "seriales"}, campo{"relacion", "relación"})
	}
	if aplica.BloquePruebas && tiene("bloque_pruebas_encontrado", "tiene") {
		exigir("bloque_pruebas_encontrado", "Bloque de pruebas encontrado", campo{"marca", "marca"}, campo{"tipo", "tipo"})
	}
	if aplica.CableControl && tiene("cable_control_encontrado", "tiene") {
		exigir("cable_control_encontrado", "Cable de control encontrado",
			campo{"calibre_corriente", "calibre de corriente"}, campo{"calibre_tension", "calibre de tensión"})
	}

	switch tipoOT {
	case "VIPE":
		if tiene("transformador", "tiene") {
			exigir("transformador", "Transformador", campo{"capacidad_kva", "capacidad kVA"}, campo{"tipo_uso", "tipo de uso"})
		}
		if tiene("totalizador_encontrado", "tiene") {
			exigir("totalizador_encontrado", "Totalizador encontrado", campo{"marca", "marca"}, campo{"capacidad_a", "capacidad"})
		}
		if tiene("cables_potencia_encontrados", "tiene") {
			exigir("cables_potencia_encontrados", "Cables de potencia encontrados",
				campo{"calibre_acometida", "calibre de acometida"}, campo{"cables_por_fase_acometida", "cables por fase"})
		}

	case "INST":
		if tiene("medidor_instalado", "se_instalo") {
			exigir("medidor_instalado", "Medidor instalado",
				campo{"serie", "serie"}, campo{"marca", "marca"}, campo{"referencia", "referencia"},
				campo{"lectura_activa_kwh", "lectura activa"})
			if vacio(acta["sellos_medidor_instalado"]) {
				faltan = append(faltan, "Medidor instalado: sellos")
			}
		}
		if tiene("telemedida_instalada", "se_instalo") {
			exigir("telemedida_instalada", "Telemedida instalada",
				campo{"ip", "IP"}, campo{"puerto", "puerto"}, campo{"serie", "serie del módem"}, campo{"marca", "marca"},
				campo{"imei", "IMEI"}, campo{"operador_sim", "operador SIM"}, campo{"serie_sim", "serie SIM"})
		}
		if aplica.TCs && tiene("tcs_instalados", "se_instalo") {
			exigir("tcs_instalados", "TCs instalados", campo{"seriales", "seriales"}, campo{"marca", "marca"}, campo{"relacion", "relación"})
			if vacio(acta["sellos_tcs_instalados"]) {
				faltan = append(faltan, "TCs instalados: sellos")
			}
		}
		if aplica.TPs && tiene("tps_instalados", "se_instalo") {
			exigir("tps_instalados", "TPs instalados", campo{"seriales", "seriales"}, campo{"marca", "marca"}, campo{"relacion", "relación"})
			if vacio(acta["sellos_tps_instalados"]) {
				faltan = append(faltan, "TPs instalados: sellos")
			}
		}
		if aplica.BloquePruebas && tiene("bloque_pruebas_instalado", "se_instalo") {
			exigir("bloque_pruebas_instalado", "Bloque de pruebas instalado", campo{"marca", "marca"}, campo{"tipo", "tipo"})
		}
		if aplica.CableControl && tiene("cable_control_instalado", "se_instalo") {
			exigir("cable_control_instalado", "Cable de control instalado",
				campo{"marca", "marca"}, campo{"calibre_corriente", "calibre de corriente"},
				campo{"calibre_tension", "calibre de tensión"}, campo{"metros", "metros"})
		}
		if !tiene("pruebas_funcionamiento", "se_realizaron") {
			faltan = append(faltan, "Pruebas de funcionamiento")
		}
	}
	return faltan
}

// vacio trata como vacio: nil, "", "null", "N/A", "-" y las listas vacias.
func vacio(v any) bool {
	switch x := v.(type) {
	case nil:
		return true
	case string:
		s := strings.ToUpper(strings.TrimSpace(x))
		return s == "" || s == "NULL" || s == "N/A" || s == "NA" || s == "-"
	case []any:
		for _, e := range x {
			if !vacio(e) {
				return false
			}
		}
		return true
	}
	return false
}
