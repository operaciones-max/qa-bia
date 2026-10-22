package ia

// System prompts de Claude. El texto vive en prompts/ (ver prompts/README.md)
// y va embebido en el binario. Los marcadores {{...}} se reemplazan al armarlos.

import (
	"embed"
	"fmt"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
)

var (
	//go:embed prompts/qa_lite.md
	promptLite string
	//go:embed prompts/qa_full.md
	promptFull string
	//go:embed prompts/extraccion.md
	promptExtraccion string
	//go:embed prompts/agentes
	promptsAgentes embed.FS
)

// listaCatalogo arma "  - causa" por linea, en el orden del catalogo.
func listaCatalogo() string {
	lineas := make([]string, len(catalogo.Tipificaciones))
	for i, t := range catalogo.Tipificaciones {
		lineas[i] = "  - " + t.Causa
	}
	return strings.Join(lineas, "\n")
}

// catalogoPorResponsable arma "Responsable:" seguido de sus causas, en el orden
// del catalogo.
func catalogoPorResponsable() string {
	var orden []string
	causas := map[string][]string{}
	for _, t := range catalogo.Tipificaciones {
		if _, ok := causas[t.Responsable]; !ok {
			orden = append(orden, t.Responsable)
		}
		causas[t.Responsable] = append(causas[t.Responsable], t.Causa)
	}
	var b strings.Builder
	for i, r := range orden {
		if i > 0 {
			b.WriteString("\n")
		}
		b.WriteString(r + ":\n")
		for _, c := range causas[r] {
			b.WriteString("  - " + c + "\n")
		}
	}
	return strings.TrimSuffix(b.String(), "\n")
}

// SystemPromptLite es el system prompt del QA lite (Retencion / Energy Solutions).
func SystemPromptLite() string {
	return strings.Replace(promptLite, "{{CATALOGO}}", listaCatalogo(), 1)
}

// SystemPromptFull es el system prompt del QA full (Activacion y normalizaciones con WMS).
func SystemPromptFull() string {
	return strings.Replace(promptFull, "{{CATALOGO}}", listaCatalogo(), 1)
}

// SystemPromptAgente arma el system prompt del subagente de cierre de un tipo
// de OT: reglas comunes + las de su familia + las de la OT + catalogo. Decide
// EXITOSA / FALLIDA / PENDIENTE sobre el acta ya extraida. Todavia no lo usa
// el pipeline (ver prompts/README.md).
func SystemPromptAgente(codigo string) (string, error) {
	tipo, ok := catalogo.TipoOTPorCodigo(codigo)
	if !ok {
		return "", fmt.Errorf("tipo de OT desconocido: %q", codigo)
	}
	comun, err := promptsAgentes.ReadFile("prompts/agentes/comun.md")
	if err != nil {
		return "", err
	}
	familia, err := promptsAgentes.ReadFile("prompts/agentes/familias/" + string(tipo.Familia) + ".md")
	if err != nil {
		return "", fmt.Errorf("familia %s sin reglas: %w", tipo.Familia, err)
	}
	ot, err := promptsAgentes.ReadFile("prompts/agentes/ots/" + tipo.Codigo + ".md")
	if err != nil {
		return "", fmt.Errorf("OT %s sin reglas: %w", tipo.Codigo, err)
	}
	return strings.NewReplacer(
		"{{OT_CODIGO}}", tipo.Codigo,
		"{{OT_NOMBRE}}", tipo.Nombre,
		"{{OT_LINEA}}", tipo.Linea,
		"{{FAMILIA}}", strings.TrimSpace(string(familia)),
		"{{OT}}", strings.TrimSpace(string(ot)),
		"{{CATALOGO_POR_RESPONSABLE}}", catalogoPorResponsable(),
	).Replace(string(comun)), nil
}

// SystemPromptExtraccion es el system prompt del servicio de extraccion de
// documentos (backend/extraccion).
func SystemPromptExtraccion() string { return promptExtraccion }
