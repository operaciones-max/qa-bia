package web

import (
	"encoding/json"
	"fmt"
	"html/template"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

var meses = []string{"ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"}

var reFechaHora = regexp.MustCompile(`^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?`)

// FormatearFecha convierte "2026-05-20 14:03:00" o ISO en "20 may 2026" (con hora si conHora).
func FormatearFecha(valor *string, conHora bool) string {
	if valor == nil || *valor == "" {
		return "—"
	}
	m := reFechaHora.FindStringSubmatch(*valor)
	if m == nil {
		return *valor
	}
	mes, _ := strconv.Atoi(m[2])
	dia, _ := strconv.Atoi(m[3])
	if mes < 1 || mes > 12 {
		return *valor
	}
	f := fmt.Sprintf("%d %s %s", dia, meses[mes-1], m[1])
	if conHora && m[4] != "" {
		f += " " + m[4] + ":" + m[5]
	}
	return f
}

// Texto muestra un valor o "—" si no hay dato.
func Texto(v any) string {
	switch x := v.(type) {
	case nil:
		return "—"
	case *string:
		if x == nil {
			return "—"
		}
		return Texto(*x)
	case string:
		s := strings.TrimSpace(x)
		if s == "" || s == "null" || s == "None" {
			return "—"
		}
		return s
	case float64:
		return strconv.FormatFloat(x, 'f', -1, 64)
	default:
		return Texto(fmt.Sprint(x))
	}
}

// SiNo muestra un booleano como Sí / No / —.
func SiNo(v *bool) string {
	switch {
	case v == nil:
		return "—"
	case *v:
		return "Sí"
	default:
		return "No"
	}
}

// TonoCoincidencia: true verde, false rojo, sin dato gris.
func TonoCoincidencia(v *bool) string {
	switch {
	case v == nil:
		return "gris"
	case *v:
		return "verde"
	default:
		return "rojo"
	}
}

// TextoCoincidencia: Coincide / No coincide / No aplica.
func TextoCoincidencia(v *bool) string {
	switch {
	case v == nil:
		return "No aplica"
	case *v:
		return "Coincide"
	default:
		return "No coincide"
	}
}

// TonoEstado colorea EXITOSA en verde y FALLIDA en rojo.
func TonoEstado(estado string) string {
	switch estado {
	case "EXITOSA":
		return "verde"
	case "FALLIDA":
		return "rojo"
	}
	return "gris"
}

// EstadoFinal: el veredicto del revisor manda sobre el estado de App Ops.
func (a ActaQA) EstadoFinal() string {
	if a.RevisionResultado != nil && *a.RevisionResultado != "" {
		return *a.RevisionResultado
	}
	if a.EstadoOT != nil {
		return *a.EstadoOT
	}
	return ""
}

// TieneDiscrepancias indica si alguna comparacion automatica dio false.
func (a ActaQA) TieneDiscrepancias() bool {
	for _, v := range []*bool{a.MedidorCoincideWMS, a.TCsCoincidenWMS, a.TPsCoincidenWMS, a.MedidorCoincideFacturaAnterior} {
		if v != nil && !*v {
			return true
		}
	}
	return false
}

var etiquetasFactura = map[string]string{
	"ok":            "Leída",
	"ok_sin_serial": "Leída, sin serial",
	"borrosa":       "No se pudo leer",
	"no_disponible": "Sin factura",
}

// TextoFactura traduce factura_anterior_estado.
func TextoFactura(estado *string) string {
	if estado == nil || *estado == "" {
		return "—"
	}
	if e, ok := etiquetasFactura[*estado]; ok {
		return e
	}
	return *estado
}

// estadosCruce traduce los estados de verificacion_equipos.cruces (backend/verificacion).
var estadosCruce = map[string][2]string{
	"coincide":                 {"verde", "Coincide"},
	"no_coincide":              {"rojo", "No coincide"},
	"posible_error_digitacion": {"ambar", "¿Error de digitación?"},
	"falta_en_acta":            {"ambar", "Falta en el acta"},
	"sin_dato":                 {"gris", "Sin dato"},
}

// TonoCruce y TextoCruce dan el color y el texto de un estado de cruce.
func TonoCruce(v any) string {
	if e, ok := estadosCruce[fmt.Sprint(v)]; ok {
		return e[0]
	}
	return "gris"
}

func TextoCruce(v any) string {
	if e, ok := estadosCruce[fmt.Sprint(v)]; ok {
		return e[1]
	}
	return "—"
}

// Numero formatea un entero con separador de miles ("1.234").
func Numero(n int) string {
	s := strconv.Itoa(n)
	var out []byte
	for i := range s {
		if i > 0 && (len(s)-i)%3 == 0 {
			out = append(out, '.')
		}
		out = append(out, s[i])
	}
	return string(out)
}

// funciones disponibles en las plantillas.
var funciones = template.FuncMap{
	"fecha":             func(v *string) string { return FormatearFecha(v, false) },
	"fechaHora":         func(v *string) string { return FormatearFecha(v, true) },
	"texto":             Texto,
	"tonoCruce":         TonoCruce,
	"textoCruce":        TextoCruce,
	"siNo":              SiNo,
	"tonoCoincidencia":  TonoCoincidencia,
	"textoCoincidencia": TextoCoincidencia,
	"tonoEstado":        TonoEstado,
	"textoFactura":      TextoFactura,
	"numero":            Numero,
	"deref": func(s *string) string {
		if s == nil {
			return ""
		}
		return *s
	},
	"deref2": func(b *bool) bool { return b != nil && *b },
	"es":     func(s *string, v string) bool { return s != nil && *s == v },
	"urlDetalle": func(id, query string) template.URL {
		u := "/actas/" + url.PathEscape(id)
		if query != "" {
			u += "?" + query
		}
		return template.URL(u)
	},
	"urlRevision": func(id string) template.URL { return template.URL("/actas/" + url.PathEscape(id) + "/revision") },
	"json": func(v any) string {
		data, _ := json.MarshalIndent(v, "", "  ")
		return string(data)
	},
	"seriales": func(l []EquipoWMS) string {
		var s []string
		for _, e := range l {
			s = append(s, e.Serial)
		}
		return Texto(strings.Join(s, ", "))
	},
	"campo":    func(m map[string]any, clave string) any { return m[clave] },
	"subcampo": func(m map[string]any, clave, sub string) any { mm, _ := m[clave].(map[string]any); return mm[sub] },
	"lista": func(v any) string {
		l, _ := v.([]any)
		var s []string
		for _, x := range l {
			s = append(s, fmt.Sprint(x))
		}
		return Texto(strings.Join(s, ", "))
	},
}
