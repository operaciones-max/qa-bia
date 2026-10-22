package cierre

import (
	"context"
	"strings"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/metabase"
)

func tipo(t *testing.T, codigo string) catalogo.TipoOT {
	t.Helper()
	tipo, ok := catalogo.TipoOTPorCodigo(codigo)
	if !ok {
		t.Fatalf("no existe %s", codigo)
	}
	return tipo
}

func TestMensajeTraeTodasLasFuentesEnOrden(t *testing.T) {
	m := Mensaje(Caso{
		Tipo: tipo(t, "INST"), TipoServicio: "Instalación", EstadoReportado: "COMPLETED", CodigoCO: "CO001",
		Acta:         dato.Objeto{"estado_ot": "EXITOSA", "tipificacion_falla": dato.Objeto{}, "tipo_medida": "DIRECTA"},
		TextoActa:    "ACTA DE INSTALACION",
		Alcance:      metabase.Fila{"Viable Para Instalar": "Si", "Tipo De Medida A Instalar": "DIRECTA"},
		Equipos:      &metabase.EquiposWMS{Medidor: &metabase.Equipo{Serial: "123", Marca: "ELSTER", Estado: "ASIGNADO"}},
		Validaciones: dato.Objeto{"medidor_coincide_wms": true},
	})
	orden := []string{"TIPO DE OT: INST (Instalación)", "ESTADO REPORTADO: COMPLETED", "--- ACTA EXTRAIDA (JSON) ---",
		`"tipo_medida": "DIRECTA"`, "--- TEXTO DEL ACTA ---", "ACTA DE INSTALACION", "--- ALCANCE ---",
		"Tipo De Medida A Instalar: DIRECTA", "--- EQUIPOS ASIGNADOS (WMS) ---", "Medidor: 123 (ELSTER, ASIGNADO)",
		"--- NOTAS ---", "(NO DISPONIBLE", "--- VALIDACIONES DEL BACKEND ---", `"medidor_coincide_wms": true`}
	pos := 0
	for _, parte := range orden {
		i := strings.Index(m[pos:], parte)
		if i == -1 {
			t.Fatalf("falta %q (o esta fuera de orden) en:\n%s", parte, m)
		}
		pos += i
	}
	if strings.Contains(m, "estado_ot") || strings.Contains(m, "tipificacion_falla") {
		t.Error("el subagente no debe recibir estado_ot ni la tipificacion de la extraccion")
	}
}

func TestMensajeSinFuentesLasMarcaNoDisponibles(t *testing.T) {
	m := Mensaje(Caso{Tipo: tipo(t, "VIPE"), Acta: dato.Objeto{}})
	for _, parte := range []string{"(NO DISPONIBLE: el PDF no trae texto", "(NO DISPONIBLE: el cliente no tiene alcance",
		"(NO DISPONIBLE: el cliente no tiene equipos"} {
		if !strings.Contains(m, parte) {
			t.Errorf("falta %q", parte)
		}
	}
}

func TestValidarAjustaElVeredicto(t *testing.T) {
	// VIPE no admite PENDIENTE: pasa a FALLIDA y se dice por que.
	r, err := Validar(dato.Objeto{"veredicto": "pendiente", "pendientes": []any{"Legalización"}}, Caso{Tipo: tipo(t, "VIPE")})
	if err != nil || r["veredicto"] != "FALLIDA" || len(dato.Lista(r["pendientes"])) != 0 {
		t.Fatalf("r = %v, err = %v", r, err)
	}
	if !strings.Contains(strings.Join(dato.Textos(r["hallazgos"]), " "), "no admite") {
		t.Errorf("hallazgos = %v", r["hallazgos"])
	}
	// INST si admite PENDIENTE.
	r, _ = Validar(dato.Objeto{"veredicto": "PENDIENTE", "pendientes": []any{"Legalización"}}, Caso{Tipo: tipo(t, "INST")})
	if r["veredicto"] != "PENDIENTE" || len(dato.Lista(r["pendientes"])) != 1 || r["subagente"] != "INST" {
		t.Errorf("r = %v", r)
	}
	// La causa se ajusta al catalogo y la exitosa no lleva tipificacion.
	r, _ = Validar(dato.Objeto{"veredicto": "FALLIDA", "tipificacion_falla": dato.Objeto{"causa_raiz": "fallas en el alistamiento operativo"}},
		Caso{Tipo: tipo(t, "INST"), Acta: dato.Objeto{}})
	if tf := dato.Mapa(r["tipificacion_falla"]); tf["causa_raiz"] != "Fallas en el Alistamiento Operativo" || tf["responsable"] != "Contratista" {
		t.Errorf("tipificacion = %v", r["tipificacion_falla"])
	}
	r, _ = Validar(dato.Objeto{"veredicto": "EXITOSA", "tipificacion_falla": dato.Objeto{"causa_raiz": "x"}}, Caso{Tipo: tipo(t, "COND")})
	if r["tipificacion_falla"] != nil || r["borrador"] != true {
		t.Errorf("r = %v", r)
	}
	if _, err := Validar(dato.Objeto{"veredicto": "TAL VEZ"}, Caso{Tipo: tipo(t, "INST")}); err == nil {
		t.Error("un veredicto invalido deberia dar error")
	}
}

type subagenteFalso struct{ codigo, mensaje string }

func (s *subagenteFalso) EvaluarCierre(_ context.Context, codigo, mensaje string) (dato.Objeto, error) {
	s.codigo, s.mensaje = codigo, mensaje
	return dato.Objeto{"veredicto": "EXITOSA", "acta_completa": false, "campos_faltantes": []any{"Medidor instalado: sellos"}}, nil
}

func TestEvaluarUsaElSubagenteDeLaOT(t *testing.T) {
	s := &subagenteFalso{}
	r, err := Evaluar(context.Background(), s, Caso{Tipo: tipo(t, "NOTE"), TipoServicio: "Normalización Telemedidas", Acta: dato.Objeto{}})
	if err != nil || s.codigo != "NOTE" || !strings.Contains(s.mensaje, "TIPO DE OT: NOTE") {
		t.Fatalf("codigo = %q, err = %v", s.codigo, err)
	}
	if r["veredicto"] != "EXITOSA" || r["familia"] != "normalizacion" {
		t.Errorf("r = %v", r)
	}
}
