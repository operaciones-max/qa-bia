// Package validaciones aplica reglas defensivas sobre la respuesta de la IA:
// reglas por tipo de medida y de servicio, comparacion con WMS y limpieza de
// errores que en realidad describen el comportamiento esperado.
package validaciones

import (
	"strings"

	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/util"
)

// CorregirSerieFoto marca serie_coincide_foto=true si la observacion de la IA
// en realidad contiene la misma serie.
func CorregirSerieFoto(item dato.Objeto) {
	if item == nil {
		return
	}
	serie := dato.TextoLimpio(item["serie"])
	obs := dato.Texto(item["observacion_serie_foto"])
	if dato.EsFalse(item["serie_coincide_foto"]) && serie != "" {
		normSerie := util.NormalizarSerial(serie)
		if normSerie != "" && strings.Contains(util.NormalizarSerial(obs), normSerie) {
			item["serie_coincide_foto"] = true
			item["observacion_serie_foto"] = nil
		}
	}
}

func esVisitaPrevia(tipoServicio string) bool {
	return strings.Contains(strings.ToLower(tipoServicio), "previa")
}

// AplicarReglasMedidaServicio fuerza aplica=false donde no corresponde:
// TCs/TPs en DIRECTA, TPs en SEMIDIRECTA y todo lo instalado en VISITA PREVIA.
func AplicarReglasMedidaServicio(qa dato.Objeto, tipoServicio string) {
	tipoMedida := strings.ToUpper(dato.Texto(qa["tipo_medida"]))
	noAplica := func(claves ...string) {
		for _, k := range claves {
			if m := dato.Hijo(qa, k); m != nil {
				m["aplica"] = false
			}
		}
	}
	switch tipoMedida {
	case "DIRECTA":
		noAplica("tcs_encontrados", "tcs_instalados", "tps_encontrados", "tps_instalados",
			"bloque_pruebas_encontrado", "bloque_pruebas_instalado",
			"cable_control_encontrado", "cable_control_instalado")
		qa["fotos_tcs"] = nil
		qa["fotos_tps"] = nil
	case "SEMIDIRECTA":
		noAplica("tps_encontrados", "tps_instalados")
		qa["fotos_tps"] = nil
	}
	if esVisitaPrevia(tipoServicio) {
		noAplica("medidor_instalado", "tcs_instalados", "tps_instalados",
			"bloque_pruebas_instalado", "cable_control_instalado",
			"telemedida_instalada", "totalizador_instalado",
			"cables_potencia_instalados", "medidor_respaldo_instalado",
			"sellos_instalados")
	}
}

// conjuntoNormalizado normaliza los seriales y descarta los vacios.
func conjuntoNormalizado(seriales []any) map[string]bool {
	out := map[string]bool{}
	for _, s := range seriales {
		if !dato.Verdadero(s) {
			continue
		}
		if n := util.NormalizarSerial(dato.TextoCrudo(s)); n != "" {
			out[n] = true
		}
	}
	return out
}

// todosEn indica si wms no esta vacio y todos sus seriales estan en acta.
func todosEn(wms, acta map[string]bool) bool {
	if len(wms) == 0 {
		return false
	}
	for s := range wms {
		if !acta[s] {
			return false
		}
	}
	return true
}

// ValidarCoincidenciaWMS recalcula en codigo (sin confiar en la IA) si el
// medidor, TCs y TPs instalados coinciden con lo asignado en WMS.
func ValidarCoincidenciaWMS(qa dato.Objeto, serialWMS string, tcsWMS, tpsWMS []string, debeComparar bool) {
	qa["medidor_coincide_wms"] = nil
	if debeComparar && serialWMS != "" {
		serieInst := dato.TextoLimpio(dato.Hijo(qa, "medidor_instalado")["serie"])
		if serieInst == "" {
			serieInst = dato.TextoLimpio(qa["medidor_instalado_acta"])
		}
		if serieInst != "" {
			qa["medidor_coincide_wms"] = util.NormalizarSerial(serieInst) == util.NormalizarSerial(serialWMS)
		}
	}

	tipoMedida := strings.ToUpper(dato.Texto(qa["tipo_medida"]))

	qa["tcs_coinciden_wms"] = nil
	if debeComparar && len(tcsWMS) > 0 && (tipoMedida == "SEMIDIRECTA" || tipoMedida == "INDIRECTA") {
		actas := dato.Lista(dato.Hijo(qa, "tcs_instalados")["seriales"])
		qa["tcs_coinciden_wms"] = todosEn(conjuntoNormalizado(dato.TextosAny(tcsWMS)), conjuntoNormalizado(actas))
	}

	qa["tps_coinciden_wms"] = nil
	if debeComparar && len(tpsWMS) > 0 && tipoMedida == "INDIRECTA" {
		actas := dato.Lista(dato.Hijo(qa, "tps_instalados")["seriales"])
		qa["tps_coinciden_wms"] = todosEn(conjuntoNormalizado(dato.TextosAny(tpsWMS)), conjuntoNormalizado(actas))
	}
}

