package extraccion

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// RutaExtraccion es la ruta del servicio original; se mantiene para no romper
// a quien ya lo llama.
const RutaExtraccion = "/ms-ia-extraction/extraction_information"

const (
	maxBytesCuerpo = 1 << 20
	// TiempoMaximo por peticion (descarga + Claude).
	TiempoMaximo = 5 * time.Minute
)

type handler struct {
	servicio *Servicio
	apiKey   string
}

// NuevoHandler arma las rutas del servicio. Si apiKey no esta vacia, cada
// peticion debe traer "Authorization: Bearer <apiKey>" o "X-API-Key: <apiKey>".
func NuevoHandler(s *Servicio, apiKey string) http.Handler {
	h := &handler{servicio: s, apiKey: apiKey}
	mux := http.NewServeMux()
	mux.HandleFunc("POST "+RutaExtraccion, h.extraer)
	mux.HandleFunc("GET /salud", func(w http.ResponseWriter, _ *http.Request) {
		w.Write([]byte("ok"))
	})
	return mux
}

func (h *handler) extraer(w http.ResponseWriter, r *http.Request) {
	inicio := time.Now()
	if !h.autorizado(r) {
		responderError(w, &Error{Codigo: http.StatusUnauthorized, Mensaje: "falta la API key o no es valida"})
		return
	}
	var sol Solicitud
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxBytesCuerpo)).Decode(&sol); err != nil {
		responderError(w, nuevoError(http.StatusBadRequest, err, "el cuerpo debe ser un JSON con link y prompt"))
		return
	}

	ctx, cancelar := context.WithTimeout(r.Context(), TiempoMaximo)
	defer cancelar()
	res, err := h.servicio.Extraer(ctx, sol)
	if err != nil {
		log.Printf("extraccion: ERROR %s (%s): %v", hostDe(sol.Link), time.Since(inicio).Round(time.Millisecond), err)
		responderError(w, err)
		return
	}
	// Solo un resumen: la respuesta trae datos personales de clientes.
	log.Printf("extraccion: id=%d %s %s/%s %d pag. modelo=%s %d bytes (%s)", res.ID, hostDe(sol.Link),
		res.Tipo, res.Metodo, res.Paginas, res.Modelo, len(res.JSON), time.Since(inicio).Round(time.Millisecond))

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	if res.ID != 0 {
		w.Header().Set("X-Extraccion-Id", strconv.FormatInt(res.ID, 10))
	}
	w.Header().Set("X-Extraccion-Metodo", res.Metodo)
	w.Write(res.JSON)
}

func (h *handler) autorizado(r *http.Request) bool {
	if h.apiKey == "" {
		return true
	}
	recibida := r.Header.Get("X-API-Key")
	if bearer, ok := strings.CutPrefix(r.Header.Get("Authorization"), "Bearer "); ok {
		recibida = bearer
	}
	return subtle.ConstantTimeCompare([]byte(recibida), []byte(h.apiKey)) == 1
}

func responderError(w http.ResponseWriter, err error) {
	codigo, mensaje := http.StatusInternalServerError, "error interno"
	var e *Error
	if errors.As(err, &e) {
		codigo, mensaje = e.Codigo, e.Mensaje
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(codigo)
	json.NewEncoder(w).Encode(map[string]string{"error": mensaje})
}

func hostDe(link string) string {
	if u, err := url.Parse(link); err == nil && u.Host != "" {
		return u.Host
	}
	return "(link invalido)"
}
