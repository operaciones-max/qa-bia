import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = (import.meta.env.VITE_SUPABASE_URL ?? "").replace(/\/rest\/v1\/?$/, "").replace(/\/$/, "");
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";

/** null si falta configurar frontend/.env.local (la app muestra un aviso). */
export const supabase: SupabaseClient | null = url && anonKey ? createClient(url, anonKey) : null;

export function clienteSupabase(): SupabaseClient {
  if (!supabase) throw new Error("Supabase no está configurado");
  return supabase;
}
