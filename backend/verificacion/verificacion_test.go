package verificacion

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/ia"
)

func acta(t *testing.T, s string) dato.Objeto {
	t.Helper()
	var o dato.Objeto
	if err := dato.Decodificar([]byte(s), &o); err != nil {
		t.Fatal(err)
	}
	return o
}

func buscar(r Resultado, equipo, d, fuente string) Cruce {
	for _, c := range r.Cruces {
		if c.Equipo == equipo && c.Dato == d && (fuente == "" || strings.HasPrefix(c.Fuente, fuente)) {
			return c
		}
	}
	return Cruce{}
}

func TestAplicaSegunTipoDeMedida(t *testing.T) {
	casos := map[string]Aplica{
		"DIRECTA":     {Conocida: true},
		"semidirecta": {Conocida: true, TCs: true, BloquePruebas: true, CableControl: true},
		"INDIRECTA":   {Conocida: true, TCs: true, TPs: true, BloquePruebas: true, CableControl: true},
		"":            {},
	}
	for tipo, esperado := range casos {
		if got := AplicaPara(tipo); got != esperado {
			t.Errorf("%q: %+v, esperado %+v", tipo, got, esperado)
		}
	}
}

func TestParsearRelacion(t *testing.T) {
	casos := map[string]float64{
		"200/5":             40,
		"200:5 A":           40,
		"300/5A":            60,
		"13.2kV/120V":       110,
		"13200/√3 / 120/√3": 110,
		"13,2 kV / 120 V":   110,
	}
	for s, factor := range casos {
		r, ok := ParsearRelacion(s)
		if !ok || !casiIgual(r.Factor(), factor) {
			t.Errorf("%q: %+v %v, esperado factor %v", s, r, ok, factor)
		}
	}
	for _, s := range []string{"", "doscientos", "200", "1/2/3"} {
		if _, ok := ParsearRelacion(s); ok {
			t.Errorf("%q no deberia entenderse", s)
		}
	}
}

func TestCompararSerie(t *testing.T) {
	casos := []struct {
		acta, otra string
		esperado   Estado
	}{
		{"0060714646", "60714646", Coincide},
		{"60-714-646", "60714646", Coincide},
		{"60714646", "60714645", ErrorDigitacion},
		{"6071464", "60714646", ErrorDigitacion},
		{"60714646", "82084260", NoCoincide},
		{"", "60714646", FaltaEnActa},
		{"60714646", "", SinDato},
	}
	for _, c := range casos {
		if got := compararSerie(c.acta, c.otra); got != c.esperado {
			t.Errorf("%q vs %q: %s, esperado %s", c.acta, c.otra, got, c.esperado)
		}
	}
}

const vipeSemidirecta = `{
  "tipo_medida": "SEMIDIRECTA", "factor_medida": "40",
  "transformador": {"tiene": true, "capacidad_kva": "75", "tipo_uso": "EXCLUSIVO"},
  "medidor_encontrado": {"serie": "60714646", "marca": "LANDIS GYR", "referencia": "E550",
    "lectura_activa_kwh": "1200", "lectura_reactiva_kvarh": "300"},
  "tcs_encontrados": {"aplica": true, "tiene": true, "seriales": ["A1", "A2", "A3"], "relacion": "200/5"},
  "tps_encontrados": {"aplica": false, "tiene": false, "seriales": []},
  "totalizador_encontrado": {"tiene": false},
  "cables_potencia_encontrados": {"tiene": true, "calibre_acometida": "4/0", "cables_por_fase_acometida": "1"}
}`

func TestVIPEFacturaYFoto(t *testing.T) {
	fotos := &Fotos{
		MedidorEncontrado: &SerieFoto{Serie: "60714646", Pagina: 3},
		TCsEncontrados:    []PlacaFoto{{Serie: "A1", Relacion: "200/5"}, {Serie: "A2", Relacion: "200/5"}},
	}
	r := Verificar(Entrada{TipoOT: "VIPE", Acta: acta(t, vipeSemidirecta), Fotos: fotos,
		Factura: Factura{Serial: "82084260", Estado: "ok"}})

	med := buscar(r, "Medidor encontrado", "serie", "factura")
	if med.ActaVsFoto != Coincide || med.ActaVsSistema != NoCoincide {
		t.Errorf("medidor encontrado = %+v", med)
	}
	if rel := buscar(r, "TCs encontrados", "relación", ""); rel.ActaVsFoto != Coincide {
		t.Errorf("relacion TCs = %+v", rel)
	}
	if f := buscar(r, "Factor de medida", "factor", ""); f.ActaVsSistema != Coincide || f.ActaVsFoto != Coincide || f.Sistema != "40" {
		t.Errorf("factor = %+v", f)
	}
	if len(r.CamposFaltantes) != 0 {
		t.Errorf("faltantes = %v", r.CamposFaltantes)
	}
	// Los TPs no aplican en semidirecta.
	if c := buscar(r, "TPs encontrados", "relación", ""); c.Equipo != "" {
		t.Error("en semidirecta no se cruzan TPs")
	}
	hallazgos := strings.Join(r.Hallazgos(), "\n")
	if !strings.Contains(hallazgos, `Medidor encontrado (serie): el acta dice "60714646" y factura anterior dice "82084260"`) {
		t.Errorf("hallazgos:\n%s", hallazgos)
	}
}

