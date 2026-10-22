package ia

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/config"
)

// claudeFalso responde como la API de Messages y guarda lo que recibio.
func claudeFalso(t *testing.T, stopReason, texto string) (*httptest.Server, *map[string]any, *http.Header) {
	var cuerpo map[string]any
	var cabeceras http.Header
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		data, _ := io.ReadAll(r.Body)
		json.Unmarshal(data, &cuerpo)
		cabeceras = r.Header.Clone()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"id": "msg_1", "type": "message", "role": "assistant", "model": cuerpo["model"],
			"content":     []map[string]any{{"type": "text", "text": texto}},
			"stop_reason": stopReason, "stop_sequence": nil,
			"usage": map[string]any{"input_tokens": 900, "output_tokens": 120},
		})
	}))
	t.Cleanup(srv.Close)
	return srv, &cuerpo, &cabeceras
}

func clienteDePrueba(url, modelo string) *Cliente {
	return NewCliente(config.Config{AnthropicAPIKey: "k", AnthropicBaseURL: url, ClaudeModel: modelo}, nil)
}

func TestExtraerInformacionArmaElRequestYDevuelveElJSON(t *testing.T) {
	srv, cuerpo, cabeceras := claudeFalso(t, "end_turn", "```json\n{\"b\": 1, \"a\": \"x\"}\n```")
	doc := Documento{
		Tipo: "pdf", Paginas: 2,
		Texto:    []PaginaTexto{{Numero: 1, Texto: "NIT 901835098"}},
		Imagenes: []PaginaImagen{{Numero: 2, Imagen: Imagen{Tipo: "image/jpeg", Datos: []byte{0xff, 0xd8}}}},
	}
	r, err := clienteDePrueba(srv.URL, "claude-opus-5-5").ExtraerInformacion(context.Background(), "Extrae {\"a\": \"\"}", doc, "low")
	if err != nil {
		t.Fatal(err)
	}
	if string(r.JSON) != `{"b": 1, "a": "x"}` || r.Modelo != "claude-opus-5-5" || r.TokensSalida != 120 {
		t.Errorf("respuesta = %+v (%s)", r, r.JSON)
	}

	c := *cuerpo
	if _, hay := c["temperature"]; hay {
		t.Error("no debe mandar temperature")
	}
	if c["fallbacks"] != "default" || !strings.Contains((*cabeceras).Get("anthropic-beta"), "server-side-fallback-2026-07-01") {
		t.Errorf("falta el respaldo ante rechazos: fallbacks=%v beta=%q", c["fallbacks"], (*cabeceras).Get("anthropic-beta"))
	}
	if c["output_config"].(map[string]any)["effort"] != "low" {
		t.Errorf("output_config = %v", c["output_config"])
	}
	bloques := c["messages"].([]any)[0].(map[string]any)["content"].([]any)
	if len(bloques) != 3 || bloques[1].(map[string]any)["type"] != "image" {
		t.Fatalf("bloques = %v", bloques)
	}
	texto := bloques[2].(map[string]any)["text"].(string)
	for _, parte := range []string{"INSTRUCCIÓN:\nExtrae", "PDF de 2 página(s)", "página(s) 2", "--- PÁGINA 1 ---\nNIT 901835098"} {
		if !strings.Contains(texto, parte) {
			t.Errorf("mensaje sin %q:\n%s", parte, texto)
		}
	}
}

func TestExtraerInformacionSinRespaldoNiEsfuerzoEnHaiku45(t *testing.T) {
	srv, cuerpo, cabeceras := claudeFalso(t, "end_turn", `{"a": 1}`)
	_, err := clienteDePrueba(srv.URL, "claude-haiku-4-5-20251001").ExtraerInformacion(context.Background(), "x", Documento{Tipo: "imagen"}, "")
	if err != nil {
		t.Fatal(err)
	}
	if _, hay := (*cuerpo)["fallbacks"]; hay || (*cabeceras).Get("anthropic-beta") != "" {
		t.Error("Haiku 4.5 no admite el respaldo")
	}
	if _, hay := (*cuerpo)["output_config"]; hay {
		t.Error("sin esfuerzo configurado no se manda output_config")
	}
}

func TestExtraerInformacionErrores(t *testing.T) {
	casos := []struct {
		stop, texto string
		esperado    error
	}{
		{"refusal", "", ErrRechazo},
		{"max_tokens", `{"a": `, ErrRespuestaCortada},
		{"end_turn", "no encontre nada", ErrSinJSON},
		{"end_turn", `["no es objeto"]`, ErrSinJSON},
	}
	for _, c := range casos {
		srv, _, _ := claudeFalso(t, c.stop, c.texto)
		_, err := clienteDePrueba(srv.URL, "claude-opus-5-5").ExtraerInformacion(context.Background(), "x", Documento{Tipo: "imagen"}, "")
		if !errors.Is(err, c.esperado) {
			t.Errorf("%s %q: err = %v, esperado %v", c.stop, c.texto, err, c.esperado)
		}
	}
}

func TestEvaluarCierreUsaElPromptDelSubagente(t *testing.T) {
	srv, cuerpo, _ := claudeFalso(t, "end_turn", `{"veredicto": "PENDIENTE", "pendientes": ["Legalización"]}`)
	r, err := clienteDePrueba(srv.URL, "claude-haiku-4-5-20251001").EvaluarCierre(context.Background(), "INST", "TIPO DE OT: INST")
	if err != nil || r["veredicto"] != "PENDIENTE" {
		t.Fatalf("r = %v, err = %v", r, err)
	}
	sistema := (*cuerpo)["system"].([]any)[0].(map[string]any)["text"].(string)
	if !strings.Contains(sistema, "subagente de cierre de las OTs INST (Instalación") || !strings.Contains(sistema, "Esta OT admite PENDIENTE") {
		t.Error("el system prompt no es el del subagente INST")
	}
	if _, err := clienteDePrueba(srv.URL, "x").EvaluarCierre(context.Background(), "NOEXISTE", "x"); err == nil {
		t.Error("un tipo de OT desconocido deberia dar error")
	}
}
