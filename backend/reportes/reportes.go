// Package reportes guarda un JSON local por acta auditada (backend/reportes_qa/,
// no se versiona).
package reportes

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

type reporte struct {
	FechaAuditoria     string      `json:"fecha_auditoria"`
	OT                 any         `json:"ot"`
	TipoServicio       any         `json:"tipo_servicio"`
	FechaEjecucion     any         `json:"fecha_ejecucion"`
	Direccion          any         `json:"direccion"`
	Empresa            any         `json:"empresa"`
	ORNorm             string      `json:"or_norm"`
	Planner            any         `json:"planner"`
	InternalBIACode    string      `json:"internal_bia_code"`
	EstadoApp          any         `json:"estado_app"`
	EstadoElectricista any         `json:"estado_electricista"`
	PDFURL             any         `json:"pdf_url"`
	ResultadoQA        dato.Objeto `json:"resultado_qa"`
}

func campo(acta map[string]string, clave string) any {
	if v, ok := acta[clave]; ok {
		return v
	}
	return nil
}

// Guardar escribe el reporte del acta y devuelve la ruta.
func Guardar(carpeta string, acta map[string]string, qa dato.Objeto) (string, error) {
	if err := os.MkdirAll(carpeta, 0o755); err != nil {
		return "", err
	}
	nombre, ok := acta["title"]
	if !ok {
		nombre, ok = acta["id"]
		if !ok {
			nombre = "sin_titulo"
		}
	}
	ahora := time.Now()
	ruta := filepath.Join(carpeta, fmt.Sprintf("%s_%s.json", ahora.Format("20060102_150405"), strings.ReplaceAll(nombre, "/", "-")))
	planner := qa["planner"]
	if planner == nil {
		planner = ""
	}
	r := reporte{
		FechaAuditoria:     ahora.Format("2006-01-02T15:04:05.000000"),
		OT:                 campo(acta, "title"),
		TipoServicio:       campo(acta, "Tipo de servicio"),
		FechaEjecucion:     campo(acta, "start"),
		Direccion:          campo(acta, "address"),
		Empresa:            campo(acta, "company_name"),
		ORNorm:             acta["OR_NORM"],
		Planner:            planner,
		InternalBIACode:    acta["internal_bia_code"],
		EstadoApp:          campo(acta, "status_app"),
		EstadoElectricista: campo(acta, "electrician_status_id"),
		PDFURL:             campo(acta, "act_pdf_url"),
		ResultadoQA:        qa,
	}
	data, err := dato.Codificar(r, true)
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(ruta, data, 0o644); err != nil {
		return "", err
	}
	abs, _ := filepath.Abs(ruta)
	fmt.Printf("  Reporte: %s\n", abs)
	return ruta, nil
}
