package ia

import (
	"context"
	"fmt"

	"github.com/anthropics/anthropic-sdk-go"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

// EvaluarCierre manda el caso al subagente de cierre del tipo de OT
// (prompts/agentes) y devuelve su respuesta JSON.
func (c *Cliente) EvaluarCierre(ctx context.Context, codigoOT, mensaje string) (dato.Objeto, error) {
	sistema, err := SystemPromptAgente(codigoOT)
	if err != nil {
		return nil, err
	}
	if c.estado != nil {
		if cd := c.estado.CooldownActivo(); cd != nil {
			return nil, fmt.Errorf("Claude en cooldown: %s", cd.Razon)
		}
	}
	texto, err := c.llamar(ctx, "cierre "+codigoOT, sistema, []anthropic.ContentBlockParamUnion{anthropic.NewTextBlock(mensaje)}, 4000)
	if err != nil {
		if EsLimiteDeUso(err) && c.estado != nil {
			c.estado.ActivarCooldown(err.Error())
		}
		return nil, err
	}
	return ExtraerJSON(texto)
}
