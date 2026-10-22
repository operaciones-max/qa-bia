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

func TestCadaTipoDeOTTieneSuSubagente(t *testing.T) {
	for _, tipo := range catalogo.TiposOT {
		p, err := SystemPromptAgente(tipo.Codigo)
		if err != nil {
			t.Fatalf("%s: %v", tipo.Codigo, err)
		}
		if strings.Contains(p, "{{") {
			t.Errorf("%s: quedo un marcador sin reemplazar", tipo.Codigo)
		}
		if !strings.Contains(p, "subagente de cierre de las OTs "+tipo.Codigo+" ("+tipo.Nombre) {
			t.Errorf("%s: el prompt no dice de que OT es", tipo.Codigo)
		}
		// PENDIENTE solo donde el tipo lo admite.
		if admite := strings.Contains(p, "Esta OT admite PENDIENTE"); admite != tipo.PermitePendiente {
			t.Errorf("%s: admite PENDIENTE = %v, esperado %v", tipo.Codigo, admite, tipo.PermitePendiente)
		}
	}
	if _, err := SystemPromptAgente("XXXX"); err == nil {
		t.Error("un codigo desconocido deberia dar error")
	}
}

func TestNoHayReglasDeOTsSinTipo(t *testing.T) {
	for _, dir := range []string{"ots", "familias"} {
		archivos, err := promptsAgentes.ReadDir("prompts/agentes/" + dir)
		if err != nil {
			t.Fatal(err)
		}
		for _, a := range archivos {
			nombre := strings.TrimSuffix(a.Name(), ".md")
			usado := false
			for _, tipo := range catalogo.TiposOT {
				usado = usado || nombre == tipo.Codigo || nombre == string(tipo.Familia)
			}
			if !usado {
				t.Errorf("%s/%s no corresponde a ningun tipo de OT", dir, a.Name())
			}
		}
	}
}

func TestSubagenteIncluyeReglasYCatalogo(t *testing.T) {
	vipe, _ := SystemPromptAgente("VIPE")
	desx, _ := SystemPromptAgente("desx")
	for _, parte := range []string{"Tu OT es una VISITA PREVIA", "Transformadores encontrados (`transformador`)", "\nContratista:\n  - Fallas en el Alistamiento Operativo\n"} {
		if !strings.Contains(vipe, parte) {
			t.Errorf("VIPE sin %q", parte)
		}
	}
	if !strings.Contains(desx, "El pago en sitio es éxito") || strings.Contains(desx, "Transformadores encontrados") {
		t.Error("DESX debe traer sus reglas y no las de VIPE")
	}
	for _, tip := range catalogo.Tipificaciones {
		if !strings.Contains(vipe, "\n  - "+tip.Causa+"\n") {
			t.Errorf("falta la causa %q", tip.Causa)
		}
	}
}
