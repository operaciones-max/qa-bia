import test from "node:test";
import assert from "node:assert/strict";
import {
  construirCondiciones, EXPRESION_DISCREPANCIAS, FILTROS_VACIOS, filtrosAUrl, filtrosDesdeUrl, limpiarBusqueda,
} from "./filtros.ts";

test("sin filtros no hay condiciones", () => {
  assert.deepEqual(construirCondiciones(FILTROS_VACIOS), []);
});

test("busqueda en varias columnas, sin caracteres que rompan PostgREST", () => {
  assert.equal(limpiarBusqueda(" VIPE_1,(x)% "), "VIPE_1  x");
  const [c] = construirCondiciones({ ...FILTROS_VACIOS, busqueda: "co080" });
  assert.deepEqual(c, {
    op: "or",
    expresion: "ot_nombre.ilike.*co080*,internal_bia_code.ilike.*co080*,tecnico_nombre.ilike.*co080*,empresa.ilike.*co080*",
  });
});

test("revision pendiente filtra por null y el resto por igualdad", () => {
  assert.deepEqual(construirCondiciones({ ...FILTROS_VACIOS, revision: "pendiente" }), [
    { op: "is", columna: "revision_resultado", valor: null },
  ]);
  assert.deepEqual(construirCondiciones({ ...FILTROS_VACIOS, revision: "FALLIDA" }), [
    { op: "eq", columna: "revision_resultado", valor: "FALLIDA" },
  ]);
});

test("rango de fechas incluye todo el dia final y discrepancias usa or", () => {
  const condiciones = construirCondiciones({
    ...FILTROS_VACIOS, desde: "2026-05-01", hasta: "2026-05-31", conDiscrepancias: true, estadoOt: "EXITOSA",
  });
  assert.deepEqual(condiciones, [
    { op: "eq", columna: "estado_ot", valor: "EXITOSA" },
    { op: "gte", columna: "fecha_ejecucion", valor: "2026-05-01" },
    { op: "lte", columna: "fecha_ejecucion", valor: "2026-05-31 23:59:59" },
    { op: "or", expresion: EXPRESION_DISCREPANCIAS },
  ]);
});

test("filtros ida y vuelta por la URL", () => {
  const filtros = { ...FILTROS_VACIOS, planner: "Dinovi Sanchez", conDiscrepancias: true, qaTrack: "Retencion" as const };
  const params = filtrosAUrl(filtros, 2);
  assert.equal(params.toString(), "qaTrack=Retencion&planner=Dinovi+Sanchez&conDiscrepancias=1&p=3");
  assert.deepEqual(filtrosDesdeUrl(params), { filtros, pagina: 2 });
  assert.deepEqual(filtrosDesdeUrl(new URLSearchParams("p=abc")), { filtros: FILTROS_VACIOS, pagina: 0 });
});
