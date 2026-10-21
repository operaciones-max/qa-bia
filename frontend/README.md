# Frontend — dashboard de revisión

El dashboard donde el equipo revisa los resultados del QA **no está en este
repo**: hoy vive en Lovable y lee directamente de Supabase.

```
Lovable (dashboard) ──lee/edita──▶ Supabase · actas_qa ◀──escribe── backend/
```

- Datos que puede mostrar y qué significa cada columna:
  [../docs/contrato-supabase.md](../docs/contrato-supabase.md).
- El frontend no necesita llamar al backend: el backend corre solo (GitHub
  Actions) y deja los resultados en la tabla.

## Traer el código aquí

Lovable puede sincronizar el proyecto con un repositorio de GitHub. Hay dos
opciones:

1. **Repo aparte (recomendado con Lovable):** conectar Lovable a su propio
   repo (por ejemplo `qa-bia-dashboard`) y enlazarlo desde aquí. Lovable
   sincroniza en las dos direcciones con su repo, así que es la forma que
   menos se rompe.
2. **Dentro de esta carpeta:** exportar el código de Lovable a `frontend/`. Se
   pierde la edición desde Lovable (o hay que copiar a mano cada cambio).

En cualquier caso, las credenciales del dashboard deben ser la *anon key* de
Supabase con políticas RLS, nunca la *service role key* que usa el backend.
