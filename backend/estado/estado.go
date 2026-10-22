// Package estado guarda el avance del QA en archivos JSON (backend/state/):
// actas procesadas, visitas previas, alcances procesados, cache de facturas
// anteriores y el cooldown del LLM.
package estado

import (
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/util"
)

// Estado lee y escribe los archivos de estado de una corrida.
type Estado struct {
	cfg config.Config
}

func New(cfg config.Config) *Estado {
	os.MkdirAll(cfg.StateDir, 0o755)
	return &Estado{cfg: cfg}
}

// ---------------------------------------------------------------- listas

func leerLista(ruta string) []string {
	data, err := os.ReadFile(ruta)
	if err != nil {
		return nil
	}
	var l []string
	json.Unmarshal(data, &l)
	return l
}

func agregarALista(ruta, valor string) error {
	l := leerLista(ruta)
	for _, x := range l {
		if x == valor {
			return escribirJSON(ruta, l)
		}
	}
	return escribirJSON(ruta, append(l, valor))
}

// Procesadas devuelve los ids de actas ya auditadas.
func (e *Estado) Procesadas() []string { return leerLista(e.cfg.ArchivoProcesados) }

// MarcarProcesada agrega un id de acta a la lista de procesadas.
func (e *Estado) MarcarProcesada(actaID string) error {
	return agregarALista(e.cfg.ArchivoProcesados, actaID)
}

// AlcancesProcesados devuelve los ids de alcances ya registrados.
func (e *Estado) AlcancesProcesados() []string { return leerLista(e.cfg.ArchivoAlcancesProcesados) }

// MarcarAlcanceProcesado agrega un id de alcance a la lista.
func (e *Estado) MarcarAlcanceProcesado(alcanceID string) error {
	return agregarALista(e.cfg.ArchivoAlcancesProcesados, alcanceID)
}

// ---------------------------------------------------------------- objetos

func leerObjeto(ruta string) *objetoOrdenado {
	o := nuevoObjetoOrdenado()
	if data, err := os.ReadFile(ruta); err == nil {
		if err := json.Unmarshal(data, o); err != nil {
			return nuevoObjetoOrdenado()
		}
	}
	return o
}

func guardarEnObjeto(ruta, clave string, valor any) error {
	raw, err := dato.Codificar(valor, false)
	if err != nil {
		return err
	}
	o := leerObjeto(ruta)
	o.Set(clave, raw)
	return escribirJSON(ruta, o)
}

// VisitaPrevia son los hallazgos de una visita previa, para compararlos con el alcance.
type VisitaPrevia struct {
	OTNombre                   string `json:"ot_nombre"`
	FechaProcesada             string `json:"fecha_procesada"`
	TipoMedida                 any    `json:"tipo_medida"`
	FactorMedida               any    `json:"factor_medida"`
	MedidorEncontrado          any    `json:"medidor_encontrado"`
	MedidorEncSerie            any    `json:"medidor_enc_serie"`
	TCsEncontrados             any    `json:"tcs_encontrados"`
	TPsEncontrados             any    `json:"tps_encontrados"`
	TecnicoNombre              any    `json:"tecnico_nombre"`
	TecnicoEmpresa             any    `json:"tecnico_empresa"`
	ContratistaNombre          any    `json:"contratista_nombre"`
	ObservacionTecnicoVerbatim any    `json:"observacion_tecnico_verbatim"`
}

// VisitasPrevias devuelve los codigos CO que tienen una visita previa guardada.
func (e *Estado) VisitasPrevias() map[string]bool {
	o := leerObjeto(e.cfg.ArchivoVisitasPrevias)
	out := map[string]bool{}
	for _, c := range o.Claves() {
		out[c] = true
	}
	return out
}

// GuardarVisitaPrevia guarda (o reemplaza) la visita previa de un codigo CO.
func (e *Estado) GuardarVisitaPrevia(codigoCO string, vp VisitaPrevia) error {
	return guardarEnObjeto(e.cfg.ArchivoVisitasPrevias, codigoCO, vp)
}

// FacturaExtraida es el resultado cacheado de leer la factura anterior de un CO.
type FacturaExtraida struct {
	Serial  *string `json:"serial"`
	Express *bool   `json:"express"`
	URL     string  `json:"url"`
	Estado  string  `json:"estado"`
	Fecha   string  `json:"fecha"`
}

// FacturaCacheada devuelve la factura cacheada de un CO, si existe.
func (e *Estado) FacturaCacheada(codigoCO string) (FacturaExtraida, bool) {
	raw, ok := leerObjeto(e.cfg.ArchivoFacturasExtraidas).Get(codigoCO)
	if !ok {
		return FacturaExtraida{}, false
	}
	var f FacturaExtraida
	json.Unmarshal(raw, &f)
	return f, true
}

