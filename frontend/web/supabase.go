package web

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

// TamPagina es la cantidad de actas por pagina del listado.
const TamPagina = 50

var (
	// ErrNoAutorizado: el token vencio o no es valido; hay que volver a loguearse.
	ErrNoAutorizado = errors.New("la sesion vencio")
	// ErrCredenciales: correo o contraseña incorrectos.
	ErrCredenciales = errors.New("Correo o contraseña incorrectos.")
)

// Supabase habla con Auth y con la API REST usando la anon key y el token del usuario.
type Supabase struct {
	url     string
	anonKey string
	http    *http.Client
}

func NewSupabase(urlBase, anonKey string) *Supabase {
	urlBase = strings.TrimSuffix(strings.TrimRight(strings.TrimSpace(urlBase), "/"), "/rest/v1")
	return &Supabase{url: urlBase, anonKey: anonKey, http: &http.Client{Timeout: 20 * time.Second}}
}

// ---------------------------------------------------------------- Auth

// Sesion es lo que se guarda en la cookie del usuario.
type Sesion struct {
	Access  string `json:"a"`
	Refresh string `json:"r"`
	Expira  int64  `json:"e"` // unix
	Email   string `json:"m"`
}

type respuestaToken struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int64  `json:"expires_in"`
	ExpiresAt    int64  `json:"expires_at"`
	User         struct {
		Email string `json:"email"`
	} `json:"user"`
	Mensaje string `json:"msg"`
	Error   string `json:"error_description"`
}

func (s *Supabase) token(ctx context.Context, grant string, cuerpo any) (Sesion, error) {
	data, _ := json.Marshal(cuerpo)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, s.url+"/auth/v1/token?grant_type="+grant, bytes.NewReader(data))
	req.Header.Set("apikey", s.anonKey)
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.http.Do(req)
	if err != nil {
		return Sesion{}, err
	}
	defer resp.Body.Close()
	var r respuestaToken
	json.NewDecoder(resp.Body).Decode(&r)
	if resp.StatusCode == http.StatusBadRequest || resp.StatusCode == http.StatusUnauthorized {
		if grant == "password" {
			return Sesion{}, ErrCredenciales
		}
		return Sesion{}, ErrNoAutorizado
	}
	if resp.StatusCode != http.StatusOK || r.AccessToken == "" {
		return Sesion{}, fmt.Errorf("Supabase Auth respondio %d %s%s", resp.StatusCode, r.Mensaje, r.Error)
	}
	expira := r.ExpiresAt
	if expira == 0 {
		expira = time.Now().Unix() + r.ExpiresIn
	}
	return Sesion{Access: r.AccessToken, Refresh: r.RefreshToken, Expira: expira, Email: r.User.Email}, nil
}

// Login valida correo y contraseña contra Supabase Auth.
func (s *Supabase) Login(ctx context.Context, email, clave string) (Sesion, error) {
	return s.token(ctx, "password", map[string]string{"email": email, "password": clave})
}

// Refrescar pide un token nuevo con el refresh token.
func (s *Supabase) Refrescar(ctx context.Context, refresh string) (Sesion, error) {
	return s.token(ctx, "refresh_token", map[string]string{"refresh_token": refresh})
}

// Logout invalida la sesion en Supabase (si falla no importa: la cookie se borra igual).
func (s *Supabase) Logout(ctx context.Context, access string) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, s.url+"/auth/v1/logout", nil)
	req.Header.Set("apikey", s.anonKey)
	req.Header.Set("Authorization", "Bearer "+access)
	if resp, err := s.http.Do(req); err == nil {
		resp.Body.Close()
	}
}

// ---------------------------------------------------------------- REST

func (s *Supabase) rest(ctx context.Context, metodo, token string, params url.Values, cuerpo any, prefer string) (*http.Response, []byte, error) {
	var body io.Reader
	if cuerpo != nil {
		data, err := json.Marshal(cuerpo)
		if err != nil {
			return nil, nil, err
		}
		body = bytes.NewReader(data)
	}
	u := s.url + "/rest/v1/actas_qa"
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	req, err := http.NewRequestWithContext(ctx, metodo, u, body)
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("apikey", s.anonKey)
	req.Header.Set("Authorization", "Bearer "+token)
	if cuerpo != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if prefer != "" {
		req.Header.Set("Prefer", prefer)
	}
	resp, err := s.http.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, err
	}
	if resp.StatusCode == http.StatusUnauthorized {
		return nil, nil, ErrNoAutorizado
	}
	if resp.StatusCode >= 400 {
		var e struct {
			Message string `json:"message"`
		}
		json.Unmarshal(data, &e)
		if e.Message == "" {
			e.Message = strings.TrimSpace(string(data))
		}
		return nil, nil, fmt.Errorf("Supabase respondio %d: %s", resp.StatusCode, e.Message)
	}
	return resp, data, nil
}

// totalDeRango lee el total de un header Content-Range ("0-49/123" o "*/0").
func totalDeRango(rango string) int {
	_, total, ok := strings.Cut(rango, "/")
	if !ok {
		return 0
	}
	n, _ := strconv.Atoi(total)
	return n
}

// Listar devuelve una pagina de actas y el total con esos filtros.
func (s *Supabase) Listar(ctx context.Context, token string, f Filtros, pagina int) ([]ActaQA, int, error) {
	params := f.Condiciones()
	params.Set("select", ColumnasResumen)
	params.Set("order", "fecha_ejecucion.desc.nullslast,ot_id.asc")
	params.Set("limit", strconv.Itoa(TamPagina))
	params.Set("offset", strconv.Itoa(pagina*TamPagina))
	resp, data, err := s.rest(ctx, http.MethodGet, token, params, nil, "count=exact")
	if err != nil {
		return nil, 0, err
	}
	var filas []ActaQA
	if err := json.Unmarshal(data, &filas); err != nil {
		return nil, 0, err
	}
	return filas, totalDeRango(resp.Header.Get("Content-Range")), nil
}

