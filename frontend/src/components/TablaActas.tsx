import { Link } from "react-router";
import type { ActaResumen } from "../types/acta.ts";
import {
  estadoFinal, formatearFecha, textoOVacio, tieneDiscrepancias, tonoCoincidencia, tonoEstado,
} from "../lib/formato.ts";
import { Insignia } from "./ui.tsx";

function Coincidencia({ valor }: { valor: boolean | null }) {
  if (valor === null) return <span className="text-slate-400">—</span>;
  return <Insignia tono={tonoCoincidencia(valor)}>{valor ? "OK" : "No"}</Insignia>;
}

export function TablaActas({ filas, busquedaActual }: { filas: ActaResumen[]; busquedaActual: string }) {
  if (filas.length === 0) {
    return <p className="py-10 text-center text-sm text-slate-500">No hay actas con estos filtros.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-medium text-slate-500">
          <tr>
            <th className="px-3 py-2">OT</th>
            <th className="px-3 py-2">Tipo</th>
            <th className="px-3 py-2">Ejecución</th>
            <th className="px-3 py-2">Técnico</th>
            <th className="px-3 py-2">Estado</th>
            <th className="px-3 py-2">Medidor WMS</th>
            <th className="px-3 py-2">Factura ant.</th>
            <th className="px-3 py-2 text-right">Errores</th>
            <th className="px-3 py-2">Revisión</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {filas.map((a) => {
            const estado = estadoFinal(a);
            return (
              <tr key={a.ot_id} className={`hover:bg-slate-50 ${tieneDiscrepancias(a) ? "bg-amber-50/40" : ""}`}>
                <td className="px-3 py-2">
                  <Link
                    to={{ pathname: `/actas/${encodeURIComponent(a.ot_id)}`, search: busquedaActual }}
                    className="font-medium text-slate-900 hover:underline"
                  >
                    {textoOVacio(a.ot_nombre)}
                  </Link>
                  <div className="text-xs text-slate-500">{textoOVacio(a.internal_bia_code)}</div>
                </td>
                <td className="px-3 py-2 text-slate-700">{textoOVacio(a.tipo_servicio)}</td>
                <td className="whitespace-nowrap px-3 py-2 text-slate-700">{formatearFecha(a.fecha_ejecucion)}</td>
                <td className="px-3 py-2 text-slate-700">{textoOVacio(a.tecnico_nombre)}</td>
                <td className="px-3 py-2">
                  <Insignia tono={tonoEstado(estado)}>{textoOVacio(estado)}</Insignia>
                </td>
                <td className="px-3 py-2"><Coincidencia valor={a.medidor_coincide_wms} /></td>
                <td className="px-3 py-2"><Coincidencia valor={a.medidor_coincide_factura_anterior} /></td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-700">{a.errores_qa?.length ?? 0}</td>
                <td className="px-3 py-2">
                  {a.revision_resultado ? (
                    <Insignia tono="azul">Revisada</Insignia>
                  ) : (
                    <span className="text-xs text-slate-400">Pendiente</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
