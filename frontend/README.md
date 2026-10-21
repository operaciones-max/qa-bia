# Frontend — dashboard de revisión

App web para revisar los resultados del QA. Lee y escribe directo en Supabase
(tabla `actas_qa`); no habla con el backend.

Stack: React 19 + TypeScript + Vite + Tailwind CSS + supabase-js.

## Pantallas

- **Login** con correo y contraseña (Supabase Auth).
- **Listado** (`/#/`): indicadores (total, exitosas, fallidas, con
  discrepancias, sin revisar), filtros por texto, tipo de servicio, planner,
  estado, track, revisión, fechas y "solo con discrepancias", con paginación.
  Los filtros quedan en la URL: se pueden compartir y se mantienen al volver
  del detalle.
- **Detalle** (`/#/actas/<ot_id>`): datos de la OT, técnico y observación
  literal, medida y equipos, comparación con WMS, factura anterior, alcance,
  tipificación de la falla, errores y alertas, y la respuesta completa de la IA.
- **Revisión**: aprobar como exitosa, marcar como fallida o quitar la revisión,
  con comentario. Se guarda en las columnas `revision_*`, que el backend nunca
  toca. Quién revisó y cuándo lo pone la base de datos.

## Correr en local

```bash
cd frontend
cp .env.example .env.local      # URL del proyecto y ANON key de Supabase
npm install
npm run dev                     # http://localhost:5173
```

Requisitos en Supabase (una sola vez):
1. Aplicar las migraciones de [`../supabase/migrations`](../supabase/migrations).
2. Crear los usuarios revisores en *Authentication → Users → Add user*.

## Scripts

| Comando | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo |
| `npm test` | Pruebas de la lógica de filtros y formato (`node --test`) |
| `npm run typecheck` | Chequeo de tipos |
| `npm run build` | Build estático en `dist/` |

## Estructura

```
src/
├── main.tsx, App.tsx    Entrada, login y rutas
├── pages/               Login, ListaActas, DetalleActa
├── components/          Tabla, filtros, indicadores, panel de revisión, piezas de UI
├── lib/
│   ├── supabase.ts      Cliente de Supabase
│   ├── actas.ts         Todas las consultas a actas_qa
│   ├── filtros.ts       Filtros de pantalla → condiciones de PostgREST (puro, con pruebas)
│   └── formato.ts       Fechas, estados y etiquetas (puro, con pruebas)
├── hooks/useSesion.ts   Sesión de Supabase Auth
└── types/acta.ts        Tipo de la fila de actas_qa (contrato con el backend)
```

## Publicar

`npm run build` genera archivos estáticos en `dist/`. Las rutas usan `#`, así
que se puede publicar tal cual en cualquier hosting estático (Netlify, Vercel,
Cloudflare Pages, S3) sin configurar redirecciones. Hay que definir
`VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` al momento del build.

La anon key es pública por diseño: lo que protege los datos son las políticas
RLS de la migración `..._seguridad.sql` (sin login no se ve nada).