// Terminos que en VISITA PREVIA describen lo esperado, no un error.
var terminosVisitaPrevia = []string{
	"pruebas de funcionamiento", "equipo patron", "equipo patrón",
	"diagrama unifilar", "no se realizaron pruebas",
	"no se reporta equipo", "no se reporta foto",
	"no se reportan fotos", "no se reportan sellos",
	"no se encontraron sellos", "no se encontro sello",
	"no se encontraron fotos", "no se encontro foto",
	"no se encontro telemedida", "no se encontró telemedida",
	"no se encontro bloque", "no se encontró bloque",
	"no se encontro cable", "no se encontró cable",
	"medidor de respaldo", "medidor de espejo",
	"planta de respaldo", "planta electrica",
	"no se encontraron alertas", "no se encontraron tcs",
	"no se encontraron tps",
	"el acta no reporta", "no se reporta el color",
	"no se reporta la serie del sello",
	"no reporta la serie del sello",
	"no reporta el color del sello",
	"no se reporta el segundo sello", "no se reporta el tercer sello",
	"color del sello", "serie del sello",
	"no reporta lectura", "no se reporta lectura",
	"operador de red", "comercializador anterior",
}

func contieneAlguno(s string, terminos ...string) bool {
	for _, t := range terminos {
		if strings.Contains(s, t) {
			return true
		}
	}
	return false
}

// LimpiarErroresFantasma saca los errores y alertas que reportan comportamiento
// normal segun las reglas de medida/servicio, y quita de las alertas lo que ya
// esta en errores.
func LimpiarErroresFantasma(qa dato.Objeto, tipoServicio string) {
	val := dato.Hijo(qa, "validaciones")
	if !dato.Verdadero(val) {
		val = dato.Objeto{}
	}
	errores := dato.Lista(val["errores_encontrados"])
	alertas := dato.Lista(qa["alertas_qa"])

	tipoMedida := strings.ToUpper(dato.Texto(qa["tipo_medida"]))
	esVisita := esVisitaPrevia(tipoServicio)
	esDirecta := tipoMedida == "DIRECTA"
	esSemidirecta := tipoMedida == "SEMIDIRECTA"

	esFantasma := func(item any) bool {
		s := " " + strings.ToLower(dato.Texto(item)) + " "
		// Regla universal: "no se reporta(n)" es un volcado de campos vacios, no un
		// error real. Si un campo critico falta, el revisor marca FALLIDA en el dashboard.
		if contieneAlguno(s, " no se reporta ", " no se reportan ") {
			return true
		}
		if contieneAlguno(s, " no se encontraron ", " no se encontro ", " no se encontró ") {
			return true
		}
		if contieneAlguno(s, "no coincide con la serie visible en foto", "no coincide con la foto",
			"serie visible en foto", "no se realizaron pruebas", "el acta no reporta") {
			return true
		}
		if esDirecta && contieneAlguno(s, " tc ", " tcs ", " tp ", " tps ", "bloque de pruebas",
			"bloque pruebas", "cable de control", "cable control") {
			return true
		}
		if esSemidirecta && contieneAlguno(s, " tp ", " tps ") && !contieneAlguno(s, " tc ", " tcs ") {
			return true
		}
		if esVisita {
			if strings.Contains(s, "instalad") && !contieneAlguno(s, "telemedida instalad", "totalizador instalad") {
				return true
			}
			if contieneAlguno(s, terminosVisitaPrevia...) {
				return true
			}
		}
		if esDirecta && contieneAlguno(s, "medidor de respaldo", "medidor de espejo", "planta de respaldo", "no se encontro") {
			return true
		}
		// Campos del acta con valor basura
		if contieneAlguno(s, ": n.v", ": .o", ": .0", ": otra", ": otro", "no reportada", "no reportado") &&
			contieneAlguno(s, "encontrada", "encontrado", "instalada", "instalado") {
			return true
		}
		return false
	}

	erroresLimpios := []any{}
	enErrores := map[string]bool{}
	for _, e := range errores {
		if !esFantasma(e) {
			erroresLimpios = append(erroresLimpios, e)
			enErrores[dato.TextoCrudo(e)] = true
		}
	}
	alertasLimpias := []any{}
	for _, a := range alertas {
		if !esFantasma(a) && !enErrores[dato.TextoCrudo(a)] {
			alertasLimpias = append(alertasLimpias, a)
		}
	}

	val["errores_encontrados"] = erroresLimpios
	qa["validaciones"] = val
	qa["alertas_qa"] = alertasLimpias
}

// SimplificarFallida: en una OT FALLIDA la tipificacion ya explica el motivo, asi
// que vacia los errores, deja solo las alertas de firma (OR/usuario/cliente) y
// quita los "cinco por que".
func SimplificarFallida(qa dato.Objeto) {
	if qa["estado_ot"] != "FALLIDA" {
		return
	}
	val := dato.Hijo(qa, "validaciones")
	if !dato.Verdadero(val) {
		val = dato.Objeto{}
	}
	val["errores_encontrados"] = []any{}
	qa["validaciones"] = val

	conservar := []any{}
	for _, a := range dato.Lista(qa["alertas_qa"]) {
		baja := strings.ToLower(dato.Texto(a))
		if strings.Contains(baja, "firm") && contieneAlguno(baja, "operador", " or ", "or ", "usuario", "cliente") {
			conservar = append(conservar, a)
		}
	}
	if strings.ToUpper(dato.Texto(qa["or_firma"])) == "NO" {
		yaEsta := false
		for _, k := range conservar {
			baja := strings.ToLower(dato.Texto(k))
			if strings.Contains(baja, "operador") && strings.Contains(baja, "firm") {
				yaEsta = true
				break
			}
		}
		if !yaEsta {
			conservar = append(conservar, "El Operador de Red NO firmó el acta.")
		}
	}
	qa["alertas_qa"] = conservar

	falla := dato.Hijo(qa, "tipificacion_falla")
	if !dato.Verdadero(falla) {
		falla = dato.Objeto{}
	}
	falla["cinco_por_que"] = []any{}
	qa["tipificacion_falla"] = falla
}
