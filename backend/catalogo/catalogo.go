// Package catalogo tiene el catalogo oficial de tipificaciones de BIA y las
// reglas de clasificacion por tipo de servicio.
package catalogo

import (
	"regexp"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
)

// Tipificacion es una causa raiz del catalogo y su responsable.
type Tipificacion struct {
	Causa       string
	Responsable string
}

// Tipificaciones es el catalogo oficial, en orden (el orden se usa en el prompt
// y para desempatar el match aproximado).
var Tipificaciones = []Tipificacion{
	// Account executive
	{"Cliente abandona proceso", "Account executive"},
	{"Cliente no conoce alcance de la actividad", "Account executive"},
	{"Documentacion incompleta", "Account executive"},
	{"OR no conoce requerimiento descargos", "Account executive"},
	{"OR no tiene conocimiento de la actividad", "Account executive"},
	{"Propietario no conoce alcance de la actividad", "Account executive"},
	{"Datos de ubicación erroneo", "Account executive"},
	{"Permisos de ingreso", "Account executive"},
	{"Error en la creación de la OT", "Account executive"},
	{"Falta activar frontera para realizar actividad", "Account executive"},
	{"La OT ya fue realizada", "Account executive"},
	{"OT Duplicada", "Account executive"},
	{"OT Fuera de SLA", "Account executive"},
	{"No se cancelo actividad apesar de solicitud del cliente", "Account executive"},
	// Operador de red
	{"Falla en la red, debe normalizar OR", "Operador de red"},
	{"OR exige adecuaciones adicionales", "Operador de red"},
	{"OR no asiste o llega tarde", "Operador de red"},
	{"OR no cumple requerimientos de la actividad", "Operador de red"},
	{"Permisos del municipio", "Operador de red"},
	// Safety
	{"Documentacion SST", "Safety Specialist"},
	// Coordinador
	{"Coordinador no confirma actividad", "Coordinador"},
	{"Contratista/ Tecnico no llega a la hora programada", "Coordinador"},
	{"Información faltante/ erronea en acta", "Coordinador"},
	// Technical expert
	{"Confirmacion de Alcance en actividad", "Technical expert"},
	{"Error en alcance", "Technical expert"},
	// Contratista
	{"Fallas en el Alistamiento Operativo", "Contratista"},
	{"Contratista no asiste o llega tarde", "Contratista"},
	{"Configuracion del modem", "Contratista"},
	// Supply
	{"Certificados de equipo", "Supply"},
	{"Equipos en sitio", "Supply"},
	{"Averia de equipo pre instalacion", "Supply"},
	{"Sim card", "Supply"},
	// Centro comercial
	{"Permisos propietario", "Centro comercial"},
	// Cliente
	{"Falla cliente-Gestion", "Cliente"},
	{"Agendamiento cliente", "Cliente"},
	{"Demora en el acceso", "Cliente"},
	{"Acceso a gabinete", "Cliente"},
	{"Cliente retira los equipos", "Cliente"},
	{"Cliente en reclamación", "Cliente"},
	{"Cliente realizo pago", "Cliente"},
	{"Cliente suspendido", "Cliente"},
	{"Cliente fuera del mercado BIA", "Cliente"},
	{"Cliente en cobro juridico", "Cliente"},
	{"Acuerdo de pago en punto", "Cliente"},
	// Factor externo
	{"Animales impiden acceso a la medida", "Factor externo"},
	{"Riesgo electrico", "Factor externo"},
	{"Codigo duplicado", "Factor externo"},
	{"Lluvias", "Factor externo"},
	{"Acceso a la medida", "Factor externo"},
	{"Manifestaciones / bloqueos / carretera cerrada", "Factor externo"},
	{"Cubertura en datos moviles", "Factor externo"},
	{"Medidor averiado", "Factor externo"},
	{"No hay registro del medidor bia encontrado", "Factor externo"},
	{"No se encuentra medidor", "Factor externo"},
	{"No se encuentra modem", "Factor externo"},
	{"Modem averiado", "Factor externo"},
	{"Telemedida conecta y normalizada antes de visita", "Factor externo"},
	{"Equipos averiados", "Factor externo"},
	{"Se requiere acompañamiento policial", "Factor externo"},
	{"Sin acceso a la plataforma para pagar", "Factor externo"},
	{"Medida es compartida", "Factor externo"},
	{"Predio desocupado, imposibilidad de acceso a la medida", "Factor externo"},
}

// CausaPorDefecto se usa cuando la IA no propone una causa reconocible.
const CausaPorDefecto = "Información faltante/ erronea en acta"

// palabrasClave infieren la causa desde la observacion del tecnico, en orden.
var palabrasClave = []struct{ clave, causa string }{
	{"reprogr", "Agendamiento cliente"},
	{"no atiende", "Agendamiento cliente"},
	{"no puede atender", "Agendamiento cliente"},
	{"ausente", "Falla cliente-Gestion"},
	{"no hay quien", "Falla cliente-Gestion"},
	{"permiso", "Permisos de ingreso"},
	{"ingreso", "Permisos de ingreso"},
	{"acceso", "Acceso a la medida"},
	{"lluvia", "Lluvias"},
	{"riesgo electrico", "Riesgo electrico"},
	{"manifestacion", "Manifestaciones / bloqueos / carretera cerrada"},
	{"bloqueo", "Manifestaciones / bloqueos / carretera cerrada"},
	{"medidor averiado", "Medidor averiado"},
	{"modem averiado", "Modem averiado"},
	{"no se encuentra medidor", "No se encuentra medidor"},
	{"no se encuentra modem", "No se encuentra modem"},
	{"or no asist", "OR no asiste o llega tarde"},
	{"or no llego", "OR no asiste o llega tarde"},
	{"operador de red no", "OR no asiste o llega tarde"},
	{"contratista no asist", "Contratista no asiste o llega tarde"},
}

