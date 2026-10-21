// Fila de la tabla actas_qa de Supabase.
// Es el contrato con el backend: ver docs/contrato-supabase.md.

export type EstadoOT = "EXITOSA" | "FALLIDA";
export type QaTrack = "Activacion" | "Retencion" | "Energy Solutions";
export type FacturaEstado = "ok" | "ok_sin_serial" | "borrosa" | "no_disponible";

export interface EquipoWms {
  serial: string;
  marca: string;
  estado: string;
}

export interface TipificacionFalla {
  causa_raiz?: string | null;
  responsable?: string | null;
  detalle?: string | null;
  mejora?: string | null;
}

/** Respuesta completa de la IA despues de las validaciones del backend. */
export interface ResultadoQA {
  observacion_tecnico_verbatim?: string | null;
  observaciones_tecnicas?: string | null;
  tipificacion_falla?: TipificacionFalla | null;
  tcs_instalados?: { seriales?: string[] } | null;
  tps_instalados?: { seriales?: string[] } | null;
  fotos_medidor?: number | null;
  fotos_tcs?: number | null;
  fotos_tps?: number | null;
  [campo: string]: unknown;
}

export interface ActaQA {
  // Identificacion
  ot_id: string;
  ot_nombre: string | null;
  procesado_en: string | null;
  tipo_servicio: string | null;
  fecha_ejecucion: string | null;
  internal_bia_code: string | null;
  contract_id: string | null;
  or_norm: string | null;
  planner: string | null;
  empresa: string | null;
  direccion: string | null;
  pdf_url: string | null;

  // Resultado
  estado_ot: EstadoOT | null;
  qa_track: QaTrack | null;
  tipo_medida: string | null;
  factor_medida: string | null;
  or_firma: "SI" | "NO" | null;
  validacion_coherente: string | null;
  errores_qa: string[] | null;
  alertas_qa: string[] | null;
  tipificacion_causa_raiz: string | null;
  tipificacion_responsable: string | null;

  // Tecnico
  tecnico_nombre: string | null;
  tecnico_empresa: "BIA" | "CONTRATISTA" | null;
  contratista_nombre: string | null;

  // Medidores y equipos
  medidor_encontrado_serie: string | null;
  medidor_encontrado_marca: string | null;
  medidor_instalado_serie: string | null;
  medidor_instalado_marca: string | null;
  sellos_medidor_encontrado: number | null;
  sellos_medidor_instalado: number | null;
  sellos_tcs_encontrados: number | null;
  sellos_tcs_instalados: number | null;
  tiene_tcs: boolean | null;
  tiene_tps: boolean | null;
  tiene_telemedida: boolean | null;
  tiene_diagrama_unifilar: boolean | null;

  // WMS
  wms_asignado: boolean | null;
  wms_medidor_serial: string | null;
  wms_medidor_marca: string | null;
  wms_completo: { medidor: EquipoWms | null; tcs: EquipoWms[]; tps: EquipoWms[] } | null;
  medidor_coincide_wms: boolean | null;
  tcs_coinciden_wms: boolean | null;
  tps_coinciden_wms: boolean | null;
  wms_marca_coincide_alcance: boolean | null;

  // Factura anterior
  serial_medidor_factura_anterior: string | null;
  medidor_coincide_factura_anterior: boolean | null;
  factura_anterior_express: boolean | null;
  factura_anterior_estado: FacturaEstado | null;

  // Cierre en App Ops (lo recalcula el backend en cada corrida)
  estado_app_ops: "Exitosa" | "Fallida" | null;
  estado_revision: "pendiente" | "cerrada" | null;

  // Alcance de ingenieria
  tiene_alcance: boolean | null;
  alcance_viable: string | null;
  alcance_medida_instalar: string | null;
  alcance_completo: Record<string, string> | null;

  resultado_qa_completo: ResultadoQA | null;

  // Revision humana: solo la escribe el frontend
  revision_resultado: EstadoOT | null;
  revision_comentario: string | null;
  revisado_por: string | null;
  revisado_en: string | null;
}

/** Columnas que trae la tabla del listado (sin los JSON pesados). */
export const COLUMNAS_RESUMEN = [
  "ot_id", "ot_nombre", "tipo_servicio", "fecha_ejecucion", "internal_bia_code", "planner",
  "estado_ot", "qa_track", "tecnico_nombre", "medidor_coincide_wms", "tcs_coinciden_wms",
  "tps_coinciden_wms", "medidor_coincide_factura_anterior", "errores_qa", "alertas_qa",
  "revision_resultado",
] as const;

export type ActaResumen = Pick<ActaQA, (typeof COLUMNAS_RESUMEN)[number]>;