func TestCamposFaltantesSegunMedida(t *testing.T) {
	a := acta(t, vipeSemidirecta)
	dato.Hijo(a, "tcs_encontrados")["relacion"] = nil
	dato.Hijo(a, "medidor_encontrado")["marca"] = ""
	r := Verificar(Entrada{TipoOT: "VIPE", Acta: a})
	faltan := strings.Join(r.CamposFaltantes, "; ")
	if !strings.Contains(faltan, "TCs encontrados: relación") || !strings.Contains(faltan, "Medidor encontrado: marca") {
		t.Errorf("faltantes = %s", faltan)
	}
	// En directa no se exigen TCs aunque vengan vacios.
	a["tipo_medida"], a["factor_medida"] = "DIRECTA", "1"
	r = Verificar(Entrada{TipoOT: "VIPE", Acta: a})
	if strings.Contains(strings.Join(r.CamposFaltantes, ";"), "TCs") {
		t.Errorf("en directa no aplican TCs: %v", r.CamposFaltantes)
	}
	if f := buscar(r, "Factor de medida", "factor", ""); f.Sistema != "1" || f.ActaVsSistema != Coincide {
		t.Errorf("factor directa = %+v", f)
	}
	if r.FotosLeidas {
		t.Error("sin fotos, FotosLeidas debe ser false")
	}
}

const instIndirecta = `{
  "tipo_medida": "INDIRECTA", "factor_medida": "1000",
  "medidor_encontrado": {"serie": "11111111", "marca": "X", "referencia": "R", "lectura_activa_kwh": "1", "lectura_reactiva_kvarh": "1"},
  "tcs_encontrados": {"seriales": ["E1", "E2", "E3"], "relacion": "50/5"},
  "tps_encontrados": {"seriales": ["P1", "P2", "P3"], "relacion": "13200/120"},
  "medidor_instalado": {"se_instalo": true, "serie": "22222222", "marca": "Y", "referencia": "R", "lectura_activa_kwh": "0"},
  "sellos_medidor_instalado": 3,
  "tcs_instalados": {"se_instalo": true, "seriales": ["T10001", "T10002", "T10003", "", null], "marca": "Z", "relacion": "50/5"},
  "sellos_tcs_instalados": 3,
  "tps_instalados": {"se_instalo": false},
  "telemedida_instalada": {"se_instalo": false},
  "pruebas_funcionamiento": {"se_realizaron": true}
}`

