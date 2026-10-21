-- Permisos de actas_qa:
--   service_role  (backend, GitHub Actions): todo; ignora RLS.
--   authenticated (usuarios del dashboard):   leer todo y escribir solo revision_*.
--   anon          (sin login):                nada.
--
-- OJO: el backend debe usar SUPABASE_SERVICE_ROLE_KEY. Con la anon key ya no
-- puede escribir.

alter table public.actas_qa enable row level security;

revoke all on public.actas_qa from anon;
revoke all on public.actas_qa from authenticated;
grant select on public.actas_qa to authenticated;
grant update (revision_resultado, revision_comentario, revisado_por, revisado_en)
  on public.actas_qa to authenticated;

drop policy if exists dashboard_lee_actas on public.actas_qa;
create policy dashboard_lee_actas on public.actas_qa
  for select to authenticated using (true);

drop policy if exists dashboard_revisa_actas on public.actas_qa;
create policy dashboard_revisa_actas on public.actas_qa
  for update to authenticated using (true) with check (true);
