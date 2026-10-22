package web

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"testing"
	"time"
)

// supabaseFalso imita Auth y la API REST de actas_qa.
type supabaseFalso struct {
	mu       sync.Mutex
	filas    []map[string]any
	patches  []map[string]any
	tokens   []string // Authorization recibidos en la API REST
	vencido  bool     // la API responde 401 (JWT vencido)
	expiraEn int64
}

func (f *supabaseFalso) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	switch {
	case r.URL.Path == "/auth/v1/token":
		var cuerpo map[string]string
		json.NewDecoder(r.Body).Decode(&cuerpo)
		if r.URL.Query().Get("grant_type") == "password" && cuerpo["password"] != "secreto" {
			w.WriteHeader(400)
			w.Write([]byte(`{"error":"invalid_grant","error_description":"Invalid login credentials"}`))
			return
		}
		json.NewEncoder(w).Encode(map[string]any{
			"access_token": "jwt-" + r.URL.Query().Get("grant_type"), "refresh_token": "r1",
			"expires_at": time.Now().Unix() + f.expiraEn, "user": map[string]any{"email": "revisor@bia.app"},
		})
	case r.URL.Path == "/auth/v1/logout":
		w.WriteHeader(204)
	case r.URL.Path == "/rest/v1/actas_qa":
		f.tokens = append(f.tokens, r.Header.Get("Authorization"))
		if f.vencido {
			w.WriteHeader(401)
			w.Write([]byte(`{"message":"JWT expired"}`))
			return
		}
		q := r.URL.Query()
		filas := f.filas
		if id := strings.TrimPrefix(q.Get("ot_id"), "eq."); id != "" {
			filas = nil
			for _, fila := range f.filas {
				if fila["ot_id"] == id {
					filas = append(filas, fila)
				}
			}
		}
		if r.Method == http.MethodPatch {
			var cambios map[string]any
			json.NewDecoder(r.Body).Decode(&cambios)
			f.patches = append(f.patches, cambios)
			for _, fila := range filas {
				for k, v := range cambios {
					fila[k] = v
				}
			}
		}
		w.Header().Set("Content-Range", "0-0/"+itoa(len(filas)))
		if r.Method == http.MethodHead {
			return
		}
		json.NewEncoder(w).Encode(filas)
	default:
		w.WriteHeader(404)
	}
}

func itoa(n int) string { b, _ := json.Marshal(n); return string(b) }

func nuevoEntorno(t *testing.T) (*supabaseFalso, *httptest.Server, *http.Client) {
	t.Helper()
	sb := &supabaseFalso{expiraEn: 3600, filas: []map[string]any{{
		"ot_id": "ot-1", "ot_nombre": "VIPE_1", "estado_ot": "FALLIDA", "tipo_servicio": "Visita previa",
		"fecha_ejecucion": "2026-05-21 09:30:00", "errores_qa": []string{"Error <b>real</b>"}, "alertas_qa": []string{},
		"medidor_coincide_factura_anterior": false,
		"resultado_qa_completo": map[string]any{
			"observacion_tecnico_verbatim": "El cliente no permitio el acceso",
			"tipificacion_falla":           map[string]any{"causa_raiz": "Agendamiento cliente", "detalle": "d", "mejora": "m"},
		},
	}}}
	srvSB := httptest.NewServer(sb)
	t.Cleanup(srvSB.Close)
	app, err := NewServidor(Config{SupabaseURL: srvSB.URL + "/rest/v1/", AnonKey: "anon"})
	if err != nil {
		t.Fatal(err)
	}
	srv := httptest.NewServer(app)
	t.Cleanup(srv.Close)
	jar, _ := cookiejar.New(nil)
	cli := &http.Client{Jar: jar}
	return sb, srv, cli
}

func leer(t *testing.T, resp *http.Response) string {
	t.Helper()
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return string(b)
}

func TestSinSesionRedirigeAlLogin(t *testing.T) {
	_, srv, cli := nuevoEntorno(t)
	resp, _ := cli.Get(srv.URL + "/")
	if resp.Request.URL.Path != "/login" || !strings.Contains(leer(t, resp), "Contraseña") {
		t.Fatalf("termino en %s", resp.Request.URL)
	}
}

func TestLoginIncorrecto(t *testing.T) {
	_, srv, cli := nuevoEntorno(t)
	resp, _ := cli.PostForm(srv.URL+"/login", url.Values{"email": {"a@b.c"}, "clave": {"mal"}})
	if resp.StatusCode != 401 || !strings.Contains(leer(t, resp), "Correo o contraseña incorrectos.") {
		t.Fatalf("status %d", resp.StatusCode)
	}
}

