// Package config tiene la configuracion del motor de QA.
//
// Los valores por defecto son los de produccion (GitHub Actions). Los secretos y
// los modos de ejecucion se leen de variables de entorno; en local se pueden
// poner en backend/.env (ver backend/.env.example). Las variables ya definidas
// en el entorno tienen prioridad sobre el archivo.
//
// Los programas se ejecutan desde la raiz del repo: las rutas relativas
// (backend/state, backend/reportes_qa) se resuelven contra ese directorio.
package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/operaciones-max/qa-bia/internal/envfile"
)

// Config es la configuracion de una corrida.
type Config struct {
	// Fuentes Metabase
	MetabaseBaseURL string
	ActasCSVURL     string
	WMSCSVURL       string
	AlcancesCSVURL  string
	MetabaseAPIKey  string

	// IA
	AnthropicAPIKey  string
	AnthropicBaseURL string // vacio = API de Anthropic; se cambia solo para pruebas
	ClaudeModel      string

	// Supabase (service role: el backend escribe todas las columnas)
	SupabaseURL string
	SupabaseKey string

	// Modos de ejecucion
	ModoPrueba            bool
	ModoUnico             bool
	ActasPrueba           int
	FechaInicio           string
	FechaInicioAlcances   string
	PausaEntreActasSeg    int
	PausaEntreAlcancesSeg int
	IntervaloSegundos     int
	MaxActasPorRun        int

	// Estado persistente y reportes
	StateDir                  string
	ArchivoProcesados         string
	ArchivoVisitasPrevias     string
	ArchivoAlcancesProcesados string
	ArchivoFacturasExtraidas  string
	ArchivoCooldownLLM        string
	CarpetaReportes           string

	// Reglas de negocio
	EstadosExitosos []string
	EstadosFallidos []string
	ORPlanners      []ORPlanner // en orden: gana el primero que coincida
	PlannerDefault  string
}

// ORPlanner asocia un operador de red con su planner.
type ORPlanner struct {
	OR      string
	Planner string
}

// Cargar lee el archivo .env indicado (si existe) y arma la configuracion.
func Cargar(archivoEnv string) Config {
	envfile.Cargar(archivoEnv)

	metabase := strings.TrimRight(env("METABASE_BASE_URL", "https://bia.metabaseapp.com"), "/")
	stateDir := env("QA_STATE_DIR", filepath.Join("backend", "state"))

	return Config{
		MetabaseBaseURL: metabase,
		ActasCSVURL:     metabase + "/public/question/5ec265f5-182d-409d-bfbd-45303880da2d.csv",
		WMSCSVURL:       metabase + "/public/question/67f6d437-6326-415a-a799-1ee34b9648b0.csv",
		AlcancesCSVURL:  metabase + "/public/question/52353a69-6510-405b-9bbd-754d762a2597.csv",
		MetabaseAPIKey:  env("METABASE_API_KEY", ""),

		AnthropicAPIKey:  env("ANTHROPIC_API_KEY", ""),
		AnthropicBaseURL: env("ANTHROPIC_BASE_URL", ""),
		// claude-haiku-4-5 = barato y rapido; claude-sonnet / claude-opus = mas capaces
		ClaudeModel: env("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),

		SupabaseURL: supabaseBaseURL(env("SUPABASE_URL", "")),
		SupabaseKey: firstNonEmpty(env("SUPABASE_SERVICE_ROLE_KEY", ""), env("SUPABASE_ANON_KEY", "")),

		ModoPrueba:            envBool("QA_MODO_PRUEBA", false),
		ModoUnico:             envBool("QA_MODO_UNICO", true),
		ActasPrueba:           envInt("QA_ACTAS_PRUEBA", 2),
		FechaInicio:           env("QA_FECHA_INICIO", "2026-05-10"),
		FechaInicioAlcances:   env("QA_FECHA_INICIO_ALCANCES", "2026-04-30"),
		PausaEntreActasSeg:    envInt("QA_PAUSA_ENTRE_ACTAS_SEGUNDOS", 20),
		PausaEntreAlcancesSeg: envInt("QA_PAUSA_ENTRE_ALCANCES_SEGUNDOS", 2),
		IntervaloSegundos:     300,
		MaxActasPorRun:        envInt("QA_MAX_ACTAS_POR_RUN", 30),

		StateDir:                  stateDir,
		ArchivoProcesados:         filepath.Join(stateDir, "actas_procesadas.json"),
		ArchivoVisitasPrevias:     filepath.Join(stateDir, "visitas_previas.json"),
		ArchivoAlcancesProcesados: filepath.Join(stateDir, "alcances_procesados.json"),
		ArchivoFacturasExtraidas:  filepath.Join(stateDir, "facturas_extraidas.json"),
		ArchivoCooldownLLM:        filepath.Join(stateDir, "llm_cooldown.json"),
		CarpetaReportes:           env("QA_CARPETA_REPORTES", filepath.Join("backend", "reportes_qa")),

		EstadosExitosos: []string{"CLOSURE_SUCCESSFUL", "COMPLETED"},
		EstadosFallidos: []string{"CLOSURE_FAILED", "ELECTRICIAN_FAILED_VISIT"},
		ORPlanners: []ORPlanner{
			{"ESSA", "Ervison Plata"},
			{"EPM", "Ervison Plata"},
			{"AIRE", "Ervison Plata"},
			{"AIR-E", "Ervison Plata"},
			{"AFINIA", "Ervison Plata"},
		},
		PlannerDefault: "Dinovi Sanchez",
	}
}

// EsExitoso indica si el estado del electricista cuenta como OT exitosa.
func (c Config) EsExitoso(estado string) bool { return contiene(c.EstadosExitosos, estado) }

// EsAnalizable indica si el estado del electricista entra al QA.
func (c Config) EsAnalizable(estado string) bool {
	return contiene(c.EstadosExitosos, estado) || contiene(c.EstadosFallidos, estado)
}

// SupabaseConfigurado indica si hay URL y key de Supabase.
func (c Config) SupabaseConfigurado() bool { return c.SupabaseURL != "" && c.SupabaseKey != "" }

func supabaseBaseURL(url string) string {
	url = strings.TrimRight(strings.TrimSpace(url), "/")
	return strings.TrimSuffix(url, "/rest/v1")
}

// env devuelve la variable sin espacios, o el default si esta vacia.
func env(nombre, porDefecto string) string { return envfile.Texto(nombre, porDefecto) }

func envBool(nombre string, porDefecto bool) bool { return envfile.Bool(nombre, porDefecto) }

func envInt(nombre string, porDefecto int) int {
	n, err := strconv.Atoi(strings.TrimSpace(os.Getenv(nombre)))
	if err != nil {
		return porDefecto
	}
	return n
}

func firstNonEmpty(valores ...string) string {
	for _, v := range valores {
		if v != "" {
			return v
		}
	}
	return ""
}

func contiene(lista []string, v string) bool {
	for _, x := range lista {
		if x == v {
			return true
		}
	}
	return false
}
