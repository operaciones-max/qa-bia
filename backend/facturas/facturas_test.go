package facturas

import "testing"

func TestSerialPorPatron(t *testing.T) {
	casos := []struct{ texto, serial, patron string }{
		{"No. Medidor: 8091012800", "8091012800", "Enel"},
		{"Datos de la Factura\nCliente X\nMedidor\n12345678-MC983", "12345678", "AFINIA (Datos de la Factura)"},
		{"Número de Medidor: AB1234", "AB1234", "Air-e/Aire"},
		{"Total\nMedidor\n99887766\n", "99887766", "Celsia (cuadro naranja)"},
		{"sin datos", "", ""},
	}
	for _, c := range casos {
		s, p := SerialPorPatron(c.texto)
		if s != c.serial || p != c.patron {
			t.Errorf("SerialPorPatron(%q) = %q, %q; esperado %q, %q", c.texto, s, p, c.serial, c.patron)
		}
	}
}
