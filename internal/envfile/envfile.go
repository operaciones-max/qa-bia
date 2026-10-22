// Package envfile carga variables de entorno desde un archivo .env simple
// (CLAVE=valor), sin pisar las que ya estan definidas. Lo usan backend y frontend.
package envfile

import (
	"bufio"
	"os"
	"strings"
)

// Cargar lee el archivo si existe; las variables ya definidas tienen prioridad.
func Cargar(ruta string) {
	if ruta == "" {
		return
	}
	f, err := os.Open(ruta)
	if err != nil {
		return
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		linea := strings.TrimSpace(sc.Text())
		if linea == "" || strings.HasPrefix(linea, "#") || !strings.Contains(linea, "=") {
			continue
		}
		clave, valor, _ := strings.Cut(linea, "=")
		clave = strings.TrimSpace(clave)
		if _, existe := os.LookupEnv(clave); existe {
			continue
		}
		os.Setenv(clave, strings.Trim(strings.Trim(strings.TrimSpace(valor), `"`), `'`))
	}
}

// Texto devuelve la variable sin espacios, o el valor por defecto si esta vacia.
func Texto(nombre, porDefecto string) string {
	if v := strings.TrimSpace(os.Getenv(nombre)); v != "" {
		return v
	}
	return porDefecto
}

// Bool interpreta 1/true/si/yes como verdadero.
func Bool(nombre string, porDefecto bool) bool {
	v := strings.ToLower(strings.TrimSpace(os.Getenv(nombre)))
	if v == "" {
		return porDefecto
	}
	return v == "1" || v == "true" || v == "si" || v == "sí" || v == "yes"
}
