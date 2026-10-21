// Formateo de valores para mostrar. Funciones puras.

import type { ActaQA, EstadoOT, FacturaEstado } from "../types/acta.ts";

export type Tono = "verde" | "rojo" | "ambar" | "azul" | "gris";

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** "2026-05-20 14:03:00" o ISO -> "20 may 2026" (con hora si conHora). */
export function formatearFecha(valor: string | null | undefined, conHora = false): string {
  if (!valor) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(valor);
  if (!m) return valor;
  const [, anio, mes, dia, hh, mm] = m;
  const fecha = `${Number(dia)} ${MESES[Number(mes) - 1]} ${anio}`;
  return conHora && hh ? `${fecha} ${hh}:${mm}` : fecha;
}

export function textoOVacio(valor: unknown): string {
  if (valor === null || valor === undefined) return "—";
  const s = String(valor).trim();
  return s === "" || s === "null" || s === "None" ? "—" : s;
}

export function textoSiNo(valor: boolean | null | undefined): string {
  if (valor === true) return "Sí";
  if (valor === false) return "No";
  return "—";
}

/** Coincidencias (WMS, factura): true = verde, false = rojo, null = no aplica. */
export function tonoCoincidencia(valor: boolean | null | undefined): Tono {
  if (valor === true) return "verde";
  if (valor === false) return "rojo";
  return "gris";
}

export function textoCoincidencia(valor: boolean | null | undefined): string {
  if (valor === true) return "Coincide";
  if (valor === false) return "No coincide";
  return "No aplica";
}

export function tonoEstado(estado: EstadoOT | null | undefined): Tono {
  if (estado === "EXITOSA") return "verde";
  if (estado === "FALLIDA") return "rojo";
  return "gris";
}

/** El veredicto del revisor manda sobre el estado que viene de App Ops. */
export function estadoFinal(acta: Pick<ActaQA, "estado_ot" | "revision_resultado">): EstadoOT | null {
  return acta.revision_resultado ?? acta.estado_ot;
}

const ETIQUETAS_FACTURA: Record<FacturaEstado, string> = {
  ok: "Leída",
  ok_sin_serial: "Leída, sin serial",
  borrosa: "No se pudo leer",
  no_disponible: "Sin factura",
};

export function textoFactura(estado: FacturaEstado | null | undefined): string {
  return estado ? ETIQUETAS_FACTURA[estado] ?? estado : "—";
}

/** true si alguna comparacion automatica dio false. */
export function tieneDiscrepancias(
  acta: Pick<ActaQA, "medidor_coincide_wms" | "tcs_coinciden_wms" | "tps_coinciden_wms" | "medidor_coincide_factura_anterior">,
): boolean {
  return [
    acta.medidor_coincide_wms,
    acta.tcs_coinciden_wms,
    acta.tps_coinciden_wms,
    acta.medidor_coincide_factura_anterior,
  ].some((v) => v === false);
}
