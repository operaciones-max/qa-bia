// Package web es el dashboard de revision de actas: un servidor HTTP con
// plantillas HTML que lee y escribe la tabla actas_qa de Supabase con el token
// del usuario logueado (asi aplican las politicas RLS).
package web

// ActaQA es una fila de la tabla actas_qa. Es el contrato con el backend:
// ver docs/contrato-supabase.md. Los numeros se dejan como `any` porque la IA
// puede devolverlos como texto.
type ActaQA struct {
	// Identificacion
	OTID            string  `json:"ot_id"`
	OTNombre        *string `json:"ot_nombre"`
	ProcesadoEn     *string `json:"procesado_en"`
	TipoServicio    *string `json:"tipo_servicio"`
	FechaEjecucion  *string `json:"fecha_ejecucion"`
	InternalBIACode *string `json:"internal_bia_code"`
	ContractID      *string `json:"contract_id"`
	ORNorm          *string `json:"or_norm"`
	Planner         *string `json:"planner"`
	Empresa         *string `json:"empresa"`
	Direccion       *string `json:"direccion"`
	PDFURL          *string `json:"pdf_url"`

	// Resultado
	EstadoOT                *string  `json:"estado_ot"`
	QATrack                 *string  `json:"qa_track"`
	TipoMedida              *string  `json:"tipo_medida"`
	FactorMedida            *string  `json:"factor_medida"`
	ORFirma                 *string  `json:"or_firma"`
	ValidacionCoherente     *string  `json:"validacion_coherente"`
	ErroresQA               []string `json:"errores_qa"`
	AlertasQA               []string `json:"alertas_qa"`
	TipificacionCausaRaiz   *string  `json:"tipificacion_causa_raiz"`
	TipificacionResponsable *string  `json:"tipificacion_responsable"`

	// Tecnico
	TecnicoNombre     *string `json:"tecnico_nombre"`
	TecnicoEmpresa    *string `json:"tecnico_empresa"`
	ContratistaNombre *string `json:"contratista_nombre"`

	// Medidores y equipos
	MedidorEncontradoSerie  *string `json:"medidor_encontrado_serie"`
	MedidorEncontradoMarca  *string `json:"medidor_encontrado_marca"`
	MedidorInstaladoSerie   *string `json:"medidor_instalado_serie"`
	MedidorInstaladoMarca   *string `json:"medidor_instalado_marca"`
	SellosMedidorEncontrado any     `json:"sellos_medidor_encontrado"`
	SellosMedidorInstalado  any     `json:"sellos_medidor_instalado"`
	SellosTCsEncontrados    any     `json:"sellos_tcs_encontrados"`
	SellosTCsInstalados     any     `json:"sellos_tcs_instalados"`
	TieneTCs                *bool   `json:"tiene_tcs"`
	TieneTPs                *bool   `json:"tiene_tps"`
	TieneTelemedida         *bool   `json:"tiene_telemedida"`
	TieneDiagramaUnifilar   *bool   `json:"tiene_diagrama_unifilar"`

	// WMS
	WMSAsignado             *bool       `json:"wms_asignado"`
	WMSMedidorSerial        *string     `json:"wms_medidor_serial"`
	WMSMedidorMarca         *string     `json:"wms_medidor_marca"`
	WMSCompleto             *EquiposWMS `json:"wms_completo"`
	MedidorCoincideWMS      *bool       `json:"medidor_coincide_wms"`
	TCsCoincidenWMS         *bool       `json:"tcs_coinciden_wms"`
	TPsCoincidenWMS         *bool       `json:"tps_coinciden_wms"`
	WMSMarcaCoincideAlcance *bool       `json:"wms_marca_coincide_alcance"`

	// Factura anterior
	SerialMedidorFacturaAnterior   *string `json:"serial_medidor_factura_anterior"`
	MedidorCoincideFacturaAnterior *bool   `json:"medidor_coincide_factura_anterior"`
	FacturaAnteriorExpress         *bool   `json:"factura_anterior_express"`
	FacturaAnteriorEstado          *string `json:"factura_anterior_estado"`

	// Cierre en App Ops (lo recalcula el backend en cada corrida)
	EstadoAppOps   *string `json:"estado_app_ops"`
	EstadoRevision *string `json:"estado_revision"`

	// Alcance de ingenieria
	TieneAlcance          *bool   `json:"tiene_alcance"`
	AlcanceViable         *string `json:"alcance_viable"`
	AlcanceMedidaInstalar *string `json:"alcance_medida_instalar"`

	ResultadoQACompleto map[string]any `json:"resultado_qa_completo"`

	// Revision humana: solo la escribe el frontend
	RevisionResultado  *string `json:"revision_resultado"`
	RevisionComentario *string `json:"revision_comentario"`
	RevisadoPor        *string `json:"revisado_por"`
	RevisadoEn         *string `json:"revisado_en"`
}

// EquipoWMS es un equipo asignado en WMS.
type EquipoWMS struct {
	Serial string `json:"serial"`
	Marca  string `json:"marca"`
	Estado string `json:"estado"`
}

// EquiposWMS son los equipos de un codigo CO en WMS.
type EquiposWMS struct {
	Medidor *EquipoWMS  `json:"medidor"`
	TCs     []EquipoWMS `json:"tcs"`
	TPs     []EquipoWMS `json:"tps"`
}

// ColumnasResumen son las columnas que trae el listado (sin los JSON pesados).
const ColumnasResumen = "ot_id,ot_nombre,tipo_servicio,fecha_ejecucion,internal_bia_code,planner,estado_ot,qa_track," +
	"tecnico_nombre,medidor_coincide_wms,tcs_coinciden_wms,tps_coinciden_wms,medidor_coincide_factura_anterior," +
	"errores_qa,alertas_qa,revision_resultado"
