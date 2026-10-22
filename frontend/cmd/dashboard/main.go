// Comando dashboard: servidor web de revision de actas.
//
// Ejecutar desde la raiz del repo:  go run ./frontend/cmd/dashboard
// Lee la configuracion de variables de entorno o de frontend/.env.
package main

import (
	"log"
	"net/http"
	"path/filepath"
	"time"

	"github.com/operaciones-max/qa-bia/frontend/web"
	"github.com/operaciones-max/qa-bia/internal/envfile"
)

func main() {
	envfile.Cargar(filepath.Join("frontend", ".env"))
	cfg := web.Config{
		SupabaseURL:  envfile.Texto("SUPABASE_URL", ""),
		AnonKey:      envfile.Texto("SUPABASE_ANON_KEY", ""),
		CookieSegura: envfile.Bool("COOKIE_SEGURA", false),
	}
	if cfg.SupabaseURL == "" || cfg.AnonKey == "" {
		log.Fatal("Falta configurar SUPABASE_URL y SUPABASE_ANON_KEY (variables de entorno o frontend/.env).")
	}
	servidor, err := web.NewServidor(cfg)
	if err != nil {
		log.Fatal(err)
	}
	direccion := ":" + envfile.Texto("PUERTO", "8080")
	log.Printf("Dashboard QA BIA en http://localhost%s", direccion)
	srv := &http.Server{
		Addr:              direccion,
		Handler:           servidor,
		ReadHeaderTimeout: 10 * time.Second,
		WriteTimeout:      60 * time.Second,
	}
	log.Fatal(srv.ListenAndServe())
}
