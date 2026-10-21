import { useState, type FormEvent } from "react";
import { clienteSupabase } from "../lib/supabase.ts";
import { Boton, MensajeError } from "../components/ui.tsx";

export function Login() {
  const [email, setEmail] = useState("");
  const [clave, setClave] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function entrar(e: FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    const { error } = await clienteSupabase().auth.signInWithPassword({ email, password: clave });
    if (error) setError(error.message === "Invalid login credentials" ? "Correo o contraseña incorrectos." : error.message);
    setEnviando(false);
  }

  const estiloCampo =
    "mt-1 w-full rounded-md border-0 px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-slate-600";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={entrar} className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6">
        <h1 className="text-lg font-semibold text-slate-900">QA BIA</h1>
        <p className="mb-5 text-sm text-slate-500">Revisión de actas de campo</p>
        <label className="block">
          <span className="text-xs text-slate-600">Correo</span>
          <input type="email" required autoComplete="email" className={estiloCampo} value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="mt-3 block">
          <span className="text-xs text-slate-600">Contraseña</span>
          <input type="password" required autoComplete="current-password" className={estiloCampo} value={clave} onChange={(e) => setClave(e.target.value)} />
        </label>
        {error && <div className="mt-3"><MensajeError error={error} /></div>}
        <Boton type="submit" variante="primario" disabled={enviando} className="mt-5 w-full py-2">
          {enviando ? "Entrando…" : "Entrar"}
        </Boton>
      </form>
    </div>
  );
}
