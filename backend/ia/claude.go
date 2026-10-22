// Package ia analiza las actas con Claude (Anthropic).
package ia

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/estado"
)

// temperatura baja para respuestas consistentes. La API 2026-10-21 ya no la
// acepta: este cliente usa el SDK v1, que sigue en la version 2023-06-01.
const temperatura = 0.1

// Cliente llama a Claude y maneja el cooldown por limites de uso.
type Cliente struct {
	sdk    anthropic.Client
	modelo string
	estado *estado.Estado
}

// NewCliente crea el cliente con la API key y el modelo de la configuracion.
func NewCliente(cfg config.Config, est *estado.Estado) *Cliente {
	opciones := []option.RequestOption{
		option.WithAPIKey(cfg.AnthropicAPIKey),
		option.WithRequestTimeout(10 * time.Minute),
	}
	if cfg.AnthropicBaseURL != "" {
		opciones = append(opciones, option.WithBaseURL(cfg.AnthropicBaseURL))
	}
	return &Cliente{sdk: anthropic.NewClient(opciones...), modelo: cfg.ClaudeModel, estado: est}
}

// Modelo devuelve el modelo configurado.
func (c *Cliente) Modelo() string { return c.modelo }

// EsLimiteDeUso indica si la API respondio 429 (rate limit) o 529 (sobrecargada).
func EsLimiteDeUso(err error) bool {
	var apierr *anthropic.Error
	return errors.As(err, &apierr) && (apierr.StatusCode == 429 || apierr.StatusCode == 529)
}

// errJSONInvalido indica que la respuesta no trae un objeto JSON parseable.
var errJSONInvalido = errors.New("JSON invalido")

// ExtraerJSON parsea el objeto JSON de la respuesta aunque venga envuelto en
// ```json o con texto alrededor.
func ExtraerJSON(texto string) (dato.Objeto, error) {
	if strings.Contains(texto, "```json") {
		texto = strings.TrimSpace(strings.SplitN(strings.SplitN(texto, "```json", 2)[1], "```", 2)[0])
	} else if strings.Contains(texto, "```") {
		texto = strings.TrimSpace(strings.SplitN(strings.SplitN(texto, "```", 2)[1], "```", 2)[0])
	}
	inicio := strings.Index(texto, "{")
	fin := strings.LastIndex(texto, "}")
	if inicio != -1 && fin != -1 && fin >= inicio {
		texto = texto[inicio : fin+1]
	}
	var obj dato.Objeto
	if err := dato.Decodificar([]byte(texto), &obj); err != nil || obj == nil {
		return nil, errJSONInvalido
	}
	return obj, nil
}

func bloquesImagen(imagenes [][]byte) []anthropic.ContentBlockParamUnion {
	bloques := make([]anthropic.ContentBlockParamUnion, 0, len(imagenes))
	for _, img := range imagenes {
		bloques = append(bloques, anthropic.NewImageBlockBase64("image/jpeg", base64.StdEncoding.EncodeToString(img)))
	}
	return bloques
}

// llamar envia un mensaje (con system prompt cacheado 1 hora si se da) y devuelve el texto.
func (c *Cliente) llamar(ctx context.Context, etiqueta, sistema string, contenido []anthropic.ContentBlockParamUnion, maxTokens int64) (string, error) {
	params := anthropic.MessageNewParams{
		Model:       anthropic.Model(c.modelo),
		MaxTokens:   maxTokens,
		Temperature: anthropic.Float(temperatura),
		Messages:    []anthropic.MessageParam{anthropic.NewUserMessage(contenido...)},
	}
	if sistema != "" {
		params.System = []anthropic.TextBlockParam{{
			Text:         sistema,
			CacheControl: anthropic.CacheControlEphemeralParam{TTL: anthropic.CacheControlEphemeralTTLTTL1h},
		}}
	}
	resp, err := c.sdk.Messages.New(ctx, params)
	if err != nil {
		return "", err
	}
	if etiqueta != "" {
		u := resp.Usage
		fmt.Printf("  Claude %s tokens: in=%d out=%d cache_w=%d cache_r=%d\n",
			etiqueta, u.InputTokens, u.OutputTokens, u.CacheCreationInputTokens, u.CacheReadInputTokens)
	}
	var texto strings.Builder
	for _, b := range resp.Content {
		if b.Type == "text" {
			texto.WriteString(b.Text)
		}
	}
	return strings.TrimSpace(texto.String()), nil
}

// recortar devuelve los primeros n caracteres (no bytes) del texto.
func recortar(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}
