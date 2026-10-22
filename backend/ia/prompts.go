package ia

// System prompts de Claude. El texto vive en prompts/ (ver prompts/README.md)
// y va embebido en el binario. {{CATALOGO}} y {{CATALOGO_POR_RESPONSABLE}} se
// reemplazan por el catalogo de tipificaciones.

import (
	_ "embed"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
)

var (
	//go:embed prompts/qa_lite.md
	promptLite string
	//go:embed prompts/qa_full.md
	promptFull string
	//go:embed prompts/evaluador_cierre_v1.md
	promptEvaluadorCierre string
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

// SystemPromptEvaluadorCierre es el system prompt del evaluador de cierre v1:
// segunda etapa que decide EXITOSA / FALLIDA / PENDIENTE sobre el acta ya
// extraida. Todavia no lo usa el pipeline (ver prompts/README.md).
func SystemPromptEvaluadorCierre() string {
	return strings.Replace(promptEvaluadorCierre, "{{CATALOGO_POR_RESPONSABLE}}", catalogoPorResponsable(), 1)
}
