// Package cierre conecta los subagentes de cierre (uno por tipo de OT, ver
// backend/ia/prompts/agentes) al QA: arma el caso con todas las fuentes, se lo
// manda al subagente de la OT y valida su veredicto.
//
// El subagente NO reemplaza el estado de App Ops (estado_ot): da un segundo
// veredicto, independiente, que queda en resultado_qa_completo.cierre_ia para
// que el revisor lo compare en el dashboard.
package cierre

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/metabase"
)

// Caso son las fuentes que recibe el subagente.
type Caso struct {
	Tipo            catalogo.TipoOT
	TipoServicio    string
	EstadoReportado string // electrician_status_id de App Ops
	CodigoCO        string
	Acta            dato.Objeto // JSON extraido del acta, antes de simplificar las fallidas
	TextoActa       string
	Alcance         metabase.Fila        // nil = sin alcance
	Equipos         *metabase.EquiposWMS // nil = sin equipos en WMS
	Validaciones    dato.Objeto
}

// Evaluador es el modelo que hace de subagente (ia.Cliente).
type Evaluador interface {
	EvaluarCierre(ctx context.Context, codigoOT, mensaje string) (dato.Objeto, error)
}

// maxTextoActa: el texto del acta va completo salvo que sea enorme.
const maxTextoActa = 40000

// Claves del acta extraida que no son evidencia de campo: el subagente no las recibe.
var clavesQueNoSonEvidencia = []string{"estado_ot", "tipificacion_falla", "qa_track", "estado_revision", "estado_app_ops"}

// Mensaje arma el mensaje con los bloques que define agentes/comun.md.
func Mensaje(c Caso) string {
	var b strings.Builder
	fmt.Fprintf(&b, "TIPO DE OT: %s (%s)\nESTADO REPORTADO: %s\nCODIGO INTERNO BIA: %s\n",
		c.Tipo.Codigo, c.TipoServicio, noDisponible(c.EstadoReportado, "sin estado"), noDisponible(c.CodigoCO, "sin código"))

	acta := dato.Objeto{}
	for k, v := range c.Acta {
		acta[k] = v
	}
	for _, k := range clavesQueNoSonEvidencia {
		delete(acta, k)
	}
	b.WriteString("\n--- ACTA EXTRAIDA (JSON) ---\n")
	b.WriteString(codificar(acta))

	b.WriteString("\n\n--- TEXTO DEL ACTA ---\n")
	texto := strings.TrimSpace(c.TextoActa)
	switch r := []rune(texto); {
	case len(r) == 0:
		b.WriteString("(NO DISPONIBLE: el PDF no trae texto; puede ser un acta escaneada o manuscrita)")
	case len(r) > maxTextoActa:
		b.WriteString(string(r[:maxTextoActa]))
		fmt.Fprintf(&b, "\n(TEXTO RECORTADO: el acta tiene %d caracteres y aquí van los primeros %d)", len(r), maxTextoActa)
	default:
		b.WriteString(texto)
	}

	b.WriteString("\n\n--- ALCANCE ---\n")
	if len(c.Alcance) == 0 {
		b.WriteString("(NO DISPONIBLE: el cliente no tiene alcance de ingeniería registrado)")
	} else {
		claves := make([]string, 0, len(c.Alcance))
		for k := range c.Alcance {
			claves = append(claves, k)
		}
		sort.Strings(claves)
		for _, k := range claves {
			if v := strings.TrimSpace(c.Alcance[k]); v != "" {
				fmt.Fprintf(&b, "%s: %s\n", k, v)
			}
		}
	}

	b.WriteString("\n--- EQUIPOS ASIGNADOS (WMS) ---\n")
	if c.Equipos == nil || (c.Equipos.Medidor == nil && len(c.Equipos.TCs) == 0 && len(c.Equipos.TPs) == 0) {
		b.WriteString("(NO DISPONIBLE: el cliente no tiene equipos registrados en WMS)")
	} else {
		if m := c.Equipos.Medidor; m != nil {
			fmt.Fprintf(&b, "Medidor: %s (%s, %s)\n", m.Serial, m.Marca, m.Estado)
		}
		for _, t := range c.Equipos.TCs {
			fmt.Fprintf(&b, "TC: %s (%s, %s)\n", t.Serial, t.Marca, t.Estado)
		}
		for _, t := range c.Equipos.TPs {
			fmt.Fprintf(&b, "TP: %s (%s, %s)\n", t.Serial, t.Marca, t.Estado)
		}
	}

	b.WriteString("\n--- NOTAS ---\n(NO DISPONIBLE: todavía no hay una fuente de notas de la visita)\n")

	b.WriteString("\n--- VALIDACIONES DEL BACKEND ---\n")
	b.WriteString(codificar(c.Validaciones))
	b.WriteString("\n")
	return b.String()
}

