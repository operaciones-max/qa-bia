package web

import (
	"bytes"
	"context"
	"embed"
	"encoding/base64"
	"encoding/json"
	"errors"
	"html/template"
	"io/fs"
	"log"
	"math"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

//go:embed plantillas/*.html
var plantillasFS embed.FS

//go:embed estaticos
var estaticosFS embed.FS

const nombreCookie = "qa_sesion"

// Config del dashboard.
type Config struct {
	SupabaseURL  string
	AnonKey      string
	CookieSegura bool // true en produccion (HTTPS)
}

// Servidor es el dashboard.
type Servidor struct {
	sb           *Supabase
	paginas      map[string]*template.Template
	cookieSegura bool
	mux          *http.ServeMux
}

// NewServidor arma las rutas y carga las plantillas.
func NewServidor(cfg Config) (*Servidor, error) {
	s := &Servidor{sb: NewSupabase(cfg.SupabaseURL, cfg.AnonKey), cookieSegura: cfg.CookieSegura, paginas: map[string]*template.Template{}}
	for _, p := range []string{"login", "lista", "detalle", "error"} {
		t, err := template.New("base.html").Funcs(funciones).ParseFS(plantillasFS, "plantillas/base.html", "plantillas/"+p+".html")
		if err != nil {
			return nil, err
		}
		s.paginas[p] = t
	}
	estaticos, _ := fs.Sub(estaticosFS, "estaticos")

	s.mux = http.NewServeMux()
	s.mux.Handle("GET /estaticos/", http.StripPrefix("/estaticos/", http.FileServerFS(estaticos)))
	s.mux.HandleFunc("GET /salud", func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("ok")) })
	s.mux.HandleFunc("GET /login", s.verLogin)
	s.mux.HandleFunc("POST /login", s.entrar)
	s.mux.HandleFunc("POST /logout", s.salir)
	s.mux.HandleFunc("GET /{$}", s.conSesion(s.verLista))
	s.mux.HandleFunc("GET /actas/{id}", s.conSesion(s.verDetalle))
	s.mux.HandleFunc("POST /actas/{id}/revision", s.conSesion(s.guardarRevision))
	return s, nil
}

func (s *Servidor) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("X-Frame-Options", "DENY")
	w.Header().Set("Referrer-Policy", "same-origin")
	// Los formularios solo se aceptan desde el mismo sitio (ademas de SameSite=Lax en la cookie).
	if r.Method == http.MethodPost && !mismoOrigen(r) {
		http.Error(w, "origen no permitido", http.StatusForbidden)
		return
	}
	s.mux.ServeHTTP(w, r)
}

func mismoOrigen(r *http.Request) bool {
	origen := r.Header.Get("Origin")
	if origen == "" {
		return true
	}
	u, err := url.Parse(origen)
	return err == nil && u.Host == r.Host
}

// ---------------------------------------------------------------- sesion

func (s *Servidor) guardarCookie(w http.ResponseWriter, ses Sesion) {
	data, _ := json.Marshal(ses)
	http.SetCookie(w, &http.Cookie{
		Name: nombreCookie, Value: base64.RawURLEncoding.EncodeToString(data), Path: "/",
		MaxAge: 30 * 24 * 3600, HttpOnly: true, Secure: s.cookieSegura, SameSite: http.SameSiteLaxMode,
	})
}

func (s *Servidor) borrarCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{Name: nombreCookie, Value: "", Path: "/", MaxAge: -1, HttpOnly: true,
		Secure: s.cookieSegura, SameSite: http.SameSiteLaxMode})
}

func leerCookie(r *http.Request) (Sesion, bool) {
	c, err := r.Cookie(nombreCookie)
	if err != nil {
		return Sesion{}, false
	}
	data, err := base64.RawURLEncoding.DecodeString(c.Value)
	if err != nil {
		return Sesion{}, false
	}
	var ses Sesion
	if json.Unmarshal(data, &ses) != nil || ses.Access == "" {
		return Sesion{}, false
	}
	return ses, true
}

