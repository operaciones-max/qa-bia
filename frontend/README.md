# Frontend — dashboard de revisión

Servidor web en Go que muestra los resultados del QA y permite revisarlos.
Lee y escribe directo en Supabase (tabla `actas_qa`); no habla con el backend.

Usa solo HTML del servidor: plantillas `html/template` y un CSS propio, sin
JavaScript. Las plantillas y el CSS van embebidos en el binario.

## Pantallas

- **Login** con correo y contraseña (Supabase Auth). La sesión se guarda en una
  cookie `HttpOnly` y el token se refresca solo antes de vencer.
- **Listado** (`/`): indicadores (total, exitosas, fallidas, con
  discrepancias, sin revisar), filtros por texto, tipo de servicio, planner,
  estado, track, revisión, fechas y "solo con discrepancias", con paginación.
  Los filtros quedan en la URL: se pueden compartir y se mantienen al volver
  del detalle.
- **Detalle** (`/actas/<ot_id>`): datos de la OT, técnico y observación
  literal, medida y equipos, comparación con WMS, factura anterior, alcance,
  tipificación de la falla, errores y alertas, y la respuesta completa de la IA.
- **Revisión**: aprobar como exitosa, marcar como fallida o quitar la revisión,
  con comentario. Se guarda en las columnas `revision_*`, que el backend nunca
  toca. Quién revisó y cuándo lo pone la base de datos.

## Seguridad

- Las consultas a Supabase usan la **anon key + el token del usuario**, así que
  aplican las políticas RLS de `supabase/migrations/…_seguridad.sql`: sin login
  no se ve nada y el revisor solo puede escribir las columnas de revisión.
- Los formularios solo se aceptan desde el mismo origen (cookie `SameSite=Lax`
  y chequeo del header `Origin`).
- En producción, servirlo detrás de HTTPS y poner `COOKIE_SEGURA=true`.

## Correr

```bash
cp frontend/.env.example frontend/.env    # SUPABASE_URL y SUPABASE_ANON_KEY
go run ./frontend/cmd/dashboard           # http://localhost:8080
```

Requisitos en Supabase (una sola vez):
1. Aplicar las migraciones de [`../supabase/migrations`](../supabase/migrations).
2. Crear los usuarios revisores en *Authentication → Users → Add user*.

`GET /salud` responde `ok` (para monitoreo o el health check del hosting).

## Estructura

```
frontend/
├── cmd/dashboard/main.go   Configuración y arranque del servidor
└── web/
    ├── servidor.go         Rutas, sesión, CSRF y handlers
    ├── supabase.go         Auth y consultas a actas_qa
    ├── filtros.go          Filtros de pantalla ↔ URL ↔ condiciones de PostgREST
    ├── formato.go          Fechas, estados y etiquetas para las plantillas
    ├── acta.go             Tipo de la fila de actas_qa (contrato con el backend)
    ├── plantillas/         base, login, lista, detalle, error
    └── estaticos/          estilos.css
```

## Publicar

`go build -o dashboard ./frontend/cmd/dashboard` genera un único binario
autocontenido. Se puede correr en cualquier servidor o contenedor con las
variables de `frontend/.env.example`.
