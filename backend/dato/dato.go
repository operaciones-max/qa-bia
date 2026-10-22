// Package dato ayuda a leer y modificar el JSON libre que devuelve la IA
// (map[string]any), con la misma semantica que tenia el codigo en Python:
// valores "falsy" (nil, "", 0, false, mapa o lista vacia) cuentan como ausentes.
//
// Los numeros se decodifican como json.Number para que se reescriban tal cual.
package dato

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strings"
)

// Objeto es un objeto JSON decodificado.
type Objeto = map[string]any

// Decodificar parsea JSON conservando los numeros como json.Number.
func Decodificar(data []byte, destino any) error {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	return dec.Decode(destino)
}

// Mapa devuelve v si es un objeto JSON; si no, nil (leer de un mapa nil es seguro).
func Mapa(v any) Objeto {
	m, _ := v.(Objeto)
	return m
}

// Hijo devuelve m[clave] como objeto, o nil.
func Hijo(m Objeto, clave string) Objeto { return Mapa(m[clave]) }

// HijoOCrear devuelve m[clave] como objeto; si no es un objeto, crea uno vacio y lo guarda.
func HijoOCrear(m Objeto, clave string) Objeto {
	if h := Mapa(m[clave]); h != nil {
		return h
	}
	h := Objeto{}
	m[clave] = h
	return h
}

// Verdadero replica la "verdad" de Python.
func Verdadero(v any) bool {
	switch x := v.(type) {
	case nil:
		return false
	case bool:
		return x
	case string:
		return x != ""
	case json.Number:
		f, err := x.Float64()
		return err != nil || f != 0
	case float64:
		return x != 0
	case int:
		return x != 0
	case Objeto:
		return len(x) > 0
	case []any:
		return len(x) > 0
	case []string:
		return len(x) > 0
	default:
		return true
	}
}

// Texto replica `str(v or "")` de Python: "" si v es falsy, si no su texto.
func Texto(v any) string {
	if !Verdadero(v) {
		return ""
	}
	return TextoCrudo(v)
}

// TextoCrudo replica `str(v)` de Python (None -> "None").
func TextoCrudo(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case string:
		return x
	case json.Number:
		return x.String()
	case bool:
		if x {
			return "True"
		}
		return "False"
	default:
		return fmt.Sprint(x)
	}
}

// TextoLimpio es strings.TrimSpace(Texto(v)).
func TextoLimpio(v any) string { return strings.TrimSpace(Texto(v)) }

// Lista devuelve v como lista, o nil.
func Lista(v any) []any {
	switch x := v.(type) {
	case []any:
		return x
	case []string:
		l := make([]any, len(x))
		for i, s := range x {
			l[i] = s
		}
		return l
	}
	return nil
}

// Textos devuelve los elementos de una lista como texto (`item or ""`).
func Textos(v any) []string {
	var out []string
	for _, item := range Lista(v) {
		out = append(out, Texto(item))
	}
	return out
}

// EsFalse indica `v is False`.
func EsFalse(v any) bool { b, ok := v.(bool); return ok && !b }

// EsTrue indica `v is True`.
func EsTrue(v any) bool { b, ok := v.(bool); return ok && b }

// TextosAny convierte []string a []any para guardarlo en un Objeto.
func TextosAny(l []string) []any {
	out := make([]any, 0, len(l))
	for _, s := range l {
		out = append(out, s)
	}
	return out
}

// Codificar serializa como lo hacia json.dumps(ensure_ascii=False): sin escapar HTML.
func Codificar(v any, indentar bool) ([]byte, error) {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	if indentar {
		enc.SetIndent("", "  ")
	}
	if err := enc.Encode(v); err != nil {
		return nil, err
	}
	return bytes.TrimRight(buf.Bytes(), "\n"), nil
}
