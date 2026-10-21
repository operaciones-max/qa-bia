import { FILTROS_VACIOS, type FiltrosActas } from "../lib/filtros.ts";
import { Boton } from "./ui.tsx";

const ESTILO_CAMPO =
  "w-full rounded-md border-0 bg-white px-2.5 py-1.5 text-sm text-slate-900 ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-slate-600";

interface Props {
  filtros: FiltrosActas;
  opciones: { tiposServicio: string[]; planners: string[] };
  onCambio: (filtros: FiltrosActas) => void;
}

export function BarraFiltros({ filtros, opciones, onCambio }: Props) {
  const cambiar = <K extends keyof FiltrosActas>(clave: K, valor: FiltrosActas[K]) =>
    onCambio({ ...filtros, [clave]: valor });

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="block lg:col-span-2">
          <span className="text-xs text-slate-500">Buscar (OT, código CO, técnico, empresa)</span>
          <input
            type="search"
            className={ESTILO_CAMPO}
            value={filtros.busqueda}
            onChange={(e) => cambiar("busqueda", e.target.value)}
            placeholder="Ej: VIPE_44339 o CO0800006765"
          />
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Tipo de servicio</span>
          <select className={ESTILO_CAMPO} value={filtros.tipoServicio} onChange={(e) => cambiar("tipoServicio", e.target.value)}>
            <option value="">Todos</option>
            {opciones.tiposServicio.map((t) => <option key={t}>{t}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Planner</span>
          <select className={ESTILO_CAMPO} value={filtros.planner} onChange={(e) => cambiar("planner", e.target.value)}>
            <option value="">Todos</option>
            {opciones.planners.map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Estado OT</span>
          <select
            className={ESTILO_CAMPO}
            value={filtros.estadoOt}
            onChange={(e) => cambiar("estadoOt", e.target.value as FiltrosActas["estadoOt"])}
          >
            <option value="">Todos</option>
            <option value="EXITOSA">Exitosa</option>
            <option value="FALLIDA">Fallida</option>
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Track QA</span>
          <select
            className={ESTILO_CAMPO}
            value={filtros.qaTrack}
            onChange={(e) => cambiar("qaTrack", e.target.value as FiltrosActas["qaTrack"])}
          >
            <option value="">Todos</option>
            <option value="Activacion">Activación</option>
            <option value="Retencion">Retención</option>
            <option value="Energy Solutions">Energy Solutions</option>
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">Revisión</span>
          <select
            className={ESTILO_CAMPO}
            value={filtros.revision}
            onChange={(e) => cambiar("revision", e.target.value as FiltrosActas["revision"])}
          >
            <option value="">Todas</option>
            <option value="pendiente">Sin revisar</option>
            <option value="EXITOSA">Aprobada como exitosa</option>
            <option value="FALLIDA">Marcada como fallida</option>
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="block">
            <span className="text-xs text-slate-500">Ejecutada desde</span>
            <input type="date" className={ESTILO_CAMPO} value={filtros.desde} onChange={(e) => cambiar("desde", e.target.value)} />
          </label>
          <label className="block">
            <span className="text-xs text-slate-500">Hasta</span>
            <input type="date" className={ESTILO_CAMPO} value={filtros.hasta} onChange={(e) => cambiar("hasta", e.target.value)} />
          </label>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={filtros.conDiscrepancias}
            onChange={(e) => cambiar("conDiscrepancias", e.target.checked)}
          />
          Solo con discrepancias (WMS o factura anterior)
        </label>
        <Boton onClick={() => onCambio(FILTROS_VACIOS)}>Limpiar filtros</Boton>
      </div>
    </div>
  );
}
