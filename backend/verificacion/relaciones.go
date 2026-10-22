package verificacion

import (
	"math"
	"regexp"
	"strconv"
	"strings"
)

// Relacion es una relacion de transformacion primario/secundario (ej. 200/5).
type Relacion struct {
	Primario   float64
	Secundario float64
}

// Factor es primario / secundario: 200/5 = 40.
func (r Relacion) Factor() float64 { return r.Primario / r.Secundario }

var (
	reRaizTres = regexp.MustCompile(`(?i)\s*/\s*(√\s*3|raiz\s*\(?\s*3\s*\)?|sqrt\s*\(?\s*3\s*\)?)`)
	reNumero   = regexp.MustCompile(`(\d+(?:[.,]\d+)?)\s*(k)?`)
)

// ParsearRelacion entiende "200/5", "200:5 A", "200/5A", "13.2kV/120V" y
// "13200/√3 / 120/√3" (la raiz de 3 se cancela).
func ParsearRelacion(s string) (Relacion, bool) {
	s = reRaizTres.ReplaceAllString(strings.TrimSpace(s), "")
	numeros := reNumero.FindAllStringSubmatch(s, -1)
	if len(numeros) != 2 {
		return Relacion{}, false
	}
	valores := make([]float64, 2)
	for i, m := range numeros {
		v, err := strconv.ParseFloat(strings.ReplaceAll(m[1], ",", "."), 64)
		if err != nil {
			return Relacion{}, false
		}
		if strings.EqualFold(m[2], "k") {
			v *= 1000
		}
		valores[i] = v
	}
	if valores[0] <= 0 || valores[1] <= 0 {
		return Relacion{}, false
	}
	return Relacion{Primario: valores[0], Secundario: valores[1]}, true
}

// mismaRelacion compara dos relaciones escritas: igual primario y secundario.
// Si alguna no se entiende, compara el texto.
func mismaRelacion(a, b string) bool {
	ra, okA := ParsearRelacion(a)
	rb, okB := ParsearRelacion(b)
	if okA && okB {
		return casiIgual(ra.Primario, rb.Primario) && casiIgual(ra.Secundario, rb.Secundario)
	}
	return normalizarTexto(a) == normalizarTexto(b)
}

// FactorEsperado es el factor de medida que dan las relaciones: el de los TCs
// por el de los TPs. Sin TCs (medida directa) el factor es 1.
func FactorEsperado(aplica Aplica, relacionTCs, relacionTPs string) (float64, bool) {
	factor := 1.0
	if aplica.TCs {
		r, ok := ParsearRelacion(relacionTCs)
		if !ok {
			return 0, false
		}
		factor *= r.Factor()
	}
	if aplica.TPs {
		r, ok := ParsearRelacion(relacionTPs)
		if !ok {
			return 0, false
		}
		factor *= r.Factor()
	}
	return factor, true
}

var rePrimerNumero = regexp.MustCompile(`\d+(?:[.,]\d+)?`)

// numero lee el primer numero de un texto ("40", "x40", "40,0").
func numero(s string) (float64, bool) {
	m := rePrimerNumero.FindString(s)
	if m == "" {
		return 0, false
	}
	v, err := strconv.ParseFloat(strings.ReplaceAll(m, ",", "."), 64)
	return v, err == nil
}

func casiIgual(a, b float64) bool {
	return math.Abs(a-b) <= 0.005*math.Max(math.Abs(a), math.Abs(b))
}

func formatoFactor(f float64) string {
	return strconv.FormatFloat(math.Round(f*100)/100, 'f', -1, 64)
}

func normalizarTexto(s string) string {
	return strings.ToUpper(strings.Join(strings.Fields(s), ""))
}
