package catalogo

import (
	"testing"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

func TestQATrack(t *testing.T) {
	casos := map[string]string{
		"Visita previa":            "Activacion",
		"Instalación":              "Activacion",
		"Mantenimiento preventivo": "Energy Solutions",
		"PQR":                      "Retencion",
	}
	for tipo, esperado := range casos {
		if got := QATrack(tipo); got != esperado {
			t.Errorf("QATrack(%q) = %q, esperado %q", tipo, got, esperado)
		}
	}
}

func TestWMSSoloParaActivacionYNormalizacionExacta(t *testing.T) {
	if !RequiereComparacionWMS("Instalación", "Activacion") ||
		!RequiereComparacionWMS("Normalización medida", "Retencion") ||
		RequiereComparacionWMS("Normalizacion Telemedidas", "Retencion") {
		t.Fatal("reglas de comparacion WMS incorrectas")
	}
}

func causa(qa dato.Objeto) (string, string) {
	f := dato.Hijo(qa, "tipificacion_falla")
	return dato.Texto(f["causa_raiz"]), dato.Texto(f["responsable"])
}

func TestTipificacionSeAjustaAlCatalogo(t *testing.T) {
	qa := dato.Objeto{"estado_ot": "FALLIDA", "tipificacion_falla": dato.Objeto{"causa_raiz": "permisos de INGRESO", "responsable": "x"}}
	ValidarTipificacion(qa)
	if c, r := causa(qa); c != "Permisos de ingreso" || r != "Account executive" {
		t.Fatalf("got %q / %q", c, r)
	}
}

func TestTipificacionInventadaCaeAObservacionODefault(t *testing.T) {
	qa := dato.Objeto{"estado_ot": "FALLIDA", "observacion_tecnico_verbatim": "Cliente pide reprogramar",
		"tipificacion_falla": dato.Objeto{"causa_raiz": "algo inventado"}}
	ValidarTipificacion(qa)
	if c, _ := causa(qa); c != "Agendamiento cliente" {
		t.Fatalf("got %q", c)
	}
	qa = dato.Objeto{"estado_ot": "FALLIDA", "tipificacion_falla": dato.Objeto{"causa_raiz": "zzz"}}
	ValidarTipificacion(qa)
	if c, _ := causa(qa); c != CausaPorDefecto {
		t.Fatalf("got %q", c)
	}
}

// En Python \w incluye letras con tilde: "Información faltante" debe sumar 2
// palabras en comun con la causa del catalogo, no partirse en "informaci" y "n".
func TestMatchAproximadoConTildes(t *testing.T) {
	qa := dato.Objeto{"estado_ot": "FALLIDA", "tipificacion_falla": dato.Objeto{"causa_raiz": "información faltante del técnico"}}
	ValidarTipificacion(qa)
	if c, r := causa(qa); c != CausaPorDefecto || r != "Coordinador" {
		t.Fatalf("got %q / %q", c, r)
	}
	qa = dato.Objeto{"estado_ot": "FALLIDA", "tipificacion_falla": dato.Objeto{"causa_raiz": "Datos de ubicación", "responsable": "Cliente / Account executive"}}
	ValidarTipificacion(qa)
	if c, r := causa(qa); c != "Datos de ubicación erroneo" || r != "Cliente / Account executive" {
		t.Fatalf("got %q / %q", c, r)
	}
}

func TestCatalogoCompleto(t *testing.T) {
	if len(Tipificaciones) != 62 {
		t.Fatalf("el catalogo tiene %d causas, esperadas 62", len(Tipificaciones))
	}
}
