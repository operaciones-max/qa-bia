package web

import (
	"net/url"
	"reflect"
	"testing"
)

func TestSinFiltrosNoHayCondiciones(t *testing.T) {
	if q := (Filtros{}).Condiciones(); len(q) != 0 {
		t.Fatalf("condiciones = %v", q)
	}
}

func TestBusquedaEnVariasColumnasSinCaracteresQueRompanPostgREST(t *testing.T) {
	if got := LimpiarBusqueda(" VIPE_1,(x)% "); got != "VIPE_1  x" {
		t.Fatalf("LimpiarBusqueda = %q", got)
	}
	q := Filtros{Busqueda: "co080"}.Condiciones()
	esperado := "(ot_nombre.ilike.*co080*,internal_bia_code.ilike.*co080*,tecnico_nombre.ilike.*co080*,empresa.ilike.*co080*)"
	if q.Get("or") != esperado {
		t.Fatalf("or = %q", q.Get("or"))
	}
}

func TestRevisionPendienteEsNullYElRestoIgualdad(t *testing.T) {
	if got := (Filtros{Revision: "pendiente"}).Condiciones().Get("revision_resultado"); got != "is.null" {
		t.Fatalf("got %q", got)
	}
	if got := (Filtros{Revision: "FALLIDA"}).Condiciones().Get("revision_resultado"); got != "eq.FALLIDA" {
		t.Fatalf("got %q", got)
	}
}

func TestRangoDeFechasYDiscrepanciasSeCombinanConAnd(t *testing.T) {
	q := Filtros{Desde: "2026-05-01", Hasta: "2026-05-31", ConDiscrepancias: true, Busqueda: "x"}.Condiciones()
	if !reflect.DeepEqual(q["fecha_ejecucion"], []string{"gte.2026-05-01", "lte.2026-05-31 23:59:59"}) {
		t.Fatalf("fechas = %v", q["fecha_ejecucion"])
	}
	// Dos parametros `or` separados: PostgREST los combina con AND.
	if len(q["or"]) != 2 || q["or"][1] != ExpresionDiscrepancias {
		t.Fatalf("or = %v", q["or"])
	}
}

func TestFiltrosIdaYVueltaPorLaURL(t *testing.T) {
	f := Filtros{Planner: "Dinovi Sanchez", ConDiscrepancias: true, QATrack: "Retencion"}
	q := f.URL(2)
	if q.Encode() != "conDiscrepancias=1&p=3&planner=Dinovi+Sanchez&qaTrack=Retencion" {
		t.Fatalf("URL = %s", q.Encode())
	}
	g, pagina := FiltrosDesdeURL(q)
	if g != f || pagina != 2 {
		t.Fatalf("vuelta = %+v, %d", g, pagina)
	}
}

func TestValoresInvalidosEnLaURLSeIgnoran(t *testing.T) {
	q, _ := url.ParseQuery("p=abc&estadoOt=TODAS&revision=x&desde=ayer&qaTrack=Retencion")
	f, pagina := FiltrosDesdeURL(q)
	if f != (Filtros{QATrack: "Retencion"}) || pagina != 0 {
		t.Fatalf("got %+v, %d", f, pagina)
	}
}
