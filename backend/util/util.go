// Package util tiene utilidades compartidas sin dependencias de negocio.
package util

import (
	"regexp"
	"strings"
	"time"
)

// Ahora devuelve la hora local en formato "2006-01-02 15:04:05".
func Ahora() string {
	return time.Now().Format("2006-01-02 15:04:05")
}

// AhoraUTC devuelve la hora UTC.
func AhoraUTC() time.Time {
	return time.Now().UTC()
}

// AhoraUTCISO devuelve la hora UTC en ISO con microsegundos y sufijo Z,
// ej. 2026-05-21T10:00:00.123456Z.
func AhoraUTCISO() string {
	return AhoraUTC().Format("2006-01-02T15:04:05.000000") + "Z"
}

var reSeparadoresSerial = regexp.MustCompile(`[\s\v\-_/]`)

// NormalizarSerial quita espacios, guiones, guion bajo y barras, los ceros a la
// izquierda y pasa a mayusculas, para comparar seriales escritos distinto.
func NormalizarSerial(s string) string {
	if s == "" {
		return ""
	}
	return strings.ToUpper(strings.TrimLeft(reSeparadoresSerial.ReplaceAllString(s, ""), "0"))
}

// Av devuelve el primer valor no vacio de una fila del CSV de alcances, o "N/A".
func Av(fila map[string]string, columnas ...string) string {
	for _, col := range columnas {
		v := strings.TrimSpace(fila[col])
		if v != "" && v != "-" && v != "N/A" && v != "n/a" && v != "nan" {
			return v
		}
	}
	return "N/A"
}
