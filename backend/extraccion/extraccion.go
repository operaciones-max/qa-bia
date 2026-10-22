// Package extraccion es el servicio de extraccion de informacion de documentos
// (OCR con IA): recibe el link de un PDF o una imagen y una instruccion con el
// JSON esperado, y devuelve ese JSON con los datos del documento.
//
// Capas, de afuera hacia adentro:
//   - http.go: recibe la peticion y responde (handler).
//   - Servicio.Extraer: el caso de uso. Descarga el archivo (descarga.go), lo
//     prepara para Claude (documento.go) y pide el JSON (Extractor = ia.Cliente).
//   - Repositorio: guarda cada solicitud con su respuesta (repositorio.go = Supabase).
package extraccion

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/operaciones-max/qa-bia/backend/ia"
)

// Solicitud es el cuerpo de la peticion (mismos campos que el servicio original).
type Solicitud struct {
	Link   string `json:"link"`
	Prompt string `json:"prompt"`
}

// Resultado es el JSON extraido y como se obtuvo.
type Resultado struct {
	ID      int64 // id en la tabla extracciones (0 si no se guardo)
	Tipo    string
	Metodo  string
	Paginas int
	Modelo  string
	JSON    json.RawMessage
}

// Extractor es la IA que arma el JSON (lo implementa ia.Cliente).
type Extractor interface {
	ExtraerInformacion(ctx context.Context, instruccion string, doc ia.Documento, esfuerzo string) (ia.RespuestaExtraccion, error)
}

// Repositorio guarda cada solicitud con su respuesta.
type Repositorio interface {
	Guardar(ctx context.Context, r Registro) (int64, error)
}

// Registro es una fila de la tabla extracciones.
type Registro struct {
	Solicitud     Solicitud
	Tipo          string
	Metodo        string
	Paginas       int
	Modelo        string
	Respuesta     json.RawMessage
	Error         string
	Duracion      time.Duration
	TokensEntrada int64
	TokensSalida  int64
}

// Error es un error con el codigo HTTP que le corresponde. Mensaje es lo que
// ve quien llama; Causa queda solo en el log.
type Error struct {
	Codigo  int
	Mensaje string
	Causa   error
}

func (e *Error) Error() string {
	if e.Causa != nil {
		return e.Mensaje + ": " + e.Causa.Error()
	}
	return e.Mensaje
}

func (e *Error) Unwrap() error { return e.Causa }

func nuevoError(codigo int, causa error, formato string, args ...any) *Error {
	return &Error{Codigo: codigo, Mensaje: fmt.Sprintf(formato, args...), Causa: causa}
}

// Largo maximo de la instruccion (el JSON esperado va adentro).
const maxPrompt = 20000

// Servicio es el caso de uso de extraccion.
type Servicio struct {
	descargador *Descargador
	extractor   Extractor
	repo        Repositorio // nil = no se guarda
	esfuerzo    string
}

// NuevoServicio arma el servicio. repo puede ser nil (por ejemplo, sin Supabase en local).
func NuevoServicio(descargador *Descargador, extractor Extractor, repo Repositorio, esfuerzo string) *Servicio {
	return &Servicio{descargador: descargador, extractor: extractor, repo: repo, esfuerzo: esfuerzo}
}

// Extraer descarga el documento, le pide el JSON a Claude y guarda la solicitud
// con su resultado (o su error).
func (s *Servicio) Extraer(ctx context.Context, sol Solicitud) (Resultado, error) {
	sol.Link = strings.TrimSpace(sol.Link)
	sol.Prompt = strings.TrimSpace(sol.Prompt)
	switch {
	case sol.Link == "":
		return Resultado{}, nuevoError(http.StatusBadRequest, nil, "falta el campo link")
	case sol.Prompt == "":
		return Resultado{}, nuevoError(http.StatusBadRequest, nil, "falta el campo prompt con el JSON esperado")
	case len([]rune(sol.Prompt)) > maxPrompt:
		return Resultado{}, nuevoError(http.StatusBadRequest, nil, "el prompt supera los %d caracteres", maxPrompt)
	}

	inicio := time.Now()
	res, respuesta, err := s.extraer(ctx, sol)
	reg := Registro{
		Solicitud:     sol,
		Tipo:          res.Tipo,
		Metodo:        res.Metodo,
		Paginas:       res.Paginas,
		Modelo:        respuesta.Modelo,
		Respuesta:     res.JSON,
		Duracion:      time.Since(inicio),
		TokensEntrada: respuesta.TokensEntrada,
		TokensSalida:  respuesta.TokensSalida,
	}
	if err != nil {
		reg.Error = err.Error()
	}
	if s.repo != nil {
		id, errRepo := s.repo.Guardar(ctx, reg)
		if errRepo != nil {
			// El cliente igual recibe su resultado; solo se pierde el registro.
			log.Printf("extraccion: no se pudo guardar en Supabase: %v", errRepo)
		}
		res.ID = id
	}
	return res, err
}

func (s *Servicio) extraer(ctx context.Context, sol Solicitud) (Resultado, ia.RespuestaExtraccion, error) {
	datos, err := s.descargador.Descargar(ctx, sol.Link)
	if err != nil {
		return Resultado{}, ia.RespuestaExtraccion{}, err
	}
	doc, err := PrepararDocumento(datos)
	if err != nil {
		return Resultado{}, ia.RespuestaExtraccion{}, err
	}
	res := Resultado{Tipo: doc.Tipo, Metodo: Metodo(doc), Paginas: doc.Paginas}

	respuesta, err := s.extractor.ExtraerInformacion(ctx, sol.Prompt, doc, s.esfuerzo)
	if err != nil {
		return res, respuesta, errorDeIA(err)
	}
	res.Modelo = respuesta.Modelo
	res.JSON = respuesta.JSON
	return res, respuesta, nil
}

// errorDeIA traduce los errores de Claude a codigos HTTP.
func errorDeIA(err error) error {
	switch {
	case ia.EsLimiteDeUso(err):
		return nuevoError(http.StatusServiceUnavailable, err, "Claude esta saturado o se alcanzo el limite de uso; reintentar en unos minutos")
	case errors.Is(err, ia.ErrRechazo), errors.Is(err, ia.ErrRespuestaCortada), errors.Is(err, ia.ErrSinJSON):
		return nuevoError(http.StatusUnprocessableEntity, err, "%s", err.Error())
	case errors.Is(err, context.DeadlineExceeded), errors.Is(err, context.Canceled):
		return nuevoError(http.StatusGatewayTimeout, err, "Claude tardo demasiado en responder")
	default:
		return nuevoError(http.StatusBadGateway, err, "fallo la llamada a Claude")
	}
}
