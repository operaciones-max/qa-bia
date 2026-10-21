import test from "node:test";
import assert from "node:assert/strict";
import { estadoFinal, formatearFecha, textoFactura, textoOVacio, tieneDiscrepancias, tonoCoincidencia } from "./formato.ts";

test("formatearFecha acepta el formato de Metabase y el ISO", () => {
  assert.equal(formatearFecha("2026-05-20 14:03:00"), "20 may 2026");
  assert.equal(formatearFecha("2026-05-20T14:03:00Z", true), "20 may 2026 14:03");
  assert.equal(formatearFecha(null), "—");
  assert.equal(formatearFecha("ayer"), "ayer");
});

test("textoOVacio trata null, vacio y 'None' como sin dato", () => {
  assert.equal(textoOVacio(null), "—");
  assert.equal(textoOVacio("  "), "—");
  assert.equal(textoOVacio("None"), "—");
  assert.equal(textoOVacio(0), "0");
});

test("el veredicto del revisor manda sobre el estado de App Ops", () => {
  assert.equal(estadoFinal({ estado_ot: "EXITOSA", revision_resultado: null }), "EXITOSA");
  assert.equal(estadoFinal({ estado_ot: "EXITOSA", revision_resultado: "FALLIDA" }), "FALLIDA");
});

test("discrepancias solo cuando alguna comparacion es false", () => {
  const base = {
    medidor_coincide_wms: true, tcs_coinciden_wms: null, tps_coinciden_wms: null, medidor_coincide_factura_anterior: null,
  };
  assert.equal(tieneDiscrepancias(base), false);
  assert.equal(tieneDiscrepancias({ ...base, medidor_coincide_factura_anterior: false }), true);
  assert.equal(tonoCoincidencia(null), "gris");
  assert.equal(textoFactura("ok_sin_serial"), "Leída, sin serial");
});