// Responsable devuelve el responsable de una causa del catalogo.
func Responsable(causa string) string {
	for _, t := range Tipificaciones {
		if t.Causa == causa {
			return t.Responsable
		}
	}
	return ""
}

// \w de Python incluye letras con tilde; el de Go no.
var rePalabra = regexp.MustCompile(`[\p{L}\p{N}_]+`)

func palabras(s string) map[string]bool {
	out := map[string]bool{}
	for _, p := range rePalabra.FindAllString(s, -1) {
		out[p] = true
	}
	return out
}

// ValidarTipificacion asegura que la causa raiz de una OT fallida este en el
// catalogo y le asigna su responsable. Si la IA propuso un responsable combinado
// (con /) que incluye el del catalogo, se respeta.
func ValidarTipificacion(qa dato.Objeto) {
	if qa["estado_ot"] != "FALLIDA" {
		return
	}
	falla := dato.Hijo(qa, "tipificacion_falla")
	if falla == nil {
		falla = dato.Objeto{}
	}
	causaOrig := dato.TextoLimpio(falla["causa_raiz"])
	responsableOrig := dato.TextoLimpio(falla["responsable"])

	// Match exacto (sin distinguir mayusculas)
	causaLower := strings.ToLower(causaOrig)
	match := ""
	for _, t := range Tipificaciones {
		if strings.ToLower(t.Causa) == causaLower {
			match = t.Causa
			break
		}
	}

	// Match aproximado: la del catalogo con mas palabras en comun
	if match == "" && causaOrig != "" {
		palabrasCausa := palabras(causaLower)
		mejor := 0
		for _, t := range Tipificaciones {
			score := 0
			for p := range palabras(strings.ToLower(t.Causa)) {
				if palabrasCausa[p] {
					score++
				}
			}
			if score > mejor {
				mejor = score
				match = t.Causa
			}
		}
		// Si el mejor match es muy debil, mejor el default
		if mejor < 2 {
			match = ""
		}
	}

	// Si la IA invento una causa, intentar inferirla desde la observacion
	if match == "" {
		observacion := strings.ToLower(dato.Texto(qa["observacion_tecnico_verbatim"]))
		for _, pc := range palabrasClave {
			if strings.Contains(observacion, pc.clave) {
				match = pc.causa
				break
			}
		}
	}
	if match == "" {
		match = CausaPorDefecto
	}

	responsable := Responsable(match)
	if strings.Contains(responsableOrig, "/") && strings.Contains(strings.ToLower(responsableOrig), strings.ToLower(responsable)) {
		responsable = responsableOrig
	}
	falla["causa_raiz"] = match
	falla["responsable"] = responsable
	qa["tipificacion_falla"] = falla
}

// QATrack clasifica el tipo de servicio: "Activacion", "Energy Solutions" o "Retencion".
func QATrack(tipoServicio string) string {
	t := strings.ToLower(tipoServicio)
	// Energy Solutions: mantenimiento, bancos de condensadores, BIA Monitor
	for _, k := range []string{"mantenimiento", "condensador", "banco", "bia monitor", "monitor", "carro canasta"} {
		if strings.Contains(t, k) {
			return "Energy Solutions"
		}
	}
	// Activacion: visitas previas + instalaciones + alta ingenieria
	if strings.Contains(t, "previa") || strings.Contains(t, "instala") || strings.Contains(t, "alta ingenier") {
		return "Activacion"
	}
	return "Retencion"
}

// NecesitaVisionLite indica si el tipo de servicio tiene actas fisicas manuscritas
// dentro del PDF (PQR, visita conjunta, emergencia).
func NecesitaVisionLite(tipoServicio string) bool {
	t := strings.ToLower(tipoServicio)
	for _, k := range []string{"pqr", "visita conjunta", "vico", "emergencia", "alrt"} {
		if strings.Contains(t, k) {
			return true
		}
	}
	return false
}

// RequiereComparacionWMS indica si el acta se compara contra los equipos asignados en WMS.
func RequiereComparacionWMS(tipoServicio, qaTrack string) bool {
	if qaTrack == "Activacion" {
		return true
	}
	// Match EXACTO para no confundir con 'Normalizacion Telemedidas'.
	switch strings.ToLower(strings.TrimSpace(tipoServicio)) {
	case "normalizacion medida", "normalización medida", "normalizacion emergencias", "normalización emergencias":
		return true
	}
	return false
}

// Planner devuelve el planner responsable segun el operador de red.
func Planner(cfg config.Config, orNorm string) string {
	for _, p := range cfg.ORPlanners {
		if strings.Contains(strings.ToUpper(orNorm), strings.ToUpper(p.OR)) {
			return p.Planner
		}
	}
	return cfg.PlannerDefault
}
