package ia

// Extraccion de informacion de documentos con Claude, para el servicio
// backend/extraccion. A diferencia del QA, no manda temperature: los modelos
// actuales (Opus 5.5, Haiku 5.5…) la rechazan.

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/shared/constant"
)

// maxTokensExtraccion deja espacio para el razonamiento del modelo y JSON largos.
const maxTokensExtraccion = 16000

// Imagen es una imagen para Claude: image/jpeg, image/png, image/gif o image/webp.
type Imagen struct {
	Tipo  string
	Datos []byte
}

// PaginaTexto es una pagina de la que se pudo sacar el texto.
type PaginaTexto struct {
	Numero int
	Texto  string
}

// PaginaImagen es una pagina que va como imagen (escaneo, foto o una imagen suelta).
type PaginaImagen struct {
	Numero int
	Imagen Imagen
}

// Documento es lo que Claude recibe del archivo.
type Documento struct {
	Tipo     string // "pdf" o "imagen"
	Paginas  int
	Texto    []PaginaTexto
	Imagenes []PaginaImagen
}

// RespuestaExtraccion es el JSON extraido y con que modelo y cuantos tokens se obtuvo.
type RespuestaExtraccion struct {
	JSON          json.RawMessage
	Modelo        string // el que respondio: puede ser el de respaldo si el principal rechazo
	TokensEntrada int64
	TokensSalida  int64
}

// Errores de la respuesta de Claude.
var (
	ErrRechazo          = errors.New("Claude declino procesar el documento")
	ErrRespuestaCortada = errors.New("la respuesta de Claude supero el maximo de tokens")
	ErrSinJSON          = errors.New("Claude no devolvio un objeto JSON valido")
)

// ExtraerInformacion le pide a Claude el JSON que describe la instruccion con
// los datos del documento. esfuerzo vacio = el del modelo.
func (c *Cliente) ExtraerInformacion(ctx context.Context, instruccion string, doc Documento, esfuerzo string) (RespuestaExtraccion, error) {
	params := anthropic.BetaMessageNewParams{
		Model:     anthropic.Model(c.modelo),
		MaxTokens: maxTokensExtraccion,
		System:    []anthropic.BetaTextBlockParam{{Text: SystemPromptExtraccion()}},
		Messages:  []anthropic.BetaMessageParam{anthropic.NewBetaUserMessage(contenidoExtraccion(instruccion, doc)...)},
	}
	if esfuerzo != "" {
		params.OutputConfig = anthropic.BetaOutputConfigParam{Effort: anthropic.BetaOutputConfigEffort(esfuerzo)}
	}
	// Si el modelo declina por sus filtros de seguridad, la API reintenta sola
	// con un modelo de respaldo dentro de la misma llamada.
	if AdmiteRespaldo(c.modelo) {
		params.Betas = []anthropic.AnthropicBeta{anthropic.AnthropicBetaServerSideFallback2026_07_01}
		params.Fallbacks = anthropic.BetaFallbacksParamUnion{OfDefault: constant.ValueOf[constant.Default]()}
	}

	resp, err := c.sdk.Beta.Messages.New(ctx, params)
	if err != nil {
		return RespuestaExtraccion{}, err
	}
	switch resp.StopReason {
	case anthropic.BetaStopReasonRefusal:
		return RespuestaExtraccion{}, ErrRechazo
	case anthropic.BetaStopReasonMaxTokens:
		return RespuestaExtraccion{}, ErrRespuestaCortada
	}
	var texto strings.Builder
	for _, b := range resp.Content {
		if b.Type == "text" {
			texto.WriteString(b.Text)
		}
	}
	crudo := strings.TrimSpace(recortarJSON(texto.String()))
	var objeto map[string]json.RawMessage
	if err := json.Unmarshal([]byte(crudo), &objeto); err != nil || objeto == nil {
		return RespuestaExtraccion{}, ErrSinJSON
	}
	return RespuestaExtraccion{
		JSON:          json.RawMessage(crudo),
		Modelo:        string(resp.Model),
		TokensEntrada: resp.Usage.InputTokens,
		TokensSalida:  resp.Usage.OutputTokens,
	}, nil
}

// AdmiteRespaldo indica si el modelo acepta el respaldo automatico ante un rechazo.
func AdmiteRespaldo(modelo string) bool {
	return strings.HasPrefix(modelo, "claude-opus-5") ||
		strings.HasPrefix(modelo, "claude-fable-5") ||
		modelo == "claude-sonnet-5-5"
}

// contenidoExtraccion arma el mensaje: cada imagen con su etiqueta y al final
// la instruccion con el texto de las paginas.
func contenidoExtraccion(instruccion string, doc Documento) []anthropic.BetaContentBlockParamUnion {
	var bloques []anthropic.BetaContentBlockParamUnion
	for _, p := range doc.Imagenes {
		etiqueta := fmt.Sprintf("Página %d:", p.Numero)
		if doc.Tipo == "imagen" {
			etiqueta = "Imagen del documento:"
		}
		bloques = append(bloques,
			anthropic.NewBetaTextBlock(etiqueta),
			anthropic.NewBetaImageBlock(anthropic.BetaBase64ImageSourceParam{
				Data:      base64.StdEncoding.EncodeToString(p.Imagen.Datos),
				MediaType: anthropic.BetaBase64ImageSourceMediaType(p.Imagen.Tipo),
			}))
	}
	return append(bloques, anthropic.NewBetaTextBlock(MensajeExtraccion(instruccion, doc)))
}

// MensajeExtraccion es el texto del mensaje: instruccion, descripcion del
// documento y texto de cada pagina.
func MensajeExtraccion(instruccion string, doc Documento) string {
	var b strings.Builder
	b.WriteString("INSTRUCCIÓN:\n")
	b.WriteString(strings.TrimSpace(instruccion))
	b.WriteString("\n\n")
	if doc.Tipo == "imagen" {
		b.WriteString("DOCUMENTO: una imagen, adjunta arriba.\n")
		return b.String()
	}
	fmt.Fprintf(&b, "DOCUMENTO: PDF de %d página(s).", doc.Paginas)
	if len(doc.Imagenes) > 0 {
		numeros := make([]string, len(doc.Imagenes))
		for i, p := range doc.Imagenes {
			numeros[i] = fmt.Sprint(p.Numero)
		}
		fmt.Fprintf(&b, " Sin texto extraíble (van como imagen arriba): página(s) %s.", strings.Join(numeros, ", "))
	}
	b.WriteString("\n")
	for _, p := range doc.Texto {
		fmt.Fprintf(&b, "\n--- PÁGINA %d ---\n%s\n", p.Numero, p.Texto)
	}
	return b.String()
}
