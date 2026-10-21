import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router";
import { PanelRevision } from "../components/PanelRevision.tsx";
import { Campo, Campos, Cargando, Insignia, MensajeError, Seccion } from "../components/ui.tsx";
import { obtenerActa } from "../lib/actas.ts";
import {
  estadoFinal, formatearFecha, textoCoincidencia, textoFactura, textoOVacio, textoSiNo,
  tonoCoincidencia, tonoEstado,
} from "../lib/formato.ts";
import type { ActaQA } from "../types/acta.ts";

function Comparacion({ valor }: { valor: boolean | null }) {
  return <Insignia tono={tonoCoincidencia(valor)}>{textoCoincidencia(valor)}</Insignia>;
}

function Lista({ items, vacio }: { items: string[] | null | undefined; vacio: string }) {
  if (!items?.length) return <p className="text-sm text-slate-500">{vacio}</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-slate-800">
      {items.map((t, i) => <li key={i}>{t}</li>)}
    </ul>
  );
}

function Seriales({ seriales }: { seriales: string[] | undefined }) {
  return <>{seriales?.length ? seriales.join(", ") : "—"}</>;
}

export function DetalleActa() {
  const { otId = "" } = useParams();
  const { search } = useLocation();
  const [acta, setActa] = useState<ActaQA | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setActa(undefined);
    obtenerActa(otId)
      .then(setActa)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [otId]);

  const volver = (
    <Link to={{ pathname: "/", search }} className="text-sm text-slate-600 hover:underline">
      ← Volver al listado
    </Link>
  );

  if (error) return <div className="space-y-4">{volver}<MensajeError error={error} /></div>;
  if (acta === undefined) return <Cargando />;
  if (acta === null) return <div className="space-y-4">{volver}<MensajeError error="No existe un acta con ese id." /></div>;

  const qa = acta.resultado_qa_completo ?? {};
  const falla = qa.tipificacion_falla;
  const estado = estadoFinal(acta);
  const empresaTecnico =
    acta.tecnico_empresa === "CONTRATISTA" ? `Contratista · ${textoOVacio(acta.contratista_nombre)}`
    : acta.tecnico_empresa === "BIA" ? "BIA Energy" : "—";

  return (
    <div className="space-y-4">
      {volver}

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{textoOVacio(acta.ot_nombre)}</h1>
          <p className="text-sm text-slate-500">
            {textoOVacio(acta.internal_bia_code)} · {textoOVacio(acta.tipo_servicio)} · {formatearFecha(acta.fecha_ejecucion, true)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Insignia tono={tonoEstado(estado)}>{textoOVacio(estado)}</Insignia>
          {acta.revision_resultado && acta.revision_resultado !== acta.estado_ot && (
            <span className="text-xs text-slate-500">(App Ops: {textoOVacio(acta.estado_ot)})</span>
          )}
          {acta.pdf_url && (
            <a href={acta.pdf_url} target="_blank" rel="noreferrer"
               className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50">
              Ver PDF del acta
            </a>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Seccion titulo="Datos generales">
            <Campos>
              <Campo etiqueta="Track QA">{textoOVacio(acta.qa_track)}</Campo>
              <Campo etiqueta="Analizada">{formatearFecha(acta.procesado_en, true)}</Campo>
              <Campo etiqueta="Empresa">{textoOVacio(acta.empresa)}</Campo>
              <Campo etiqueta="Dirección">{textoOVacio(acta.direccion)}</Campo>
              <Campo etiqueta="Operador de red">{textoOVacio(acta.or_norm)}</Campo>
              <Campo etiqueta="Planner">{textoOVacio(acta.planner)}</Campo>
              <Campo etiqueta="Contrato">{textoOVacio(acta.contract_id)}</Campo>
              <Campo etiqueta="Cierre en App Ops">
                {acta.estado_app_ops ?? "Sin cerrar"} ({textoOVacio(acta.estado_revision)})
              </Campo>
            </Campos>
          </Seccion>

          <Seccion titulo="Técnico">
            <Campos>
              <Campo etiqueta="Nombre">{textoOVacio(acta.tecnico_nombre)}</Campo>
              <Campo etiqueta="Empresa">{empresaTecnico}</Campo>
            </Campos>
            <div className="mt-3">
              <p className="text-xs text-slate-500">Observación del técnico (literal)</p>
              <blockquote className="mt-1 whitespace-pre-wrap border-l-2 border-slate-300 pl-3 text-sm italic text-slate-800">
                {textoOVacio(qa.observacion_tecnico_verbatim)}
              </blockquote>
            </div>
            {qa.observaciones_tecnicas && (
              <div className="mt-3">
                <p className="text-xs text-slate-500">Resumen técnico (IA)</p>
                <p className="mt-1 text-sm text-slate-800">{qa.observaciones_tecnicas}</p>
              </div>
            )}
          </Seccion>

          <Seccion titulo="Medida y equipos">
            <Campos>
              <Campo etiqueta="Tipo de medida">{textoOVacio(acta.tipo_medida)} · factor {textoOVacio(acta.factor_medida)}</Campo>
              <Campo etiqueta="Firma del operador de red">{textoOVacio(acta.or_firma)}</Campo>
              <Campo etiqueta="Medidor encontrado">
                {textoOVacio(acta.medidor_encontrado_serie)} · {textoOVacio(acta.medidor_encontrado_marca)}
              </Campo>
              <Campo etiqueta="Medidor instalado">
                {textoOVacio(acta.medidor_instalado_serie)} · {textoOVacio(acta.medidor_instalado_marca)}
              </Campo>
              <Campo etiqueta="Sellos medidor (encontrado / instalado)">
                {textoOVacio(acta.sellos_medidor_encontrado)} / {textoOVacio(acta.sellos_medidor_instalado)}
              </Campo>
              <Campo etiqueta="Sellos TCs (encontrados / instalados)">
                {textoOVacio(acta.sellos_tcs_encontrados)} / {textoOVacio(acta.sellos_tcs_instalados)}
              </Campo>
              <Campo etiqueta="TCs / TPs">{textoSiNo(acta.tiene_tcs)} / {textoSiNo(acta.tiene_tps)}</Campo>
              <Campo etiqueta="Telemedida · diagrama unifilar">
                {textoSiNo(acta.tiene_telemedida)} · {textoSiNo(acta.tiene_diagrama_unifilar)}
              </Campo>
            </Campos>
          </Seccion>

          <Seccion titulo="Comparación con WMS">
            {acta.wms_asignado ? (
              <Campos>
                <Campo etiqueta="Medidor asignado">
                  {textoOVacio(acta.wms_medidor_serial)} · {textoOVacio(acta.wms_medidor_marca)}
                </Campo>
                <Campo etiqueta="Medidor instalado vs WMS"><Comparacion valor={acta.medidor_coincide_wms} /></Campo>
                <Campo etiqueta="TCs asignados en WMS">
                  <Seriales seriales={acta.wms_completo?.tcs.map((t) => t.serial)} />
                </Campo>
                <Campo etiqueta="TCs instalados (acta)"><Seriales seriales={qa.tcs_instalados?.seriales} /></Campo>
                <Campo etiqueta="TCs vs WMS"><Comparacion valor={acta.tcs_coinciden_wms} /></Campo>
                <Campo etiqueta="TPs vs WMS"><Comparacion valor={acta.tps_coinciden_wms} /></Campo>
                <Campo etiqueta="Marca WMS vs alcance"><Comparacion valor={acta.wms_marca_coincide_alcance} /></Campo>
              </Campos>
            ) : (
              <p className="text-sm text-slate-500">Este código no tiene equipos asignados en WMS.</p>
            )}
          </Seccion>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Seccion titulo="Factura anterior">
              <Campos>
                <Campo etiqueta="Lectura">{textoFactura(acta.factura_anterior_estado)}</Campo>
                <Campo etiqueta="Serial en factura">{textoOVacio(acta.serial_medidor_factura_anterior)}</Campo>
                <Campo etiqueta="vs medidor encontrado"><Comparacion valor={acta.medidor_coincide_factura_anterior} /></Campo>
                <Campo etiqueta="Express">{textoSiNo(acta.factura_anterior_express)}</Campo>
              </Campos>
            </Seccion>
            <Seccion titulo="Alcance de ingeniería">
              {acta.tiene_alcance ? (
                <Campos>
                  <Campo etiqueta="Viable para instalar">{textoOVacio(acta.alcance_viable)}</Campo>
                  <Campo etiqueta="Medida a instalar">{textoOVacio(acta.alcance_medida_instalar)}</Campo>
                </Campos>
              ) : (
                <p className="text-sm text-slate-500">Sin alcance registrado.</p>
              )}
            </Seccion>
          </div>

          {estado === "FALLIDA" && falla && (
            <Seccion titulo="Tipificación de la falla">
              <Campos>
                <Campo etiqueta="Causa raíz">{textoOVacio(falla.causa_raiz ?? acta.tipificacion_causa_raiz)}</Campo>
                <Campo etiqueta="Responsable">{textoOVacio(falla.responsable ?? acta.tipificacion_responsable)}</Campo>
              </Campos>
              <div className="mt-3 space-y-2 text-sm text-slate-800">
                <p><span className="text-xs text-slate-500">Detalle</span><br />{textoOVacio(falla.detalle)}</p>
                <p><span className="text-xs text-slate-500">Mejora propuesta</span><br />{textoOVacio(falla.mejora)}</p>
              </div>
            </Seccion>
          )}
        </div>

        <div className="space-y-4">
          <PanelRevision key={acta.ot_id} acta={acta} onGuardada={setActa} />
          <Seccion titulo={`Errores QA (${acta.errores_qa?.length ?? 0})`}>
            <Lista items={acta.errores_qa} vacio="Sin errores." />
          </Seccion>
          <Seccion titulo={`Alertas (${acta.alertas_qa?.length ?? 0})`}>
            <Lista items={acta.alertas_qa} vacio="Sin alertas." />
          </Seccion>
          <details className="rounded-lg border border-slate-200 bg-white px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">Respuesta completa de la IA</summary>
            <pre className="mt-3 max-h-96 overflow-auto rounded bg-slate-50 p-3 text-xs text-slate-700">
              {JSON.stringify(acta.resultado_qa_completo, null, 2)}
            </pre>
          </details>
        </div>
      </div>
    </div>
  );
}
