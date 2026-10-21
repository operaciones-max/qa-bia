import type { ReactNode } from "react";
import { Link } from "react-router";
import { supabase } from "../lib/supabase.ts";

export function Layout({ email, children }: { email?: string; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="text-base font-semibold text-slate-900">
            QA BIA <span className="font-normal text-slate-500">· Revisión de actas</span>
          </Link>
          {email && (
            <div className="flex items-center gap-3 text-sm">
              <span className="hidden text-slate-500 sm:inline">{email}</span>
              <button className="text-slate-700 underline-offset-2 hover:underline" onClick={() => supabase?.auth.signOut()}>
                Salir
              </button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
