import { HashRouter, Route, Routes } from "react-router";
import { Layout } from "./components/Layout.tsx";
import { Cargando, MensajeError } from "./components/ui.tsx";
import { useSesion } from "./hooks/useSesion.ts";
import { supabase } from "./lib/supabase.ts";
import { DetalleActa } from "./pages/DetalleActa.tsx";
import { ListaActas } from "./pages/ListaActas.tsx";
import { Login } from "./pages/Login.tsx";

export function App() {
  const sesion = useSesion();

  if (!supabase) {
    return (
      <Layout>
        <MensajeError error="Falta configurar Supabase: copiar frontend/.env.example a frontend/.env.local y completar VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY." />
      </Layout>
    );
  }
  if (sesion === undefined) return <Cargando />;
  if (sesion === null) return <Login />;

  // HashRouter: las rutas funcionan en cualquier hosting estatico sin configuracion.
  return (
    <HashRouter>
      <Layout email={sesion.user.email}>
        <Routes>
          <Route path="/" element={<ListaActas />} />
          <Route path="/actas/:otId" element={<DetalleActa />} />
          <Route path="*" element={<MensajeError error="Página no encontrada." />} />
        </Routes>
      </Layout>
    </HashRouter>
  );
}
