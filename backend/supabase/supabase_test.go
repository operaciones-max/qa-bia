package supabase

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
)

func clientePara(t *testing.T, h http.HandlerFunc) *Cliente {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return New(config.Config{SupabaseURL: srv.URL, SupabaseKey: "k"})
}

func TestGuardarInformaSiGuardo(t *testing.T) {
	status := http.StatusCreated
	c := clientePara(t, func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(status) })
	if !Guardar(c, dato.Objeto{"ot_id": "ot-1"}) {
		t.Fatal("201 deberia contar como guardado")
	}
	status = http.StatusInternalServerError
	if Guardar(c, dato.Objeto{"ot_id": "ot-1"}) {
		t.Fatal("500 no deberia contar como guardado")
	}
}

func TestSinSupabaseConfiguradoNoBloquea(t *testing.T) {
	if New(config.Config{}) != nil || !Guardar(nil, dato.Objeto{}) || !ActualizarAlcance(nil, "CO1", nil) {
		t.Fatal("sin Supabase debe devolver true sin hacer nada")
	}
}

func TestLeerTodasRecorreLasPaginas(t *testing.T) {
	total := TamPagina + 3
	var offsets []string
	c := clientePara(t, func(w http.ResponseWriter, r *http.Request) {
		off, _ := strconv.Atoi(r.URL.Query().Get("offset"))
		offsets = append(offsets, r.URL.Query().Get("offset"))
		n := min(TamPagina, total-off)
		filas := make([]map[string]string, n)
		for i := range filas {
			filas[i] = map[string]string{"ot_id": fmt.Sprintf("ot-%d", off+i)}
		}
		json.NewEncoder(w).Encode(filas)
	})
	filas, err := c.LeerTodas("ot_id")
	if err != nil || len(filas) != total {
		t.Fatalf("leidas %d filas, err %v", len(filas), err)
	}
	if fmt.Sprint(offsets) != fmt.Sprintf("[0 %d]", TamPagina) {
		t.Fatalf("offsets = %v", offsets)
	}
}

func TestRegistroUsaNullDondePythonUsabaNone(t *testing.T) {
	r := Registro(map[string]string{"id": "ot-1", "act_pdf_url": ""}, dato.Objeto{}, nil)
	if r["pdf_url"] != nil || r["ot_nombre"] != nil || r["estado_revision"] != "pendiente" || r["tiene_alcance"] != false {
		t.Fatalf("registro inesperado: %v", r)
	}
	if r["factor_medida"] != "" {
		t.Fatalf("factor_medida = %v", r["factor_medida"])
	}
}
