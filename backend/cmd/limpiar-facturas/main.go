// Comando limpiar-facturas: fuerza a reprocesar las visitas previas para volver
// a extraer la factura anterior con los patrones nuevos.
//
//  1. Busca en Supabase todas las visitas previas (VIPE).
//  2. Las saca de backend/state/actas_procesadas.json.
//  3. Saca sus codigos CO de backend/state/facturas_extraidas.json.
//  4. Resetea las columnas de factura en Supabase.
//
// El proximo run del QA las reprocesa. Ejecutar desde la raiz del repo:
//
//	go run ./backend/cmd/limpiar-facturas
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

	fmt.Println("Buscando todas las VIPE (visita previa) para reprocesar con nuevos patrones de factura...")
	actas, err := sb.Consultar(url.Values{
		"select": {"ot_id,ot_nombre,internal_bia_code,tipo_servicio,factura_anterior_estado,medidor_coincide_factura_anterior"},
		"or":     {"(tipo_servicio.ilike.*visita previa*,ot_nombre.ilike.VIPE_*)"},
	})
	if err != nil {
		fmt.Printf("ERROR consulta: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Total VIPE encontradas: %d\n", len(actas))
	imprimirDesglose(actas, "factura_anterior_estado", "estado_factura")
	if len(actas) == 0 {
		fmt.Println("Nada que limpiar.")
		return
	}

	otIDs, codigos := map[string]bool{}, map[string]bool{}
	for _, a := range actas {
		if id := dato.Texto(a["ot_id"]); id != "" {
			otIDs[id] = true
		}
		if co := dato.Texto(a["internal_bia_code"]); co != "" {
			codigos[co] = true
		}
	}
	for i, a := range actas {
		if i == 10 {
			fmt.Printf("  ... y %d mas\n", len(actas)-10)
			break
		}
		fmt.Printf("  - %s | CO=%s | estado=%s\n", dato.TextoCrudo(a["ot_nombre"]),
			dato.TextoCrudo(a["internal_bia_code"]), dato.TextoCrudo(a["factura_anterior_estado"]))
	}

	est := estado.New(cfg)
	// 1. Actas procesadas
	if antes, despues, existe, err := est.QuitarProcesadas(otIDs); err != nil {
		fmt.Printf("ERROR actas_procesadas.json: %v\n", err)
	} else if existe {
		fmt.Printf("actas_procesadas.json: %d -> %d (removidas %d)\n", antes, despues, antes-despues)
	}
	// 2. Cache de facturas
	if antes, despues, existe, err := est.QuitarFacturas(codigos); err != nil {
		fmt.Printf("ERROR facturas_extraidas.json: %v\n", err)
	} else if existe {
		fmt.Printf("facturas_extraidas.json: %d -> %d (removidas %d)\n", antes, despues, antes-despues)
	} else {
		fmt.Println("facturas_extraidas.json no existe (nada que limpiar).")
	}

	// 3. Columnas de factura en Supabase
	fmt.Println("Reseteando columnas de factura en Supabase...")
	reseteadas := 0
	for _, a := range actas {
		id := dato.Texto(a["ot_id"])
		if id == "" {
			continue
		}
		err := sb.ActualizarOT(id, map[string]any{
			"serial_medidor_factura_anterior":   nil,
			"medidor_coincide_factura_anterior": nil,
			"factura_anterior_estado":           nil,
		})
		if err != nil {
			fmt.Printf("  Error reseteando %s: %v\n", id, err)
			continue
		}
		reseteadas++
	}
	fmt.Printf("Supabase: %d actas reseteadas.\n", reseteadas)
	fmt.Println("\nListo. Disparar workflow QA BIA Automatico para reprocesarlas.")
}

// imprimirDesglose muestra cuantas filas hay por valor de una columna, de mayor a menor.
func imprimirDesglose(filas []dato.Objeto, columna, etiqueta string) {
	conteo := map[string]int{}
	var valores []string
	for _, f := range filas {
		v := dato.Texto(f[columna])
		if v == "" {
			v = "null"
		}
		if conteo[v] == 0 {
			valores = append(valores, v)
		}
		conteo[v]++
	}
	sort.SliceStable(valores, func(i, j int) bool { return conteo[valores[i]] > conteo[valores[j]] })
	for _, v := range valores {
		fmt.Printf("  - %s='%s': %d\n", etiqueta, v, conteo[v])
	}
}
