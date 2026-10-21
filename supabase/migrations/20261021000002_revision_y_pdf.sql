-- Columnas nuevas:
--   pdf_url    -> la escribe el backend (link al PDF del acta para el revisor).
--   revision_* -> las escribe SOLO el frontend. El backend nunca las toca, asi
--                 que reprocesar un acta no borra la revision humana.
--
-- Aplicar ANTES de correr el backend nuevo: si falta pdf_url, Supabase rechaza
-- la escritura de las actas.

alter table public.actas_qa
  add column if not exists pdf_url             text,
  add column if not exists revision_resultado  text check (revision_resultado in ('EXITOSA', 'FALLIDA')),
  add column if not exists revision_comentario text,
  add column if not exists revisado_por        text,
  add column if not exists revisado_en         timestamptz;

create index if not exists actas_qa_fecha_ejecucion_idx on public.actas_qa (fecha_ejecucion desc);
create index if not exists actas_qa_internal_bia_code_idx on public.actas_qa (internal_bia_code);

-- Quien revisa y cuando lo pone la base de datos (no se puede falsear desde el navegador).
create or replace function public.actas_qa_firmar_revision() returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.revision_resultado is distinct from old.revision_resultado
     or new.revision_comentario is distinct from old.revision_comentario then
    if new.revision_resultado is null then
      new.revision_comentario := null;
      new.revisado_por := null;
      new.revisado_en := null;
    else
      new.revisado_por := coalesce(auth.jwt() ->> 'email', new.revisado_por);
      new.revisado_en := now();
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists actas_qa_firmar_revision on public.actas_qa;
create trigger actas_qa_firmar_revision
  before update on public.actas_qa
  for each row execute function public.actas_qa_firmar_revision();
