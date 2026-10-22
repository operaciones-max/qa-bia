package web

import "testing"

func ptr[T any](v T) *T { return &v }

func TestFormatearFechaAceptaElFormatoDeMetabaseYElISO(t *testing.T) {
	casos := []struct {
		valor   *string
		conHora bool
		esper   string
	}{
		{ptr("2026-05-20 14:03:00"), false, "20 may 2026"},
		{ptr("2026-05-20T14:03:00Z"), true, "20 may 2026 14:03"},
		{nil, false, "—"},
		{ptr("ayer"), false, "ayer"},
	}
	for _, c := range casos {
		if got := FormatearFecha(c.valor, c.conHora); got != c.esper {
			t.Errorf("FormatearFecha(%v) = %q, esperado %q", c.valor, got, c.esper)
		}
	}
}

func TestTextoTrataNullVacioYNoneComoSinDato(t *testing.T) {
	for _, v := range []any{nil, (*string)(nil), "  ", "None", "null"} {
		if Texto(v) != "—" {
			t.Errorf("Texto(%#v) = %q", v, Texto(v))
		}
	}
	if Texto(float64(2)) != "2" || Texto(1.5) != "1.5" {
		t.Error("numeros mal formateados")
	}
}

func TestElVeredictoDelRevisorMandaSobreAppOps(t *testing.T) {
	a := ActaQA{EstadoOT: ptr("EXITOSA")}
	if a.EstadoFinal() != "EXITOSA" {
		t.Fatal("sin revision manda App Ops")
	}
	a.RevisionResultado = ptr("FALLIDA")
	if a.EstadoFinal() != "FALLIDA" {
		t.Fatal("la revision manda")
	}
}

func TestDiscrepanciasSoloCuandoAlgunaComparacionEsFalse(t *testing.T) {
	a := ActaQA{MedidorCoincideWMS: ptr(true)}
	if a.TieneDiscrepancias() {
		t.Fatal("no deberia haber discrepancias")
	}
	a.MedidorCoincideFacturaAnterior = ptr(false)
	if !a.TieneDiscrepancias() {
		t.Fatal("deberia haber discrepancias")
	}
	if TonoCoincidencia(nil) != "gris" || TextoFactura(ptr("ok_sin_serial")) != "Leída, sin serial" || Numero(1234567) != "1.234.567" {
		t.Fatal("formato inesperado")
	}
}
