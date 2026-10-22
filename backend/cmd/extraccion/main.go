// Comando extraccion: servicio HTTP que extrae informacion de PDFs e imagenes
// con Claude (ver docs/servicio-extraccion.md).
//
// Ejecutar desde la raiz del repo:  go run ./backend/cmd/extraccion
// Lee la configuracion de variables de entorno o de backend/.env.
package main

import (
	"log"
	"net/http"
	"path/filepath"
	"time"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/extraccion"
	"github.com/operaciones-max/qa-bia/backend/ia"
	"github.com/operaciones-max/qa-bia/backend/supabase"
	"github.com/operaciones-max/qa-bia/internal/envfile"
)

func main() {
	cfg := config.Cargar(filepath.Join("backend", ".env"))
	if cfg.AnthropicAPIKey == "" {
		log.Fatal("Falta ANTHROPIC_API_KEY (variable de entorno o backend/.env).")
	}
	// Modelo propio del servicio: CLAUDE_MODEL es el del QA.
	cfg.ClaudeModel = envfile.Texto("EXTRACCION_MODELO", "claude-opus-5-5")

	repo := extraccion.NuevoRepositorioSupabase(supabase.New(cfg))
	if repo == nil {
		log.Print("AVISO: sin SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY no se guardan las solicitudes.")
	}
	apiKey := envfile.Texto("EXTRACCION_API_KEY", "")
	if apiKey == "" {
		log.Print("AVISO: sin EXTRACCION_API_KEY cualquiera que llegue al puerto puede usar el servicio (y gastar en Claude).")
	}

	servicio := extraccion.NuevoServicio(
		extraccion.NuevoDescargador(false),
		ia.NewCliente(cfg, nil),
		repo,
		envfile.Texto("EXTRACCION_ESFUERZO", ""),
	)
	direccion := ":" + envfile.Texto("EXTRACCION_PUERTO", envfile.Texto("PORT", "8081"))
	log.Printf("Servicio de extraccion en http://localhost%s%s (modelo %s)", direccion, extraccion.RutaExtraccion, cfg.ClaudeModel)
	srv := &http.Server{
		Addr:              direccion,
		Handler:           extraccion.NuevoHandler(servicio, apiKey),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      extraccion.TiempoMaximo + 30*time.Second,
	}
	log.Fatal(srv.ListenAndServe())
}
