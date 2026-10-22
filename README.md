# QA BIA — Auditoría automatizada de actas

Sistema que revisa con IA (Anthropic Claude) las actas de campo de BIA Energy
(instalaciones, visitas previas, PQR, normalizaciones, etc.), las cruza con el
inventario WMS, los alcances de ingeniería y la factura anterior, y deja el
resultado en Supabase para que el equipo lo revise en un dashboard web.

Todo está escrito en **Go** (un solo módulo: `github.com/operaciones-max/qa-bia`).

> **Estado:** pausado. El cron de GitHub Actions está desactivado; el QA solo
> corre a mano desde *Actions → QA BIA Automatico → Run workflow*.

## Arquitectura

```
Metabase (actas, WMS, alcances, facturas, App Ops)
        │ lee
        ▼
┌─ BACKEND · backend/ ─────────────────────────────────────────┐
│ go run ./backend/cmd/qa   (en GitHub Actions)                │
│ metabase → pdf → ia (Claude) → validaciones → supabase       │
└──────────────────────────────────────────────────────────────┘
        │ escribe (service role key)
        ▼
Supabase · tabla actas_qa          ← esquema y permisos en supabase/migrations/
        ▲ lee y guarda la revisión (usuario con login, RLS)
        │
┌─ FRONTEND · frontend/ ───────────────────────────────────────┐
│ go run ./frontend/cmd/dashboard   (servidor web)             │
│ listado con filtros · detalle del acta · revisión humana     │
└──────────────────────────────────────────────────────────────┘
```

Aparte, `backend/` tiene un **servicio de extracción de documentos** (OCR con
Claude): recibe el link de un PDF o una imagen y devuelve el JSON pedido. Ver
[docs/servicio-extraccion.md](docs/servicio-extraccion.md).

El backend y el frontend **no se llaman entre sí**: se comunican solo a través
de la tabla `actas_qa`. Qué columna escribe cada lado está en
[docs/contrato-supabase.md](docs/contrato-supabase.md).

## Estructura del repo

```
qa-bia/
├── go.mod, go.sum
├── backend/                  Motor de QA (ver backend/README.md)
│   ├── cmd/qa/               Programa principal del QA
│   ├── cmd/limpiar-*/        Scripts de mantenimiento (forzar reprocesos)
│   ├── cmd/extraccion/       Servicio HTTP de extracción de documentos (OCR) + Dockerfile
│   ├── metabase, pdf, ia, facturas, catalogo, validaciones, supabase, …  paquetes
│   └── state/                Estado del bot: actas ya procesadas, caches (lo commitea el bot)
├── frontend/                 Dashboard de revisión (ver frontend/README.md)
│   ├── cmd/dashboard/        Servidor web
│   └── web/                  Handlers, plantillas HTML y CSS (embebidos en el binario)
├── internal/envfile/         Lectura de archivos .env (compartido)
├── supabase/migrations/      Tablas actas_qa y extracciones, columnas de revisión y permisos (RLS)
├── docs/
│   ├── contrato-supabase.md  Columnas de actas_qa: quién escribe qué
│   ├── servicio-extraccion.md  Servicio de extracción: API, configuración y origen
│   ├── agentes-ot.md         Subagentes de cierre por tipo de OT: estado y qué falta
│   └── hallazgos.md          Revisión del código: bugs, riesgos y su estado
└── .github/workflows/        CI, QA automático y 2 workflows de limpieza manual
```

## Puesta en marcha (una sola vez)

1. **Supabase:** aplicar en orden los archivos de `supabase/migrations/`
   (SQL Editor del proyecto, o `supabase db push` con la CLI). Se pueden
   correr más de una vez sin problema.
2. **Usuarios del dashboard:** crearlos en *Authentication → Users → Add user*.
3. **GitHub Actions:** el secreto `SUPABASE_SERVICE_ROLE_KEY` debe estar
   cargado. Con la seguridad activada, la anon key ya no puede escribir.

## Uso diario

Requiere Go 1.24+ y un compilador C (gcc/clang) para leer PDFs con MuPDF.
Todos los comandos se corren desde la raíz del repo.

```bash
# Backend: correr el QA en local sin tocar producción
cp backend/.env.example backend/.env      # completar ANTHROPIC_API_KEY
go run ./backend/cmd/qa

# Frontend: levantar el dashboard
cp frontend/.env.example frontend/.env    # URL y anon key de Supabase
go run ./frontend/cmd/dashboard           # http://localhost:8080

# Servicio de extracción de documentos
go run ./backend/cmd/extraccion           # http://localhost:8081

# Pruebas
go test ./...
```

El workflow **CI** corre `gofmt`, `go vet`, las pruebas y el build en cada push y PR.

## Trabajar en una rama

1. Crear la rama desde `main` y hacer los cambios.
2. Probar en local: el backend con `QA_MODO_PRUEBA=true` y sin credenciales de
   Supabase (ver `backend/.env.example`), y el dashboard con `go run`.
3. Si hace falta correr el QA en GitHub Actions, lanzar el workflow eligiendo
   la rama: corre el código de esa rama y commitea el estado en esa misma rama.
   **Ojo:** usa los mismos secretos, o sea que escribe en el Supabase de producción.
4. Abrir un PR hacia `main`; el CI tiene que pasar.
