import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { BarraFiltros } from "../components/BarraFiltros.tsx";
import { Indicadores } from "../components/Indicadores.tsx";
import { TablaActas } from "../components/TablaActas.tsx";
import { Boton, Cargando, MensajeError } from "../components/ui.tsx";
import {
  calcularIndicadores, listarActas, opcionesDeFiltro, TAM_PAGINA, type Indicadores as DatosIndicadores,
} from "../lib/actas.ts";
import { filtrosAUrl, filtrosDesdeUrl, type FiltrosActas } from "../lib/filtros.ts";
import type { ActaResumen } from "../types/acta.ts";

/** Espera a que el usuario deje de escribir antes de consultar. */
function useDiferido<T>(valor: T, ms = 300): T {
  const [diferido, setDiferido] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setDiferido(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return diferido;
}

export function ListaActas() {
  const [params, setParams] = useSearchParams();
  const { filtros, pagina } = useMemo(() => filtrosDesdeUrl(params), [params]);
  const clave = useDiferido(params.toString());

  const [filas, setFilas] = useState<ActaResumen[] | null>(null);
  const [total, setTotal] = useState(0);
  const [indicadores, setIndicadores] = useState<DatosIndicadores | null>(null);
  const [opciones, setOpciones] = useState({ tiposServicio: [] as string[], planners: [] as string[] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    opcionesDeFiltro().then(setOpciones).catch(() => undefined);
  }, []);

  useEffect(() => {
    let vigente = true;
    const { filtros: f, pagina: p } = filtrosDesdeUrl(new URLSearchParams(clave));
    setError(null);
    Promise.all([listarActas(f, p), calcularIndicadores(f)])
      .then(([lista, ind]) => {
        if (!vigente) return;
        setFilas(lista.filas);
        setTotal(lista.total);
        setIndicadores(ind);
      })
      .catch((e) => vigente && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      vigente = false;
    };
  }, [clave]);

  const cambiarFiltros = (nuevos: FiltrosActas) => setParams(filtrosAUrl(nuevos, 0), { replace: true });
  const irAPagina = (p: number) => setParams(filtrosAUrl(filtros, p));
  const paginas = Math.max(1, Math.ceil(total / TAM_PAGINA));

  return (
    <div className="space-y-4">
      <Indicadores datos={indicadores} />
      <BarraFiltros filtros={filtros} opciones={opciones} onCambio={cambiarFiltros} />
      {error && <MensajeError error={`No se pudieron cargar las actas: ${error}`} />}
      {filas === null && !error ? <Cargando /> : filas && <TablaActas filas={filas} busquedaActual={`?${params}`} />}
      {total > TAM_PAGINA && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>
            Página {pagina + 1} de {paginas} · {total.toLocaleString("es-CO")} actas
          </span>
          <div className="flex gap-2">
            <Boton disabled={pagina === 0} onClick={() => irAPagina(pagina - 1)}>Anterior</Boton>
            <Boton disabled={pagina + 1 >= paginas} onClick={() => irAPagina(pagina + 1)}>Siguiente</Boton>
          </div>
        </div>
      )}
    </div>
  );
}
