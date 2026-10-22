// Comando qa: corre el QA automatizado de actas.
//
// Ejecutar desde la raiz del repo:  go run ./backend/cmd/qa
package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/pipeline"
)

func main() {
	cfg := config.Cargar(filepath.Join("backend", ".env"))
	if cfg.AnthropicAPIKey == "" {
		fmt.Fprintln(os.Stderr, "ERROR: falta ANTHROPIC_API_KEY (variable de entorno o backend/.env).")
		os.Exit(1)
	}
	pipeline.New(cfg).Main(context.Background())
}
