import type { Indicadores as Datos } from "../lib/actas.ts";

const TARJETAS: { clave: keyof Datos; etiqueta: string; color: string }[] = [
  { clave: "total", etiqueta: "Actas", color: "text-slate-900" },
  { clave: "exitosas", etiqueta: "Exitosas", color: "text-emerald-700" },
  { clave: "fallidas", etiqueta: "Fallidas", color: "text-rose-700" },
  { clave: "conDiscrepancias", etiqueta: "Con discrepancias", color: "text-amber-700" },
  { clave: "sinRevisar", etiqueta: "Sin revisar", color: "text-sky-700" },
];

export function Indicadores({ datos }: { datos: Datos | null }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {TARJETAS.map((t) => (
        <div key={t.clave} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <p className="text-xs text-slate-500">{t.etiqueta}</p>
          <p className={`mt-1 text-2xl font-semibold tabular-nums ${t.color}`}>
            {datos ? datos[t.clave].toLocaleString("es-CO") : "—"}
          </p>
        </div>
      ))}
    </div>
  );
}