func TestINSTCruzaConWMSYVisitaPrevia(t *testing.T) {
	fotos := &Fotos{
		MedidorInstalado: &SerieFoto{Serie: "22222222"},
		TCsInstalados:    []PlacaFoto{{Serie: "T10001", Relacion: "50/5"}, {Serie: "T10002", Relacion: "50/5"}},
		TPsEncontrados:   []PlacaFoto{{Serie: "P1", Relacion: "13200/120"}},
	}
	r := Verificar(Entrada{
		TipoOT: "INST", Acta: acta(t, instIndirecta), Fotos: fotos,
		Factura:      Factura{Serial: "11111111", Estado: "ok"},
		VisitaPrevia: &VisitaPrevia{OT: "VIPE_1", MedidorSerie: "11111111"},
		Asignados:    &Asignados{Medidor: "33333333", TCs: []string{"T10001", "T10002", "T10004"}},
	})

	if c := buscar(r, "Medidor encontrado", "serie", "visita previa"); c.ActaVsSistema != Coincide {
		t.Errorf("medidor encontrado vs VIPE = %+v", c)
	}
	inst := buscar(r, "Medidor instalado", "serie", "WMS")
	if inst.ActaVsFoto != Coincide || inst.ActaVsSistema != NoCoincide || inst.Sistema != "33333333" {
		t.Errorf("medidor instalado = %+v", inst)
	}
	// T10003 no es el asignado (T10004 lo es: difiere en un caracter) y T10004 no esta en el acta.
	var t3, t4 Cruce
	for _, c := range r.Cruces {
		if c.Equipo == "TCs instalados" && c.Acta == "T10003" {
			t3 = c
		}
		if c.Equipo == "TCs instalados" && c.Acta == "" && c.Sistema == "T10004" {
			t4 = c
		}
	}
	if t3.ActaVsSistema != ErrorDigitacion || t3.ActaVsFoto != SinDato {
		t.Errorf("T10003 = %+v", t3)
	}
	for _, c := range r.Cruces {
		if c.Equipo == "TCs instalados" && c.Dato == "serie" && c.Acta == "" && c.Sistema == "" && c.Foto == "" {
			t.Errorf("una serie vacia del acta no es un cruce: %+v", c)
		}
	}
	if t4.Equipo != "" {
		t.Errorf("T10004 ya se emparejo con T10003, no deberia quedar suelto: %+v", t4)
	}
	// Factor: 50/5 = 10 por 13200/120 = 110 → 1100, el acta dice 1000.
	if f := buscar(r, "Factor de medida", "factor", ""); f.Sistema != "1100" || f.ActaVsSistema != NoCoincide || f.Foto != "1100" {
		t.Errorf("factor = %+v", f)
	}
	if len(r.CamposFaltantes) != 0 {
		t.Errorf("faltantes = %v", r.CamposFaltantes)
	}
	r = Verificar(Entrada{TipoOT: "INST", Acta: acta(t, instIndirecta), Asignados: &Asignados{TCs: []string{"X99999"}}})
	if h := strings.Join(r.Hallazgos(), "\n"); !strings.Contains(h, `TCs instalados (serie): "T10001" no está en WMS asignado`) {
		t.Errorf("hallazgos:\n%s", h)
	}
}

func TestINSTSinPruebasNiSerieInstalada(t *testing.T) {
	a := acta(t, instIndirecta)
	dato.Hijo(a, "pruebas_funcionamiento")["se_realizaron"] = false
	dato.Hijo(a, "medidor_instalado")["serie"] = nil
	r := Verificar(Entrada{TipoOT: "INST", Acta: a})
	faltan := strings.Join(r.CamposFaltantes, "; ")
	if !strings.Contains(faltan, "Pruebas de funcionamiento") || !strings.Contains(faltan, "Medidor instalado: serie") {
		t.Errorf("faltantes = %s", faltan)
	}
	if !strings.Contains(strings.Join(r.Observaciones, " "), "WMS") {
		t.Errorf("deberia avisar que no hay equipos asignados: %v", r.Observaciones)
	}
}

func TestPaginasConFotos(t *testing.T) {
	textos := []string{
		"Datos del cliente",
		"Registro fotografico medidor, sellos y celdas\nBia 2 may 2026 09:52:45",
		"Firma\nBia 2 may 2026 10:01:00",
		"Registro fotografico de TCs instalados\nBia 2 may 2026 10:05:10",
	}
	paginas, recortadas := PaginasConFotos(textos)
	if fmt.Sprint(paginas) != "[1 3]" || recortadas {
		t.Errorf("paginas = %v, recortadas = %v", paginas, recortadas)
	}
}

type lectorFalso struct{ paginas []int }

func (l *lectorFalso) LeerFotosEquipos(_ context.Context, paginas []ia.PaginaImagen, _, _ string) (json.RawMessage, error) {
	for _, p := range paginas {
		l.paginas = append(l.paginas, p.Numero)
	}
	return json.RawMessage(`{"medidor_encontrado": {"serie": "60714646", "pagina": 1}, "tcs_encontrados": [], "observaciones": ["placa del TC 2 tapada"]}`), nil
}

func TestLeerFotosMandaSoloLasPaginasConEquipos(t *testing.T) {
	contenido := "BT /F1 12 Tf 72 720 Td (Registro fotografico medidor Bia 2 may 2026 09:52:45) Tj ET"
	pdfBytes := []byte(fmt.Sprintf(`%%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length %d >> stream
%s
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
trailer << /Root 1 0 R >>
%%%%EOF
`, len(contenido), contenido))

	lector := &lectorFalso{}
	fotos, err := LeerFotos(context.Background(), lector, pdfBytes, "VIPE", "DIRECTA")
	if err != nil {
		t.Fatal(err)
	}
	if fotos == nil || fotos.MedidorEncontrado.Serie != "60714646" || fmt.Sprint(lector.paginas) != "[1]" {
		t.Fatalf("fotos = %+v, paginas = %v", fotos, lector.paginas)
	}
	if len(fotos.Observaciones) != 1 {
		t.Errorf("observaciones = %v", fotos.Observaciones)
	}
}
