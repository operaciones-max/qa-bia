package ia

import (
	"errors"
	"fmt"
	"strings"
	"testing"

	"github.com/anthropics/anthropic-sdk-go"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
)

func TestEtiquetaTipoNoConvierteTodoEnVisitaPrevia(t *testing.T) {
	casos := map[string]string{
		"Visita previa":        "VISITA PREVIA",
		"Instalación":          "INSTALACION",
		"Normalización medida": "NORMALIZACIÓN MEDIDA",
		"Alta ingenieria":      "ALTA INGENIERIA",
	}
	for tipo, esperado := range casos {
		if got := EtiquetaTipo(tipo); got != esperado {
			t.Errorf("EtiquetaTipo(%q) = %q, esperado %q", tipo, got, esperado)
		}
	}
}

func TestExtraerJSONToleraBloquesYTextoAlrededor(t *testing.T) {
	obj, err := ExtraerJSON("```json\n{\"a\": 1}\n```")
	if err != nil || obj["a"].(fmt.Stringer).String() != "1" {
		t.Fatalf("got %v, %v", obj, err)
	}
	obj, err = ExtraerJSON(`Aqui va: {"a": {"b": 2}} fin`)
	if err != nil || obj["a"] == nil {
		t.Fatalf("got %v, %v", obj, err)
	}
	if _, err := ExtraerJSON("no hay json"); err == nil {
		t.Fatal("deberia fallar")
	}
}

func TestLimiteDeUsoSoloPor429Y529(t *testing.T) {
	for codigo, esperado := range map[int]bool{429: true, 529: true, 500: false, 400: false} {
		err := fmt.Errorf("envuelto: %w", &anthropic.Error{StatusCode: codigo})
		if EsLimiteDeUso(err) != esperado {
			t.Errorf("status %d: esperado %v", codigo, esperado)
		}
	}
	if EsLimiteDeUso(errors.New("could not generate rate")) {
		t.Error("un error sin status no es limite de uso")
	}
}

func TestPromptsIncluyenElCatalogo(t *testing.T) {
	for nombre, p := range map[string]string{"lite": SystemPromptLite(), "full": SystemPromptFull()} {
		if strings.Contains(p, "{{CATALOGO}}") || !strings.Contains(p, "  - Error en alcance\n") {
			t.Errorf("prompt %s sin catalogo", nombre)
		}
	}
}

func TestEvaluadorCierreIncluyeElCatalogoPorResponsable(t *testing.T) {
	p := SystemPromptEvaluadorCierre()
	if strings.Contains(p, "{{") {
		t.Fatal("quedo un placeholder sin reemplazar")
	}
	for _, tip := range catalogo.Tipificaciones {
		if !strings.Contains(p, "\n  - "+tip.Causa+"\n") {
			t.Errorf("falta la causa %q", tip.Causa)
		}
	}
	// Cada causa queda bajo el titulo de su responsable.
	if !strings.Contains(p, "\nContratista:\n  - Fallas en el Alistamiento Operativo\n") {
		t.Error("las causas no quedaron agrupadas por responsable")
	}
}
