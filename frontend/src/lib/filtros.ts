// Traduce los filtros de la pantalla a condiciones de PostgREST.
// Es una funcion pura (sin Supabase) para poder probarla.

import type { EstadoOT, QaTrack } from "../types/acta.ts";

export interface FiltrosActas {
  busqueda: string;
  tipoServicio: string;
  estadoOt: "" | EstadoOT;
  qaTrack: "" | QaTrack;
  planner: string;
  revision: "" | "pendiente" | EstadoOT;
  desde: string; // YYYY-MM-DD sobre fecha_ejecucion
  hasta: string;
  conDiscrepancias: boolean;
}

export const FILTROS_VACIOS: FiltrosActas = {
  busqueda: "",
  tipoServicio: "",
  estadoOt: "",
  qaTrack: "",
  planner: "",
  revision: "",
  desde: "",
  hasta: "",
  conDiscrepancias: false,
};

// Los filtros viajan en la URL (?estadoOt=FALLIDA&p=2) para que se puedan
// compartir y se mantengan al volver del detalle.

export function filtrosDesdeUrl(params: URLSearchParams): { filtros: FiltrosActas; pagina: number } {
  const texto = (clave: keyof FiltrosActas) => params.get(clave) ?? "";
  const filtros: FiltrosActas = {
    busqueda: texto("busqueda"),
    tipoServicio: texto("tipoServicio"),
    estadoOt: texto("estadoOt") as FiltrosActas["estadoOt"],
    qaTrack: texto("qaTrack") as FiltrosActas["qaTrack"],
    planner: texto("planner"),
    revision: texto("revision") as FiltrosActas["revision"],
    desde: texto("desde"),
    hasta: texto("hasta"),
    conDiscrepancias: params.get("conDiscrepancias") === "1",
  };
  const pagina = Math.max(0, Number.parseInt(params.get("p") ?? "1", 10) - 1 || 0);
  return { filtros, pagina };
}

export function filtrosAUrl(filtros: FiltrosActas, pagina: number): URLSearchParams {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor === true) params.set(clave, "1");
    else if (typeof valor === "string" && valor) params.set(clave, valor);
  }
  if (pagina > 0) params.set("p", String(pagina + 1));
  return params;
}

export type Condicion =
  | { op: "eq"; columna: string; valor: string | boolean }
  | { op: "is"; columna: string; valor: null }
  | { op: "gte" | "lte"; columna: string; valor: string }
  | { op: "or"; expresion: string };

/** Discrepancias que el revisor tiene que mirar: WMS o factura anterior no coinciden. */
export const EXPRESION_DISCREPANCIAS = [
  "medidor_coincide_wms.eq.false",
  "tcs_coinciden_wms.eq.false",
  "tps_coinciden_wms.eq.false",
  "medidor_coincide_factura_anterior.eq.false",
].join(",");

/** Quita los caracteres que rompen la sintaxis de un filtro `or` de PostgREST. */
export function limpiarBusqueda(texto: string): string {
  return texto.replace(/[,()%*\\"]/g, " ").trim();
}

export function construirCondiciones(f: FiltrosActas): Condicion[] {
  const condiciones: Condicion[] = [];

  const busqueda = limpiarBusqueda(f.busqueda);
  if (busqueda) {
    const patron = `*${busqueda}*`;
    condiciones.push({
      op: "or",
      expresion: ["ot_nombre", "internal_bia_code", "tecnico_nombre", "empresa"]
        .map((c) => `${c}.ilike.${patron}`)
        .join(","),
    });
  }
  if (f.tipoServicio) condiciones.push({ op: "eq", columna: "tipo_servicio", valor: f.tipoServicio });
  if (f.estadoOt) condiciones.push({ op: "eq", columna: "estado_ot", valor: f.estadoOt });
  if (f.qaTrack) condiciones.push({ op: "eq", columna: "qa_track", valor: f.qaTrack });
  if (f.planner) condiciones.push({ op: "eq", columna: "planner", valor: f.planner });

  if (f.revision === "pendiente") {
    condiciones.push({ op: "is", columna: "revision_resultado", valor: null });
  } else if (f.revision) {
    condiciones.push({ op: "eq", columna: "revision_resultado", valor: f.revision });
  }

  if (f.desde) condiciones.push({ op: "gte", columna: "fecha_ejecucion", valor: f.desde });
  if (f.hasta) condiciones.push({ op: "lte", columna: "fecha_ejecucion", valor: `${f.hasta} 23:59:59` });

  if (f.conDiscrepancias) condiciones.push({ op: "or", expresion: EXPRESION_DISCREPANCIAS });

  return condiciones;
}
