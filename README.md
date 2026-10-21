# QA BIA — Auditoría automatizada de actas

Sistema que revisa con IA (Anthropic Claude) las actas de campo de BIA Energy
(instalaciones, visitas previas, PQR, normalizaciones, etc.), las cruza con el
inventario WMS, los alcances de ingeniería y la factura anterior, y deja el
resultado en Supabase para que el equipo lo revise en un dashboard.

> **Estado:** pausado. El cron de GitHub Actions está desactivado; el QA solo
> corre a mano desde *Actions → QA BIA Automatico → Run workflow*.

## Arquitectura

```
Metabase (actas, WMS, alcances, facturas, App Ops)
        │ lee
        ▼
┌─ BACKEND · backend/ ─────────────────────────────────────────┐
│ metabase → pdf → ia (Claude) → validaciones → supabase       │
│ pipeline.py orquesta · estado.py guarda qué ya se procesó    │
└──────────────────────────────────────────────────────────────┘
        │ escribe
        ▼
Supabase · tabla actas_qa
        ▲ lee y edita la revisión
        │
┌─ FRONTEND · frontend/ ─────────┐
│ Dashboard de revisión (Lovable) │
└─────────────────────────────────┘
```

El backend y el frontend **no se llaman entre sí**: se comunican solo a través
de la tabla `actas_qa` de Supabase. Qué columna escribe cada lado está en
[docs/contrato-supabase.md](docs/contrato-supabase.md).

## Estructura del repo

```
qa-bia/
├── backend/                 Motor de QA en Python (corre en GitHub Actions)
│   ├── qa_bia/              Paquete principal (ver backend/README.md)
│   ├── scripts/             Scripts de mantenimiento (forzar reprocesos)
│   ├── state/               Estado del bot: actas ya procesadas, caches (lo commitea el bot)
│   ├── tests/               Pruebas de las reglas deterministas
│   ├── requirements.txt
│   └── .env.example         Variables para correr en local
├── frontend/                Dashboard de revisión (hoy vive en Lovable, ver frontend/README.md)
├── docs/
│   ├── contrato-supabase.md Columnas de actas_qa: quién escribe qué
│   └── hallazgos.md         Revisión del código: bugs y riesgos encontrados
└── .github/workflows/       QA automático + 2 workflows de limpieza manual
```

## Uso rápido

```bash
cd backend
pip install -r requirements-dev.txt
cp .env.example .env          # poner ANTHROPIC_API_KEY; dejar Supabase vacío para no escribir en producción
python -m qa_bia              # corre el QA
python -m pytest              # corre las pruebas
```

Más detalle en [backend/README.md](backend/README.md).

## Trabajar en una rama

1. Crear la rama desde `main` y hacer los cambios.
2. Probar en local con `QA_MODO_PRUEBA=true` y sin credenciales de Supabase
   (ver `backend/.env.example`).
3. Si hace falta correrlo en GitHub Actions, lanzar el workflow eligiendo la
   rama: corre el código de esa rama y commitea el estado en esa misma rama.
   **Ojo:** usa los mismos secretos, o sea escribe en el Supabase de producción.
4. Abrir un PR hacia `main`.
