import { useState } from "react";
import { guardarRevision } from "../lib/actas.ts";
import { formatearFecha } from "../lib/formato.ts";
import type { ActaQA, EstadoOT } from "../types/acta.ts";
import { Boton, Insignia, MensajeError, Seccion } from "./ui.tsx";

/** Veredicto del revisor. Solo escribe columnas revision_* (el backend no las toca). */
export function PanelRevision({ acta, onGuardada }: { acta: ActaQA; onGuardada: (acta: ActaQA) => void }) {
  const [comentario, setComentario] = useState(acta.revision_comentario ?? "");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function guardar(resultado: EstadoOT | null) {
    setGuardando(true);
    setError(null);
    try {
      const actualizada = await guardarRevision(acta.ot_id, { resultado, comentario });
      setComentario(actualizada.revision_comentario ?? "");
      onGuardada(actualizada);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Seccion titulo="Revisión">
      {acta.revision_resultado ? (
        <p className="mb-3 text-sm text-slate-700">
          <Insignia tono={acta.revision_resultado === "EXITOSA" ? "verde" : "rojo"}>
            {acta.revision_resultado === "EXITOSA" ? "Aprobada como exitosa" : "Marcada como fallida"}
          </Insignia>{" "}
          por {acta.revisado_por ?? "—"} el {formatearFecha(acta.revisado_en, true)}
        </p>
      ) : (
        <p className="mb-3 text-sm text-slate-500">Esta acta todavía no fue revisada.</p>
      )}
      <label className="block">
        <span className="text-xs text-slate-500">Comentario</span>
        <textarea
          className="mt-1 w-full rounded-md border-0 px-2.5 py-1.5 text-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-slate-600"
          rows={3}
          value={comentario}
          onChange={(e) => setComentario(e.target.value)}
          placeholder="Qué se revisó, qué hay que corregir…"
        />
      </label>
      {error && <div className="mt-2"><MensajeError error={error} /></div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Boton variante="primario" disabled={guardando} onClick={() => guardar("EXITOSA")}>
          Aprobar como exitosa
        </Boton>
        <Boton variante="peligro" disabled={guardando} onClick={() => guardar("FALLIDA")}>
          Marcar como fallida
        </Boton>
        {acta.revision_resultado && (
          <Boton disabled={guardando} onClick={() => guardar(null)}>
            Quitar revisión
          </Boton>
        )}
      </div>
    </Seccion>
  );
}