// GuardarFactura guarda en cache la factura leida de un CO.
func (e *Estado) GuardarFactura(codigoCO string, f FacturaExtraida) error {
	return guardarEnObjeto(e.cfg.ArchivoFacturasExtraidas, codigoCO, f)
}

// ---------------------------------------------------------------- cooldown del LLM

// Cooldown indica hasta cuando no se llama a Claude tras un limite de uso.
type Cooldown struct {
	Until    string `json:"until"`
	Razon    string `json:"razon"`
	Activado string `json:"activado"`
}

const formatoCooldown = "2006-01-02T15:04:05"

// CooldownActivo devuelve el cooldown vigente, o nil (y borra el archivo si ya vencio).
func (e *Estado) CooldownActivo() *Cooldown {
	data, err := os.ReadFile(e.cfg.ArchivoCooldownLLM)
	if err != nil {
		return nil
	}
	var c Cooldown
	if err := json.Unmarshal(data, &c); err != nil {
		return nil
	}
	hasta, err := time.Parse(formatoCooldown, strings.TrimSuffix(c.Until, "Z"))
	if err != nil {
		return nil
	}
	if !util.AhoraUTC().Before(hasta) {
		os.Remove(e.cfg.ArchivoCooldownLLM)
		return nil
	}
	return &c
}

var reReintentarEn = regexp.MustCompile(`(?:try again in|retry.*?in|retry_delay.*?seconds:)\s*(\d+\.?\d*)`)

// ActivarCooldown pausa las llamadas a Claude segun el error de limite recibido:
// hasta el dia siguiente si es cuota diaria, o los segundos que indique el error.
func (e *Estado) ActivarCooldown(msgError string) Cooldown {
	fmt.Printf("  [cooldown] Error original Claude: %s\n", recortar(msgError, 400))
	msg := strings.ToLower(msgError)
	ahora := util.AhoraUTC()
	var hasta time.Time
	var razon string
	if strings.Contains(msg, "per day") || strings.Contains(msg, "tokens per day") || strings.Contains(msg, "requests per day") {
		hasta = time.Date(ahora.Year(), ahora.Month(), ahora.Day(), 0, 5, 0, 0, time.UTC).AddDate(0, 0, 1)
		razon = "daily_quota"
	} else {
		segundos := 65
		if m := reReintentarEn.FindStringSubmatch(msgError); m != nil {
			if f, err := strconv.ParseFloat(m[1], 64); err == nil {
				segundos = int(f) + 5
			}
		}
		hasta = ahora.Add(time.Duration(segundos) * time.Second)
		razon = "per_minute"
	}
	c := Cooldown{
		Until:    hasta.Format(formatoCooldown) + "Z",
		Razon:    razon,
		Activado: ahora.Format(formatoCooldown) + "Z",
	}
	escribirJSON(e.cfg.ArchivoCooldownLLM, c)
	return c
}

// ---------------------------------------------------------------- utilidades

// escribirJSON escribe con indentacion de 2 espacios y sin escapar acentos ni HTML,
// igual que json.dump(..., ensure_ascii=False, indent=2) en Python.
func escribirJSON(ruta string, v any) error {
	data, err := dato.Codificar(v, true)
	if err != nil {
		return err
	}
	return os.WriteFile(ruta, data, 0o644)
}

func recortar(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}

// ---------------------------------------------------------------- limpieza (scripts)

// QuitarProcesadas saca ids de la lista de actas procesadas para que se
// reprocesen. Devuelve cuantas habia antes y despues; existe=false si no hay archivo.
func (e *Estado) QuitarProcesadas(ids map[string]bool) (antes, despues int, existe bool, err error) {
	if _, err := os.Stat(e.cfg.ArchivoProcesados); err != nil {
		return 0, 0, false, nil
	}
	l := leerLista(e.cfg.ArchivoProcesados)
	quedan := []string{}
	for _, id := range l {
		if !ids[id] {
			quedan = append(quedan, id)
		}
	}
	return len(l), len(quedan), true, escribirJSON(e.cfg.ArchivoProcesados, quedan)
}

// QuitarFacturas saca codigos CO del cache de facturas extraidas.
func (e *Estado) QuitarFacturas(codigos map[string]bool) (antes, despues int, existe bool, err error) {
	if _, err := os.Stat(e.cfg.ArchivoFacturasExtraidas); err != nil {
		return 0, 0, false, nil
	}
	o := leerObjeto(e.cfg.ArchivoFacturasExtraidas)
	antes = o.Len()
	for co := range codigos {
		o.Delete(co)
	}
	return antes, o.Len(), true, escribirJSON(e.cfg.ArchivoFacturasExtraidas, o)
}
