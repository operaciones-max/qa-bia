// Acceso a la tabla actas_qa. Toda la comunicacion con Supabase pasa por aqui.

import { clienteSupabase } from "./supabase.ts";
import {
  construirCondiciones, EXPRESION_DISCREPANCIAS, type Condicion, type FiltrosActas,
} from "./filtros.ts";
import { COLUMNAS_RESUMEN, type ActaQA, type ActaResumen, type EstadoOT } from "../types/acta.ts";

const TABLA = "actas_qa";
export const TAM_PAGINA = 50;

// Los metodos del query builder de supabase-js que usan las condiciones.
interface ConsultaFiltrable {
  eq(columna: string, valor: unknown): this;
  is(columna: string, valor: null): this;
  gte(columna: string, valor: unknown): this;
  lte(columna: string, valor: unknown): this;
  or(expresion: string): this;
}

function aplicarCondiciones<Q extends ConsultaFiltrable>(consulta: Q, condiciones: Condicion[]): Q {
  let q = consulta;
  for (const c of condiciones) {
    if (c.op === "or") q = q.or(c.expresion);
    else if (c.op === "is") q = q.is(c.columna, null);
    else q = q[c.op](c.columna, c.valor);
  }
  return q;
}

export async function listarActas(
  filtros: FiltrosActas,
  pagina: number,
): Promise<{ filas: ActaResumen[]; total: number }> {
  const desde = pagina * TAM_PAGINA;
  const consulta = clienteSupabase()
    .from(TABLA)
    .select(COLUMNAS_RESUMEN.join(","), { count: "exact" });
  const { data, count, error } = await aplicarCondiciones(consulta, construirCondiciones(filtros))
    .order("fecha_ejecucion", { ascending: false, nullsFirst: false })
    .order("ot_id")
    .range(desde, desde + TAM_PAGINA - 1);
  if (error) throw new Error(error.message);
  return { filas: (data ?? []) as unknown as ActaResumen[], total: count ?? 0 };
}

export interface Indicadores {
  total: number;
  exitosas: number;
  fallidas: number;
  conDiscrepancias: number;
  sinRevisar: number;
}

async function contar(condiciones: Condicion[]): Promise<number> {
  const consulta = clienteSupabase().from(TABLA).select("ot_id", { count: "exact", head: true });
  const { count, error } = await aplicarCondiciones(consulta, condiciones);
  if (error) throw new Error(error.message);
  return count ?? 0;
}

/** Totales sobre los mismos filtros de la tabla. */
export async function calcularIndicadores(filtros: FiltrosActas): Promise<Indicadores> {
  const base = construirCondiciones(filtros);
  const [total, exitosas, fallidas, conDiscrepancias, sinRevisar] = await Promise.all([
    contar(base),
    contar([...base, { op: "eq", columna: "estado_ot", valor: "EXITOSA" }]),
    contar([...base, { op: "eq", columna: "estado_ot", valor: "FALLIDA" }]),
    contar([...base, { op: "or", expresion: EXPRESION_DISCREPANCIAS }]),
    contar([...base, { op: "is", columna: "revision_resultado", valor: null }]),
  ]);
  return { total, exitosas, fallidas, conDiscrepancias, sinRevisar };
}

/** Valores distintos para los desplegables de filtro. */
export async function opcionesDeFiltro(): Promise<{ tiposServicio: string[]; planners: string[] }> {
  const { data, error } = await clienteSupabase()
    .from(TABLA)
    .select("tipo_servicio,planner")
    .limit(5000);
  if (error) throw new Error(error.message);
  const filas = (data ?? []) as { tipo_servicio: string | null; planner: string | null }[];
  const distintos = (valores: (string | null)[]) =>
    [...new Set(valores.filter((v): v is string => !!v))].sort((a, b) => a.localeCompare(b, "es"));
  return {
    tiposServicio: distintos(filas.map((f) => f.tipo_servicio)),
    planners: distintos(filas.map((f) => f.planner)),
  };
}

export async function obtenerActa(otId: string): Promise<ActaQA | null> {
  const { data, error } = await clienteSupabase().from(TABLA).select("*").eq("ot_id", otId).maybeSingle();
  if (error) throw new Error(error.message);
  return data as ActaQA | null;
}

export interface Revision {
  resultado: EstadoOT | null;
  comentario: string;
}

/** Guarda el veredicto del revisor. resultado=null borra la revision. */
export async function guardarRevision(otId: string, revision: Revision): Promise<ActaQA> {
  const cliente = clienteSupabase();
  const { data: sesion } = await cliente.auth.getUser();
  const cambios = revision.resultado
    ? {
        revision_resultado: revision.resultado,
        revision_comentario: revision.comentario.trim() || null,
        revisado_por: sesion.user?.email ?? null,
        revisado_en: new Date().toISOString(),
      }
    : { revision_resultado: null, revision_comentario: null, revisado_por: null, revisado_en: null };
  const { data, error } = await cliente.from(TABLA).update(cambios).eq("ot_id", otId).select("*").single();
  if (error) throw new Error(error.message);
  return data as ActaQA;
}
