// Comando limpiar-pqr-vico-emerg: fuerza a reprocesar las PQR, visitas
// conjuntas y emergencias (que se analizan con vision de las actas fisicas).
// Las saca de backend/state/actas_procesadas.json para que el proximo run del
// QA las vuelva a analizar. Ejecutar desde la raiz del repo:
//
//	go run ./backend/cmd/limpiar-pqr-vico-emerg
package main

import (
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"sort"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/estado"
	"github.com/operaciones-max/qa-bia/backend/supabase"
)

func main() {
	cfg := config.Cargar(filepath.Join("backend", ".env"))
	sb := supabase.New(cfg)
	if sb == nil {
		fmt.Println("ERROR: SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY requeridos")
		os.Exit(1)
	}

	fmt.Println("Buscando PQR/VICO/Emergencia para reprocesar con vision...")
	actas, err := sb.Consultar(url.Values{
		"select":        {"ot_id,ot_nombre,internal_bia_code,tipo_servicio,procesado_en"},
		"tipo_servicio": {"in.(PQR,Emergencia,Visita conjunta)"},
	})
	if err != nil {
		fmt.Printf("ERROR consulta: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Total PQR/VICO/Emergencia encontradas: %d\n", len(actas))

	conteo := map[string]int{}
	var tipos []string
	for _, a := range actas {
		t := dato.Texto(a["tipo_servicio"])
		if t == "" {
			t = "null"
		}
		if conteo[t] == 0 {
			tipos = append(tipos, t)
		}
		conteo[t]++
	}
	sort.SliceStable(tipos, func(i, j int) bool { return conteo[tipos[i]] > conteo[tipos[j]] })
	for _, t := range tipos {
		fmt.Printf("  - tipo='%s': %d\n", t, conteo[t])
	}
	if len(actas) == 0 {
		fmt.Println("Nada que limpiar.")
		return
	}

	otIDs := map[string]bool{}
	for _, a := range actas {
		if id := dato.Texto(a["ot_id"]); id != "" {
			otIDs[id] = true
		}
	}
	if antes, despues, existe, err := estado.New(cfg).QuitarProcesadas(otIDs); err != nil {
		fmt.Printf("ERROR actas_procesadas.json: %v\n", err)
	} else if existe {
		fmt.Printf("actas_procesadas.json: %d -> %d (removidas %d)\n", antes, despues, antes-despues)
	}
	fmt.Println("\nListo. Disparar workflow QA BIA Automatico para reprocesar con vision.")
}
