package extraccion

import (
	"context"

	"github.com/operaciones-max/qa-bia/backend/supabase"
)

// TablaExtracciones es la tabla de Supabase donde queda cada solicitud
// (supabase/migrations/…_extracciones.sql).
const TablaExtracciones = "extracciones"

// RepositorioSupabase guarda las extracciones en Supabase con la service role key.
type RepositorioSupabase struct {
	cliente *supabase.Cliente
}

// NuevoRepositorioSupabase devuelve nil si Supabase no esta configurado.
func NuevoRepositorioSupabase(c *supabase.Cliente) Repositorio {
	if c == nil {
		return nil
	}
	return &RepositorioSupabase{cliente: c}
}

// Guardar inserta la fila y devuelve su id.
func (r *RepositorioSupabase) Guardar(_ context.Context, reg Registro) (int64, error) {
	return r.cliente.Insertar(TablaExtracciones, Fila(reg))
}

// Fila arma las columnas de la tabla extracciones.
func Fila(reg Registro) map[string]any {
	return map[string]any{
		"link":           reg.Solicitud.Link,
		"solicitud":      reg.Solicitud,
		"tipo_archivo":   vacioANil(reg.Tipo),
		"metodo":         vacioANil(reg.Metodo),
		"paginas":        ceroANil(int64(reg.Paginas)),
		"modelo":         vacioANil(reg.Modelo),
		"respuesta":      reg.Respuesta, // null si fallo
		"error":          vacioANil(reg.Error),
		"duracion_ms":    reg.Duracion.Milliseconds(),
		"tokens_entrada": ceroANil(reg.TokensEntrada),
		"tokens_salida":  ceroANil(reg.TokensSalida),
	}
}

func vacioANil(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func ceroANil(n int64) any {
	if n == 0 {
		return nil
	}
	return n
}
