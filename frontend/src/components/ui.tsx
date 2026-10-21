// Piezas de interfaz reutilizables.

import type { ReactNode } from "react";
import type { Tono } from "../lib/formato.ts";

const TONOS: Record<Tono, string> = {
  verde: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  rojo: "bg-rose-50 text-rose-700 ring-rose-600/20",
  ambar: "bg-amber-50 text-amber-800 ring-amber-600/20",
  azul: "bg-sky-50 text-sky-700 ring-sky-600/20",
  gris: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export function Insignia({ tono, children }: { tono: Tono; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap ${TONOS[tono]}`}>
      {children}
    </span>
  );
}

export function Seccion({ titulo, children, accion }: { titulo: string; children: ReactNode; accion?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <header className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-800">{titulo}</h2>
        {accion}
      </header>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

/** Lista de pares etiqueta / valor. */
export function Campos({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">{children}</dl>;
}

export function Campo({ etiqueta, children }: { etiqueta: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-slate-500">{etiqueta}</dt>
      <dd className="break-words text-sm text-slate-900">{children}</dd>
    </div>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return <p className="py-8 text-center text-sm text-slate-500">{texto}</p>;
}

export function MensajeError({ error }: { error: string }) {
  return (
    <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
      {error}
    </div>
  );
}

export function Boton({
  children, variante = "secundario", ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario" | "peligro" }) {
  const estilos = {
    primario: "bg-slate-900 text-white hover:bg-slate-700",
    secundario: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    peligro: "bg-rose-600 text-white hover:bg-rose-500",
  }[variante];
  return (
    <button
      {...props}
      className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50 ${estilos} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}