// Evaluar le manda el caso al subagente y valida su respuesta. El resultado
// lleva ademas que subagente respondio y si sus reglas siguen en borrador.
func Evaluar(ctx context.Context, ev Evaluador, c Caso) (dato.Objeto, error) {
	r, err := ev.EvaluarCierre(ctx, c.Tipo.Codigo, Mensaje(c))
	if err != nil {
		return nil, err
	}
	return Validar(r, c)
}

// Validar normaliza la respuesta del subagente:
//   - veredicto EXITOSA, FALLIDA o PENDIENTE; PENDIENTE solo si la OT lo admite;
//   - pendientes solo con PENDIENTE y tipificacion solo con FALLIDA;
//   - la causa de la tipificacion ajustada al catalogo.
func Validar(r dato.Objeto, c Caso) (dato.Objeto, error) {
	veredicto := strings.ToUpper(dato.TextoLimpio(r["veredicto"]))
	switch veredicto {
	case "EXITOSA", "FALLIDA", "PENDIENTE":
	default:
		return nil, fmt.Errorf("el subagente %s devolvió un veredicto inválido: %q", c.Tipo.Codigo, veredicto)
	}
	hallazgos := dato.Lista(r["hallazgos"])
	if veredicto == "PENDIENTE" && !c.Tipo.PermitePendiente {
		veredicto = "FALLIDA"
		hallazgos = append(hallazgos, "El subagente propuso PENDIENTE, que esta OT no admite: se toma como FALLIDA.")
	}
	r["veredicto"] = veredicto
	r["hallazgos"] = hallazgos
	if veredicto != "PENDIENTE" {
		r["pendientes"] = []any{}
	}
	if veredicto == "FALLIDA" {
		// ValidarTipificacion trabaja sobre un QA: se le arma uno con lo justo.
		tipificacion := dato.Mapa(r["tipificacion_falla"])
		if tipificacion == nil {
			tipificacion = dato.Objeto{}
		}
		tmp := dato.Objeto{
			"estado_ot":                    "FALLIDA",
			"tipificacion_falla":           tipificacion,
			"observacion_tecnico_verbatim": c.Acta["observacion_tecnico_verbatim"],
		}
		catalogo.ValidarTipificacion(tmp)
		r["tipificacion_falla"] = tmp["tipificacion_falla"]
	} else {
		r["tipificacion_falla"] = nil
	}
	r["subagente"] = c.Tipo.Codigo
	r["subagente_nombre"] = c.Tipo.Nombre
	r["familia"] = string(c.Tipo.Familia)
	r["borrador"] = c.Tipo.Borrador
	return r, nil
}

func noDisponible(s, porDefecto string) string {
	if strings.TrimSpace(s) == "" {
		return porDefecto
	}
	return s
}

func codificar(v any) string {
	if v == nil {
		return "{}"
	}
	data, err := dato.Codificar(v, true)
	if err != nil {
		return fmt.Sprintf("(no se pudo codificar: %v)", err)
	}
	return string(data)
}
