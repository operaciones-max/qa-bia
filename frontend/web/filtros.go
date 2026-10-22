package web

import (
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

// Filtros son los filtros del listado. Viajan en la URL (?estadoOt=FALLIDA&p=2)
// para poder compartirlos y conservarlos al volver del detalle.
type Filtros struct {
	Busqueda         string
	TipoServicio     string
	EstadoOT         string // "", EXITOSA, FALLIDA
	QATrack          string // "", Activacion, Retencion, Energy Solutions
	Planner          string
	Revision         string // "", pendiente, EXITOSA, FALLIDA
	Desde            string // YYYY-MM-DD sobre fecha_ejecucion
	Hasta            string
	ConDiscrepancias bool
}

// ExpresionDiscrepancias: WMS o factura anterior no coinciden.
const ExpresionDiscrepancias = "(medidor_coincide_wms.eq.false,tcs_coinciden_wms.eq.false," +
	"tps_coinciden_wms.eq.false,medidor_coincide_factura_anterior.eq.false)"

var valoresValidos = map[string][]string{
	"estadoOt": {"EXITOSA", "FALLIDA"},
	"qaTrack":  {"Activacion", "Retencion", "Energy Solutions"},
	"revision": {"pendiente", "EXITOSA", "FALLIDA"},
}

var reFecha = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

func valido(clave, v string) string {
	for _, ok := range valoresValidos[clave] {
		if v == ok {
			return v
		}
	}
	return ""
}

func fecha(v string) string {
	if reFecha.MatchString(v) {
		return v
	}
	return ""
}

// FiltrosDesdeURL lee los filtros y la pagina (desde 0) de la query string.
func FiltrosDesdeURL(q url.Values) (Filtros, int) {
	f := Filtros{
		Busqueda:         strings.TrimSpace(q.Get("busqueda")),
		TipoServicio:     q.Get("tipoServicio"),
		EstadoOT:         valido("estadoOt", q.Get("estadoOt")),
		QATrack:          valido("qaTrack", q.Get("qaTrack")),
		Planner:          q.Get("planner"),
		Revision:         valido("revision", q.Get("revision")),
		Desde:            fecha(q.Get("desde")),
		Hasta:            fecha(q.Get("hasta")),
		ConDiscrepancias: q.Get("conDiscrepancias") == "1",
	}
	pagina, err := strconv.Atoi(q.Get("p"))
	if err != nil || pagina < 1 {
		pagina = 1
	}
	return f, pagina - 1
}

// URL devuelve la query string de los filtros y la pagina (desde 0).
func (f Filtros) URL(pagina int) url.Values {
	q := url.Values{}
	agregar := func(k, v string) {
		if v != "" {
			q.Set(k, v)
		}
	}
	agregar("busqueda", f.Busqueda)
	agregar("tipoServicio", f.TipoServicio)
	agregar("estadoOt", f.EstadoOT)
	agregar("qaTrack", f.QATrack)
	agregar("planner", f.Planner)
	agregar("revision", f.Revision)
	agregar("desde", f.Desde)
	agregar("hasta", f.Hasta)
	if f.ConDiscrepancias {
		q.Set("conDiscrepancias", "1")
	}
	if pagina > 0 {
		q.Set("p", strconv.Itoa(pagina+1))
	}
	return q
}

var reCaracteresOr = regexp.MustCompile(`[,()%*\\"]`)

// LimpiarBusqueda quita los caracteres que rompen un filtro `or` de PostgREST.
func LimpiarBusqueda(texto string) string {
	return strings.TrimSpace(reCaracteresOr.ReplaceAllString(texto, " "))
}

// Condiciones traduce los filtros a parametros de PostgREST (se pueden repetir).
func (f Filtros) Condiciones() url.Values {
	q := url.Values{}
	if b := LimpiarBusqueda(f.Busqueda); b != "" {
		patron := "*" + b + "*"
		var partes []string
		for _, col := range []string{"ot_nombre", "internal_bia_code", "tecnico_nombre", "empresa"} {
			partes = append(partes, col+".ilike."+patron)
		}
		q.Add("or", "("+strings.Join(partes, ",")+")")
	}
	if f.TipoServicio != "" {
		q.Add("tipo_servicio", "eq."+f.TipoServicio)
	}
	if f.EstadoOT != "" {
		q.Add("estado_ot", "eq."+f.EstadoOT)
	}
	if f.QATrack != "" {
		q.Add("qa_track", "eq."+f.QATrack)
	}
	if f.Planner != "" {
		q.Add("planner", "eq."+f.Planner)
	}
	switch f.Revision {
	case "pendiente":
		q.Add("revision_resultado", "is.null")
	case "EXITOSA", "FALLIDA":
		q.Add("revision_resultado", "eq."+f.Revision)
	}
	if f.Desde != "" {
		q.Add("fecha_ejecucion", "gte."+f.Desde)
	}
	if f.Hasta != "" {
		q.Add("fecha_ejecucion", "lte."+f.Hasta+" 23:59:59")
	}
	if f.ConDiscrepancias {
		q.Add("or", ExpresionDiscrepancias)
	}
	return q
}
