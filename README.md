# QA BIA — Auditoría automatizada de actas

Sistema que revisa con IA (Anthropic Claude) las actas de campo de BIA Energy
(instalaciones, visitas previas, PQR, normalizaciones, etc.), las cruza con el
inventario WMS, los alcances de ingeniería y la factura anterior, y deja el
resultado en Supabase para que el equipo lo revise en un dashboard web.

> **Estado:** pausado. El cron de GitHub Actions está desactivado; el QA solo
> corre a mano desde *Actions → QA BIA Automatico → Run workflow*.

## Arquitectura

```
Metabase (actas, WMS, alcances, facturas, App Ops)
        │ lee
        ▼
┌─ BACKEND · backend/ ─────────────────────────────────────────┐
│ Python, corre en GitHub Actions                              │
│ metabase → pdf → ia (Claude) → validaciones → supabase       │
└──────────────────────────────────────────────────────────────┘
        │ escribe (service role key)
        ▼
Supabase · tabla actas_qa          ← esquema y permisos en supabase/migrations/
        ▲ lee y guarda la revisión (usuario con login)
        │
┌─ FRONTEND · frontend/ ───────────────────────────────────────┐
│ React + Vite, sitio estático                                 │
│ listado con filtros · detalle del acta · revisión humana     │
└──────────────────────────────────────────────────────────────┘
```

El backend y el frontend **no se llaman entre sí**: se comunican solo a través
de la tabla `actas_qa`. Qué columna escribe cada lado está en
[docs/contrato-supabase.md](docs/contrato-supabase.md).

## Estructura del repo

```
qa-bia/
├── backend/                 Motor de QA en Python (ver backend/README.md)
│   ├── qa_bia/              Paquete principal
│   ├── scripts/             Scripts de mantenimiento (forzar reprocesos)
│   ├── state/               Estado del bot: actas ya procesadas, caches (lo commitea el bot)
│   └── tests/
├── frontend/                Dashboard de revisión (ver frontend/README.md)
│   └── src/
├── supabase/migrations/     Tabla actas_qa, columnas de revisión y permisos (RLS)
├── docs/
│   ├── contrato-supabase.md Columnas de actas_qa: quién escribe qué
│   └── hallazgos.md         Revisión del código: bugs y riesgos encontrados
└── .github/workflows/       CI, QA automático y 2 workflows de limpieza manual
```

## Puesta en marcha (una sola vez)

1. **Supabase:** aplicar en orden los archivos de `supabase/migrations/`
   (SQL Editor del proyecto, o `supabase db push` con la CLI). Se pueden
   correr más de una vez sin problema.
2. **Usuarios del dashboard:** crearlos en *Authentication → Users → Add user*.
3. **GitHub Actions:** el secreto `SUPABASE_SERVICE_ROLE_KEY` debe estar
   cargado. Con la seguridad activada, la anon key ya no puede escribir.

## Uso diario

```bash
# Backend: correr el QA en local sin tocar producción
cd backend && pip install -r requirements-dev.txt
cp .env.example .env              # completar ANTHROPIC_API_KEY
python -m qa_bia

# Frontend: levantar el dashboard
cd frontend && npm install
cp .env.example .env.local        # URL y anon key de Supabase
npm run dev
```

Pruebas: `python -m pytest` en `backend/` y `npm test` en `frontend/`. El
workflow **CI** las corre en cada push y PR.

## Trabajar en una rama

1. Crear la rama desde `main` y hacer los cambios.
2. Probar en local: backend con `QA_MODO_PRUEBA=true` y sin credenciales de
   Supabase (ver `backend/.env.example`); frontend con `npm run dev`.
3. Si hace falta correr el QA en GitHub Actions, lanzar el workflow eligiendo
   la rama: corre el código de esa rama y commitea el estado en esa misma rama.
   **Ojo:** usa los mismos secretos, o sea escribe en el Supabase de producción.
4. Abrir un PR hacia `main`; el CI tiene que pasar.
