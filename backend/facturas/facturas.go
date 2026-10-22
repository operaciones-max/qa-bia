// Package facturas extrae el serial del medidor de la factura anterior del
// cliente: primero con expresiones regulares por comercializador y, si no
// alcanza, con Claude.
package facturas

import (
	"context"
	"fmt"
	"regexp"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/ia"
	"github.com/operaciones-max/qa-bia/backend/pdf"
)

// Patrones de serial de medidor por OR/comercializador, aprendidos el
// 2026-05-15. Se prueban en orden y gana la primera coincidencia.
var patronesSerial = []struct {
	re     *regexp.Regexp
	nombre string
}{
	{regexp.MustCompile(`(?i)No\.\s*Medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "Enel"},
	{regexp.MustCompile(`(?i)N[úu]mero\s+de\s+Medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "Air-e/Aire"},
	{regexp.MustCompile(`(?i)Medidor\s+No\.?\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "Enel X"},
	{regexp.MustCompile(`(?i)C[óo]digo\s+(?:del\s+)?medidor\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "ERCO"},
	{regexp.MustCompile(`(?i)Medidor\s+Activa\s*:?\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "CENS"},
	{regexp.MustCompile(`(?i)\bMedidor\s*\n\s*([0-9][0-9A-Z\-]{3,19})`), "Celsia (cuadro naranja)"},
	{regexp.MustCompile(`(?i)\bMedidor\s*:\s*([0-9A-Z][0-9A-Z\-]{3,19})`), "EPM/generico"},
}

var (
	reAnclaAfinia  = regexp.MustCompile(`(?i)Datos\s+de\s+la\s+Factura`)
	reSerialAfinia = regexp.MustCompile(`(?i)Medidor\s*[:\n]?\s*([0-9][0-9A-Z\-]{3,19})`)
	reSufijo       = regexp.MustCompile(`-[A-Z][A-Z0-9]*$`)
)

// limpiarSerial quita sufijos tipo '-MC983' o '-V2', que son codigos de
// version/modelo y no parte del serial.
func limpiarSerial(s string) string {
	return strings.TrimSpace(reSufijo.ReplaceAllString(s, ""))
}

func tieneDigito(s string) bool { return strings.ContainsAny(s, "0123456789") }

// serialContextual busca el ancla y despues el serial dentro de los siguientes `ventana` caracteres.
func serialContextual(texto string, ancla, serial *regexp.Regexp, ventana int) string {
	loc := ancla.FindStringIndex(texto)
	if loc == nil {
		return ""
	}
	resto := []rune(texto[loc[1]:])
	if len(resto) > ventana {
		resto = resto[:ventana]
	}
	m := serial.FindStringSubmatch(string(resto))
	if m == nil {
		return ""
	}
	s := limpiarSerial(strings.ToUpper(strings.TrimSpace(m[1])))
	if s != "" && tieneDigito(s) {
		return s
	}
	return ""
}

// SerialPorPatron busca el serial con los patrones conocidos. Devuelve el serial
// y el nombre del patron, o "" si ninguno aplica.
func SerialPorPatron(texto string) (string, string) {
	if texto == "" {
		return "", ""
	}
	// AFINIA: el serial esta dentro del recuadro 'Datos de la Factura' (gana sobre los lineales)
	if s := serialContextual(texto, reAnclaAfinia, reSerialAfinia, 800); s != "" {
		return s, "AFINIA (Datos de la Factura)"
	}
	for _, p := range patronesSerial {
		if m := p.re.FindStringSubmatch(texto); m != nil {
			s := limpiarSerial(strings.ToUpper(strings.TrimSpace(m[1])))
			if s != "" && tieneDigito(s) {
				return s, p.nombre
			}
		}
	}
	return "", ""
}

// Resultado de leer una factura anterior.
type Resultado struct {
	Serial  string // "" si no se encontro
	Express *bool  // nil si no se pudo leer el PDF
	Estado  string // "regex_<patron>", "ok", "pdf_vacio", "error_descarga: ...", etc.
}

// ExtraerSerial descarga la factura y extrae el serial del medidor y si es "express".
func ExtraerSerial(ctx context.Context, claude *ia.Cliente, url string) Resultado {
	pdfBytes, err := pdf.Descargar(url)
	if err != nil {
		return Resultado{Estado: fmt.Sprintf("error_descarga: %v", err)}
	}
	texto, err := pdf.Texto(pdfBytes)
	if err != nil {
		return Resultado{Estado: fmt.Sprintf("error_pdf: %v", err)}
	}
	if strings.TrimSpace(texto) == "" {
		return Resultado{Estado: "pdf_vacio"}
	}

	express := strings.Contains(strings.ToLower(texto), "express")

	// 1er intento: regex por comercializador (gratis, sin tokens)
	if serial, patron := SerialPorPatron(texto); serial != "" {
		fmt.Printf("     Serial extraido por regex (%s): %s\n", patron, serial)
		return Resultado{Serial: serial, Express: &express, Estado: "regex_" + patron}
	}

	// 2do intento: Claude
	serial, estado := claude.ExtraerSerialDeFactura(ctx, texto)
	return Resultado{Serial: serial, Express: &express, Estado: estado}
}