type handlerConSesion func(w http.ResponseWriter, r *http.Request, ses Sesion)

// conSesion exige login y refresca el token si esta por vencer.
func (s *Servidor) conSesion(h handlerConSesion) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ses, ok := leerCookie(r)
		if !ok {
			http.Redirect(w, r, "/login", http.StatusSeeOther)
			return
		}
		if time.Now().Unix() > ses.Expira-60 {
			nueva, err := s.sb.Refrescar(r.Context(), ses.Refresh)
			if err != nil {
				s.cerrarSesion(w, r)
				return
			}
			ses = nueva
			s.guardarCookie(w, ses)
		}
		h(w, r, ses)
	}
}

func (s *Servidor) cerrarSesion(w http.ResponseWriter, r *http.Request) {
	s.borrarCookie(w)
	http.Redirect(w, r, "/login", http.StatusSeeOther)
}

// ---------------------------------------------------------------- render

func (s *Servidor) render(w http.ResponseWriter, pagina string, status int, datos map[string]any) {
	var buf bytes.Buffer
	if err := s.paginas[pagina].ExecuteTemplate(&buf, "base.html", datos); err != nil {
		log.Printf("error renderizando %s: %v", pagina, err)
		http.Error(w, "error interno", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(status)
	buf.WriteTo(w)
}

// fallo muestra el error, o manda al login si la sesion vencio.
func (s *Servidor) fallo(w http.ResponseWriter, r *http.Request, ses Sesion, err error) {
	if errors.Is(err, ErrNoAutorizado) {
		s.cerrarSesion(w, r)
		return
	}
	log.Printf("%s %s: %v", r.Method, r.URL.Path, err)
	s.render(w, "error", http.StatusBadGateway, map[string]any{"Email": ses.Email, "Error": err.Error()})
}

// ---------------------------------------------------------------- handlers

func (s *Servidor) verLogin(w http.ResponseWriter, r *http.Request) {
	if _, ok := leerCookie(r); ok {
		http.Redirect(w, r, "/", http.StatusSeeOther)
		return
	}
	s.render(w, "login", http.StatusOK, map[string]any{})
}

func (s *Servidor) entrar(w http.ResponseWriter, r *http.Request) {
	email := strings.TrimSpace(r.PostFormValue("email"))
	ses, err := s.sb.Login(r.Context(), email, r.PostFormValue("clave"))
	if err != nil {
		status := http.StatusBadGateway
		if errors.Is(err, ErrCredenciales) {
			status = http.StatusUnauthorized
		} else {
			log.Printf("login: %v", err)
		}
		s.render(w, "login", status, map[string]any{"Error": err.Error(), "EmailIngresado": email})
		return
	}
	s.guardarCookie(w, ses)
	http.Redirect(w, r, "/", http.StatusSeeOther)
}

func (s *Servidor) salir(w http.ResponseWriter, r *http.Request) {
	if ses, ok := leerCookie(r); ok {
		s.sb.Logout(r.Context(), ses.Access)
	}
	s.cerrarSesion(w, r)
}

func (s *Servidor) verLista(w http.ResponseWriter, r *http.Request, ses Sesion) {
	f, pagina := FiltrosDesdeURL(r.URL.Query())
	// El formulario manda todos los campos, incluso vacios: se limpia la URL.
	if limpia := f.URL(pagina).Encode(); r.URL.RawQuery != limpia {
		destino := "/"
		if limpia != "" {
			destino += "?" + limpia
		}
		http.Redirect(w, r, destino, http.StatusSeeOther)
		return
	}
	ctx, cancelar := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancelar()

	var (
		wg          sync.WaitGroup
		filas       []ActaQA
		total       int
		indicadores Indicadores
		opciones    Opciones
		errLista    error
		errInd      error
	)
	wg.Add(3)
	go func() { defer wg.Done(); filas, total, errLista = s.sb.Listar(ctx, ses.Access, f, pagina) }()
	go func() { defer wg.Done(); indicadores, errInd = s.sb.CalcularIndicadores(ctx, ses.Access, f) }()
	go func() { defer wg.Done(); opciones, _ = s.sb.CargarOpciones(ctx, ses.Access) }()
	wg.Wait()
	if err := errors.Join(errLista, errInd); err != nil {
		s.fallo(w, r, ses, err)
		return
	}

	paginas := int(math.Max(1, math.Ceil(float64(total)/TamPagina)))
	query := f.URL(pagina).Encode()
	datos := map[string]any{
		"Email":       ses.Email,
		"Filtros":     f,
		"Opciones":    opciones,
		"Indicadores": indicadores,
		"Filas":       filas,
		"Total":       total,
		"Pagina":      pagina + 1,
		"Paginas":     paginas,
		"Paginar":     total > TamPagina,
		"Query":       query,
	}
	if pagina > 0 {
		datos["Anterior"] = template.URL("/?" + f.URL(pagina-1).Encode())
	}
	if pagina+1 < paginas {
		datos["Siguiente"] = template.URL("/?" + f.URL(pagina+1).Encode())
	}
	s.render(w, "lista", http.StatusOK, datos)
}

// volverAlListado conserva los filtros del listado (vienen en la query del detalle).
func volverAlListado(q url.Values) string {
	f, pagina := FiltrosDesdeURL(q)
	return f.URL(pagina).Encode()
}

func (s *Servidor) verDetalle(w http.ResponseWriter, r *http.Request, ses Sesion) {
	s.renderDetalle(w, r, ses, http.StatusOK, "")
}

func (s *Servidor) renderDetalle(w http.ResponseWriter, r *http.Request, ses Sesion, status int, errRevision string) {
	acta, err := s.sb.Obtener(r.Context(), ses.Access, r.PathValue("id"))
	if err != nil {
		s.fallo(w, r, ses, err)
		return
	}
	query := volverAlListado(r.URL.Query())
	if acta == nil {
		s.render(w, "error", http.StatusNotFound, map[string]any{
			"Email": ses.Email, "Error": "No existe un acta con ese id.", "Volver": template.URL("/?" + query)})
		return
	}
	s.render(w, "detalle", status, map[string]any{
		"Email":         ses.Email,
		"Acta":          acta,
		"QA":            acta.ResultadoQACompleto,
		"Volver":        template.URL("/?" + query),
		"Query":         query,
		"Guardado":      r.URL.Query().Get("guardado") == "1",
		"ErrorRevision": errRevision,
	})
}

func (s *Servidor) guardarRevision(w http.ResponseWriter, r *http.Request, ses Sesion) {
	id := r.PathValue("id")
	resultado := ""
	switch r.PostFormValue("accion") {
	case "EXITOSA":
		resultado = "EXITOSA"
	case "FALLIDA":
		resultado = "FALLIDA"
	case "quitar":
	default:
		http.Error(w, "accion no valida", http.StatusBadRequest)
		return
	}
	q, _ := url.ParseQuery(r.PostFormValue("q"))
	err := s.sb.GuardarRevision(r.Context(), ses.Access, id, resultado, r.PostFormValue("comentario"), ses.Email)
	if errors.Is(err, ErrNoAutorizado) {
		s.cerrarSesion(w, r)
		return
	}
	if err != nil {
		r.URL.RawQuery = volverAlListado(q)
		s.renderDetalle(w, r, ses, http.StatusBadGateway, err.Error())
		return
	}
	destino := "/actas/" + url.PathEscape(id) + "?" + volverAlListado(q)
	if !strings.HasSuffix(destino, "?") {
		destino += "&"
	}
	http.Redirect(w, r, destino+"guardado=1", http.StatusSeeOther)
}
