package estado

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// objetoOrdenado es un objeto JSON que conserva el orden de sus claves, como los
// dict de Python. Asi los archivos de estado no cambian de orden al reescribirse.
type objetoOrdenado struct {
	claves  []string
	valores map[string]json.RawMessage
}

func nuevoObjetoOrdenado() *objetoOrdenado {
	return &objetoOrdenado{valores: map[string]json.RawMessage{}}
}

func (o *objetoOrdenado) Get(clave string) (json.RawMessage, bool) {
	v, ok := o.valores[clave]
	return v, ok
}

// Set reemplaza el valor (manteniendo su posicion) o agrega la clave al final.
func (o *objetoOrdenado) Set(clave string, valor json.RawMessage) {
	if _, existe := o.valores[clave]; !existe {
		o.claves = append(o.claves, clave)
	}
	o.valores[clave] = valor
}

func (o *objetoOrdenado) Delete(clave string) bool {
	if _, existe := o.valores[clave]; !existe {
		return false
	}
	delete(o.valores, clave)
	for i, c := range o.claves {
		if c == clave {
			o.claves = append(o.claves[:i], o.claves[i+1:]...)
			break
		}
	}
	return true
}

func (o *objetoOrdenado) Len() int { return len(o.claves) }

func (o *objetoOrdenado) Claves() []string { return append([]string(nil), o.claves...) }

func (o *objetoOrdenado) UnmarshalJSON(data []byte) error {
	dec := json.NewDecoder(bytes.NewReader(data))
	tok, err := dec.Token()
	if err != nil {
		return err
	}
	if d, ok := tok.(json.Delim); !ok || d != '{' {
		return fmt.Errorf("se esperaba un objeto JSON")
	}
	o.claves = nil
	o.valores = map[string]json.RawMessage{}
	for dec.More() {
		tok, err := dec.Token()
		if err != nil {
			return err
		}
		clave, _ := tok.(string)
		var valor json.RawMessage
		if err := dec.Decode(&valor); err != nil {
			return err
		}
		o.Set(clave, valor)
	}
	_, err = dec.Token()
	return err
}

func (o *objetoOrdenado) MarshalJSON() ([]byte, error) {
	var buf bytes.Buffer
	buf.WriteByte('{')
	for i, clave := range o.claves {
		if i > 0 {
			buf.WriteByte(',')
		}
		k, err := json.Marshal(clave)
		if err != nil {
			return nil, err
		}
		buf.Write(k)
		buf.WriteByte(':')
		buf.Write(o.valores[clave])
	}
	buf.WriteByte('}')
	return buf.Bytes(), nil
}
