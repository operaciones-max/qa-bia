package catalogo

import "strings"

// Familia agrupa los tipos de OT que se evaluan con las mismas reglas generales.
// Cada familia tiene su archivo en backend/ia/prompts/agentes/familias/.
type Familia string

const (
	FamiliaPrevia        Familia = "previa"        // levantar informacion para armar un alcance
	FamiliaEjecucion     Familia = "ejecucion"     // ejecutar un trabajo definido de antemano
	FamiliaNormalizacion Familia = "normalizacion" // corregir una anomalia conocida
	FamiliaEmergencia    Familia = "emergencia"    // atender una falla reportada
	FamiliaRetiro        Familia = "retiro"        // retirar equipos
	FamiliaVerificacion  Familia = "verificacion"  // revisar, medir o acompanar sin intervenir
	FamiliaCartera       Familia = "cartera"       // suspender o reconectar por pago
	FamiliaGestion       Familia = "gestion"       // apoyar o formalizar otra actividad
)

// Lineas de negocio.
const (
	LineaVAS        = "VAS / Energy Solutions"
	LineaGeneracion = "Generación"
	LineaActivacion = "Activación"
	LineaRetencion  = "Retención"
)

// TipoOT es un tipo de OT con su subagente de cierre. Las reglas propias de
// cada uno estan en backend/ia/prompts/agentes/ots/<Codigo>.md.
type TipoOT struct {
	Codigo           string
	Nombre           string
	Linea            string
	Familia          Familia
	PermitePendiente bool
	// Borrador: las reglas se escribieron a partir del nombre de la OT y faltan
	// validarlas con operaciones (docs/agentes-ot.md). Las de VIPE, INST y DESX
	// vienen del prompt v1_closure_evaluator.
	Borrador bool
}

// TiposOT son todos los tipos de OT, por linea de negocio.
var TiposOT = []TipoOT{
	// VAS / Energy Solutions
	{"AING", "Alta Ingeniería", LineaVAS, FamiliaEjecucion, false, true},
	{"AMCA", "Ejecución aumento de carga", LineaVAS, FamiliaEjecucion, false, true},
	{"PREA", "Previa aumento de carga", LineaVAS, FamiliaPrevia, false, true},
	{"MANT", "Ejecución mantenimiento", LineaVAS, FamiliaEjecucion, false, true},
	{"PREM", "Previa mantenimiento", LineaVAS, FamiliaPrevia, false, true},
	{"TERM", "Ejecución termografía", LineaVAS, FamiliaEjecucion, false, true},
	{"PRET", "Previa termografía", LineaVAS, FamiliaPrevia, false, true},
	{"ISNT", "Instalación Cambio NT", LineaVAS, FamiliaEjecucion, false, true},
	{"VPNT", "Visita Previa Cambio NT", LineaVAS, FamiliaPrevia, false, true},
	{"ISIC", "Ejecución Independización Cuentas", LineaVAS, FamiliaEjecucion, false, true},
	{"PVIC", "Previa Independización Cuentas", LineaVAS, FamiliaPrevia, false, true},
	{"BICH", "Instalación BIA Monitor", LineaVAS, FamiliaEjecucion, false, true},
	{"PREB", "Previa Bichito", LineaVAS, FamiliaPrevia, false, true},
	{"NOBI", "Normalización BIA Monitor", LineaVAS, FamiliaNormalizacion, false, true},
	{"ALBI", "Emergencia BIA Monitor", LineaVAS, FamiliaEmergencia, false, true},
	{"REBI", "Retiro BIA Monitor", LineaVAS, FamiliaRetiro, false, true},
	{"COND", "Instalación condensadores", LineaVAS, FamiliaEjecucion, false, true},
	{"PREC", "Previa Bancos de Condensadores", LineaVAS, FamiliaPrevia, false, true},
	{"NOCO", "Normalización condensadores", LineaVAS, FamiliaNormalizacion, false, true},
	{"ALCO", "Emergencia Banco de Condensadores", LineaVAS, FamiliaEmergencia, false, true},
	{"RECO", "Retiro Banco de Condensadores", LineaVAS, FamiliaRetiro, false, true},
	// Generacion
	{"GVICO", "Visita Conjunta Generación", LineaGeneracion, FamiliaVerificacion, false, true},
	// Activacion
	{"VIPE", "Visita previa", LineaActivacion, FamiliaPrevia, false, false},
	{"PREV", "Visita pre-venta", LineaActivacion, FamiliaPrevia, false, true},
	{"INST", "Instalación", LineaActivacion, FamiliaEjecucion, true, false},
	{"LEGA", "Legalización", LineaActivacion, FamiliaGestion, false, true},
	{"NORM", "Normalización medida", LineaActivacion, FamiliaNormalizacion, false, true},
	{"VIAD", "Visita Adicional", LineaActivacion, FamiliaEjecucion, false, true},
	{"SUCA", "Suministro de carro canasta", LineaActivacion, FamiliaGestion, false, true},
	{"REQA", "Revisión por QA", LineaActivacion, FamiliaVerificacion, false, true},
	{"PRRU", "Pruebas de Rutina", LineaActivacion, FamiliaVerificacion, false, true},
	{"VEXT", "Verificación externa", LineaActivacion, FamiliaVerificacion, false, true},
	// Retencion
	{"DESX", "Desconexión", LineaRetencion, FamiliaCartera, false, false},
	{"RECX", "Reconexión", LineaRetencion, FamiliaCartera, false, true},
	{"ALRT", "Emergencia", LineaRetencion, FamiliaEmergencia, false, true},
	{"NOAL", "Normalización Emergencias", LineaRetencion, FamiliaNormalizacion, false, true},
	{"NOTE", "Normalización Telemedidas", LineaRetencion, FamiliaNormalizacion, false, true},
	{"PQRS", "PQR", LineaRetencion, FamiliaVerificacion, false, true},
	{"VERF", "Verificación consumo", LineaRetencion, FamiliaVerificacion, false, true},
	{"VICO", "Visita conjunta", LineaRetencion, FamiliaVerificacion, false, true},
	{"INFR", "Inspección de frontera", LineaRetencion, FamiliaVerificacion, false, true},
	{"RDEP", "Retiro de Equipos", LineaRetencion, FamiliaRetiro, false, true},
	{"INPE", "Instalación de planta eléctrica", LineaRetencion, FamiliaEjecucion, false, true},
	{"REPE", "Retiro de planta eléctrica", LineaRetencion, FamiliaRetiro, false, true},
	{"TLIS", "Toma de Lectura In Situ", LineaRetencion, FamiliaVerificacion, false, true},
}

// TipoOTPorCodigo busca un tipo de OT por su codigo (sin distinguir mayusculas).
func TipoOTPorCodigo(codigo string) (TipoOT, bool) {
	codigo = strings.ToUpper(strings.TrimSpace(codigo))
	for _, t := range TiposOT {
		if t.Codigo == codigo {
			return t, true
		}
	}
	return TipoOT{}, false
}

// TipoOTDeTitulo saca el tipo de OT del titulo, que empieza con el codigo
// (ej. "VIPE_44339_3986E7" o "PREB_CO0100003376_1350990039_1").
func TipoOTDeTitulo(titulo string) (TipoOT, bool) {
	codigo, _, _ := strings.Cut(strings.TrimSpace(titulo), "_")
	return TipoOTPorCodigo(codigo)
}
