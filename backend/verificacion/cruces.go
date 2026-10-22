package verificacion

import (
	"github.com/operaciones-max/qa-bia/backend/util"
)

// Estado es el resultado de cruzar el dato del acta con otra fuente.
type Estado string

const (
	Coincide        Estado = "coincide"
	NoCoincide      Estado = "no_coincide"
	ErrorDigitacion Estado = "posible_error_digitacion" // difieren en 1 o 2 caracteres
	FaltaEnActa     Estado = "falta_en_acta"            // la otra fuente lo tiene y el acta no
	SinDato         Estado = "sin_dato"                 // la otra fuente no lo tiene
)

// Cruce es un dato de un equipo visto en las tres fuentes: lo escrito en el
// acta, lo que se ve en la foto y lo que dice el sistema.
type Cruce struct {
	Equipo        string `json:"equipo"`
	Dato          string `json:"dato"` // "serie", "relación" o "factor"
	Acta          string `json:"acta"`
	Foto          string `json:"foto"`
	Sistema       string `json:"sistema"`
	Fuente        string `json:"fuente_sistema"` // factura anterior, visita previa, WMS asignado…
	ActaVsFoto    Estado `json:"acta_vs_foto"`
	ActaVsSistema Estado `json:"acta_vs_sistema"`
}

// compararSerie cruza dos series ignorando separadores y ceros a la izquierda.
func compararSerie(acta, otra string) Estado {
	a, o := util.NormalizarSerial(acta), util.NormalizarSerial(otra)
	switch {
	case o == "":
		return SinDato
	case a == "":
		return FaltaEnActa
	case a == o:
		return Coincide
	case distancia(a, o) <= 2 && min(len(a), len(o)) >= 5:
		return ErrorDigitacion
	}
	return NoCoincide
}

// compararRelacion cruza dos relaciones de transformacion.
func compararRelacion(acta, otra string) Estado {
	switch {
	case otra == "":
		return SinDato
	case acta == "":
		return FaltaEnActa
	case mismaRelacion(acta, otra):
		return Coincide
	}
	return NoCoincide
}

// emparejar asigna a cada serie del acta una de la otra lista: primero las
// exactas y despues la mas parecida (a 1 o 2 caracteres) entre las que quedan.
// Devuelve el emparejamiento ("" si no hay) y las de la otra lista sin usar.
func emparejar(acta, otras []string) (pares []string, sobrantes []string) {
	pares = make([]string, len(acta))
	usada := make([]bool, len(otras))
	for i, a := range acta {
		for j, o := range otras {
			if !usada[j] && util.NormalizarSerial(a) != "" && util.NormalizarSerial(a) == util.NormalizarSerial(o) {
				pares[i], usada[j] = o, true
				break
			}
		}
	}
	for i, a := range acta {
		if pares[i] != "" {
			continue
		}
		mejor, mejorDist := -1, 3
		for j, o := range otras {
			if usada[j] || util.NormalizarSerial(o) == "" {
				continue
			}
			if d := distancia(util.NormalizarSerial(a), util.NormalizarSerial(o)); d < mejorDist {
				mejor, mejorDist = j, d
			}
		}
		if mejor >= 0 {
			pares[i], usada[mejor] = otras[mejor], true
		}
	}
	for j, o := range otras {
		if !usada[j] && util.NormalizarSerial(o) != "" {
			sobrantes = append(sobrantes, o)
		}
	}
	return pares, sobrantes
}

// cruzarSeries arma un cruce por cada serie de un grupo de equipos (TCs o TPs):
// las del acta contra las de las fotos y las del sistema, y agrega las que
// estan en el sistema o en la foto pero no en el acta.
func cruzarSeries(equipo string, acta, fotos, sistema []string, fuente string) []Cruce {
	paresFoto, sobranFoto := emparejar(acta, fotos)
	paresSistema, sobranSistema := emparejar(acta, sistema)
	var cruces []Cruce
	for i, serie := range acta {
		c := Cruce{Equipo: equipo, Dato: "serie", Acta: serie, Foto: paresFoto[i], Sistema: paresSistema[i],
			Fuente: fuente, ActaVsFoto: SinDato, ActaVsSistema: SinDato}
		// Las fotos no siempre muestran todos los equipos: sin pareja en la
		// foto queda sin dato. Lo asignado en WMS si es la lista completa.
		if c.Foto != "" {
			c.ActaVsFoto = compararSerie(serie, c.Foto)
		}
		if len(sistema) > 0 {
			c.ActaVsSistema = compararSerieEnLista(serie, c.Sistema)
		}
		cruces = append(cruces, c)
	}
	for _, s := range sobranSistema {
		cruces = append(cruces, Cruce{Equipo: equipo, Dato: "serie", Sistema: s, Fuente: fuente,
			ActaVsFoto: SinDato, ActaVsSistema: FaltaEnActa})
	}
	for _, f := range sobranFoto {
		cruces = append(cruces, Cruce{Equipo: equipo, Dato: "serie", Foto: f, Fuente: fuente,
			ActaVsFoto: FaltaEnActa, ActaVsSistema: SinDato})
	}
	return cruces
}

// compararSerieEnLista: si no hubo parecido en la lista, es que no coincide.
func compararSerieEnLista(acta, encontrada string) Estado {
	if encontrada == "" {
		return NoCoincide
	}
	return compararSerie(acta, encontrada)
}

// distancia de Levenshtein entre dos textos.
func distancia(a, b string) int {
	ra, rb := []rune(a), []rune(b)
	prev := make([]int, len(rb)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(ra); i++ {
		cur := make([]int, len(rb)+1)
		cur[0] = i
		for j := 1; j <= len(rb); j++ {
			costo := 1
			if ra[i-1] == rb[j-1] {
				costo = 0
			}
			cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+costo)
		}
		prev = cur
	}
	return prev[len(rb)]
}