// Contar devuelve cuantas actas cumplen las condiciones.
func (s *Supabase) Contar(ctx context.Context, token string, condiciones url.Values) (int, error) {
	params := url.Values{}
	for k, v := range condiciones {
		params[k] = append([]string(nil), v...)
	}
	params.Set("select", "ot_id")
	resp, _, err := s.rest(ctx, http.MethodHead, token, params, nil, "count=exact")
	if err != nil {
		return 0, err
	}
	return totalDeRango(resp.Header.Get("Content-Range")), nil
}

// Indicadores son los totales que se muestran arriba del listado.
type Indicadores struct {
	Total, Exitosas, Fallidas, ConDiscrepancias, SinRevisar int
}

// CalcularIndicadores cuenta en paralelo, sobre los mismos filtros del listado.
func (s *Supabase) CalcularIndicadores(ctx context.Context, token string, f Filtros) (Indicadores, error) {
	con := func(k, v string) url.Values {
		q := f.Condiciones()
		if k != "" {
			q.Add(k, v)
		}
		return q
	}
	consultas := []url.Values{
		con("", ""),
		con("estado_ot", "eq.EXITOSA"),
		con("estado_ot", "eq.FALLIDA"),
		con("or", ExpresionDiscrepancias),
		con("revision_resultado", "is.null"),
	}
	resultados := make([]int, len(consultas))
	errs := make([]error, len(consultas))
	var wg sync.WaitGroup
	for i, q := range consultas {
		wg.Add(1)
		go func() {
			defer wg.Done()
			resultados[i], errs[i] = s.Contar(ctx, token, q)
		}()
	}
	wg.Wait()
	if err := errors.Join(errs...); err != nil {
		if errors.Is(err, ErrNoAutorizado) {
			return Indicadores{}, ErrNoAutorizado
		}
		return Indicadores{}, err
	}
	return Indicadores{resultados[0], resultados[1], resultados[2], resultados[3], resultados[4]}, nil
}

// Opciones son los valores de los desplegables de filtro.
type Opciones struct {
	TiposServicio []string
	Planners      []string
}

// CargarOpciones trae los tipos de servicio y planners distintos.
func (s *Supabase) CargarOpciones(ctx context.Context, token string) (Opciones, error) {
	params := url.Values{"select": {"tipo_servicio,planner"}, "limit": {"5000"}}
	_, data, err := s.rest(ctx, http.MethodGet, token, params, nil, "")
	if err != nil {
		return Opciones{}, err
	}
	var filas []struct {
		TipoServicio *string `json:"tipo_servicio"`
		Planner      *string `json:"planner"`
	}
	if err := json.Unmarshal(data, &filas); err != nil {
		return Opciones{}, err
	}
	tipos, planners := map[string]bool{}, map[string]bool{}
	for _, f := range filas {
		if f.TipoServicio != nil && *f.TipoServicio != "" {
			tipos[*f.TipoServicio] = true
		}
		if f.Planner != nil && *f.Planner != "" {
			planners[*f.Planner] = true
		}
	}
	return Opciones{TiposServicio: ordenados(tipos), Planners: ordenados(planners)}, nil
}

func ordenados(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Slice(out, func(i, j int) bool { return strings.ToLower(out[i]) < strings.ToLower(out[j]) })
	return out
}

// Obtener devuelve un acta completa, o nil si no existe (o el usuario no la puede ver).
func (s *Supabase) Obtener(ctx context.Context, token, otID string) (*ActaQA, error) {
	params := url.Values{"select": {"*"}, "ot_id": {"eq." + otID}}
	_, data, err := s.rest(ctx, http.MethodGet, token, params, nil, "")
	if err != nil {
		return nil, err
	}
	var filas []ActaQA
	if err := json.Unmarshal(data, &filas); err != nil {
		return nil, err
	}
	if len(filas) == 0 {
		return nil, nil
	}
	return &filas[0], nil
}

// GuardarRevision guarda el veredicto del revisor ("EXITOSA", "FALLIDA" o "" para
// quitarlo). Quien revisa y cuando lo firma un trigger en la base de datos.
func (s *Supabase) GuardarRevision(ctx context.Context, token, otID, resultado, comentario, email string) error {
	var cambios map[string]any
	if resultado == "" {
		cambios = map[string]any{"revision_resultado": nil, "revision_comentario": nil, "revisado_por": nil, "revisado_en": nil}
	} else {
		var com any
		if c := strings.TrimSpace(comentario); c != "" {
			com = c
		}
		cambios = map[string]any{
			"revision_resultado":  resultado,
			"revision_comentario": com,
			"revisado_por":        email,
			"revisado_en":         time.Now().UTC().Format(time.RFC3339),
		}
	}
	params := url.Values{"ot_id": {"eq." + otID}, "select": {"ot_id"}}
	_, data, err := s.rest(ctx, http.MethodPatch, token, params, cambios, "return=representation")
	if err != nil {
		return err
	}
	var filas []map[string]any
	json.Unmarshal(data, &filas)
	if len(filas) == 0 {
		return errors.New("no se pudo guardar: el acta no existe o no tienes permiso para revisarla")
	}
	return nil
}
