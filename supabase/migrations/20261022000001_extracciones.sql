-- Servicio de extraccion de documentos (backend/cmd/extraccion): cada solicitud
-- con su respuesta. Reemplaza la base PostgreSQL propia del servicio original.
--
-- Permisos: solo service_role (el servicio). Ni el dashboard ni anon la ven:
-- la respuesta trae datos personales de clientes.

create table if not exists public.extracciones (
  id             bigint generated always as identity primary key,
  creado_en      timestamptz not null default now(),
  link           text not null,
  solicitud      jsonb not null,   -- {"link", "prompt"} tal como llego
  tipo_archivo   text check (tipo_archivo in ('pdf', 'imagen')),
  metodo         text check (metodo in ('texto', 'imagenes', 'mixto')),
  paginas        integer,
  modelo         text,             -- el que respondio
  respuesta      jsonb,            -- JSON extraido; null si fallo
  error          text,             -- null si salio bien
  duracion_ms    integer,
  tokens_entrada integer,
  tokens_salida  integer
);

create index if not exists extracciones_creado_en_idx on public.extracciones (creado_en desc);

alter table public.extracciones enable row level security;
revoke all on public.extracciones from anon;
revoke all on public.extracciones from authenticated;