func TestRecorridoCompleto(t *testing.T) {
	sb, srv, cli := nuevoEntorno(t)
	resp, _ := cli.PostForm(srv.URL+"/login", url.Values{"email": {"revisor@bia.app"}, "clave": {"secreto"}})
	lista := leer(t, resp)
	if resp.Request.URL.Path != "/" || !strings.Contains(lista, "VIPE_1") || !strings.Contains(lista, "revisor@bia.app") {
		t.Fatalf("listado inesperado en %s:\n%s", resp.Request.URL, lista)
	}
	if !strings.Contains(lista, `class="discrepancia"`) {
		t.Error("la fila con factura que no coincide deberia marcarse")
	}
	if sb.tokens[0] != "Bearer jwt-password" {
		t.Errorf("la API debe usar el token del usuario, uso %q", sb.tokens[0])
	}

	// Detalle conservando filtros; el HTML de la IA se escapa
	resp, _ = cli.Get(srv.URL + "/actas/ot-1?estadoOt=FALLIDA")
	detalle := leer(t, resp)
	for _, esperado := range []string{"El cliente no permitio el acceso", "Agendamiento cliente", `href="/?estadoOt=FALLIDA"`, "Error &lt;b&gt;real&lt;/b&gt;"} {
		if !strings.Contains(detalle, esperado) {
			t.Errorf("el detalle no contiene %q", esperado)
		}
	}

	// Guardar la revision
	resp, _ = cli.PostForm(srv.URL+"/actas/ot-1/revision", url.Values{
		"accion": {"EXITOSA"}, "comentario": {" ok "}, "q": {"estadoOt=FALLIDA"}})
	guardado := leer(t, resp)
	if resp.Request.URL.RawQuery != "estadoOt=FALLIDA&guardado=1" || !strings.Contains(guardado, "Revisión guardada.") {
		t.Fatalf("redirigio a %s", resp.Request.URL)
	}
	p := sb.patches[0]
	if p["revision_resultado"] != "EXITOSA" || p["revision_comentario"] != "ok" || p["revisado_por"] != "revisor@bia.app" {
		t.Fatalf("PATCH = %v", p)
	}

	// Quitar la revision
	cli.PostForm(srv.URL+"/actas/ot-1/revision", url.Values{"accion": {"quitar"}})
	if p := sb.patches[1]; p["revision_resultado"] != nil || p["revisado_por"] != nil {
		t.Fatalf("PATCH al quitar = %v", p)
	}

	// Acta inexistente
	resp, _ = cli.Get(srv.URL + "/actas/no-existe")
	if resp.StatusCode != 404 {
		t.Errorf("status %d para un acta inexistente", resp.StatusCode)
	}
	leer(t, resp)
}

func TestFormularioDesdeOtroSitioSeRechaza(t *testing.T) {
	_, srv, cli := nuevoEntorno(t)
	cli.PostForm(srv.URL+"/login", url.Values{"email": {"revisor@bia.app"}, "clave": {"secreto"}})
	req, _ := http.NewRequest(http.MethodPost, srv.URL+"/actas/ot-1/revision", strings.NewReader("accion=FALLIDA"))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Origin", "https://otro-sitio.com")
	resp, _ := cli.Do(req)
	if resp.StatusCode != 403 {
		t.Fatalf("status %d", resp.StatusCode)
	}
}

func TestTokenPorVencerSeRefrescaYJWTVencidoVuelveAlLogin(t *testing.T) {
	sb, srv, cli := nuevoEntorno(t)
	sb.expiraEn = 30 // vence en menos de 60 s: se refresca en la siguiente request
	cli.PostForm(srv.URL+"/login", url.Values{"email": {"revisor@bia.app"}, "clave": {"secreto"}})
	sb.mu.Lock()
	sb.tokens = nil
	sb.mu.Unlock()
	leer(t, must(cli.Get(srv.URL+"/")))
	if sb.tokens[0] != "Bearer jwt-refresh_token" {
		t.Fatalf("no se refresco el token: %v", sb.tokens[:1])
	}

	sb.vencido = true
	resp := must(cli.Get(srv.URL + "/"))
	leer(t, resp)
	if resp.Request.URL.Path != "/login" {
		t.Fatalf("con el JWT vencido deberia volver al login, quedo en %s", resp.Request.URL)
	}
}

func must(resp *http.Response, err error) *http.Response {
	if err != nil {
		panic(err)
	}
	return resp
}
