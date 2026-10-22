// Package metabase lee las fuentes de datos desde Metabase: actas, inventario
// WMS, alcances de ingenieria, facturas anteriores (HubSpot) y el estado de
// cierre de App Ops.
package metabase

import (
	"encoding/csv"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/util"
)

const (
	preguntaFacturas = 71842 // hubspot-general: URL de la factura anterior + contract_id
	preguntaAppOps   = 15673 // BD Analisis App Ops: estado de cierre real
)

// Fila es una fila de un CSV, por nombre de columna.
type Fila = map[string]string

// Metabase lee las preguntas de Metabase de la configuracion.
type Metabase struct {
	cfg  config.Config
	http *http.Client
}

func New(cfg config.Config) *Metabase {
	return &Metabase{cfg: cfg, http: &http.Client{}}
}

// ---------------------------------------------------------------- CSV

var errUTF8 = errors.New("el CSV no es UTF-8 valido")

// leerCSV parsea un CSV con encabezado, como csv.DictReader de Python.
// Con reemplazar=true los bytes invalidos se reemplazan en vez de fallar.
func leerCSV(data []byte, reemplazar bool) ([]string, []Fila, error) {
	texto := string(data)
	if !utf8.ValidString(texto) {
		if !reemplazar {
			return nil, nil, errUTF8
		}
		texto = strings.ToValidUTF8(texto, "�")
	}
	r := csv.NewReader(strings.NewReader(texto))
	r.FieldsPerRecord = -1
	r.LazyQuotes = true
	encabezado, err := r.Read()
	if err == io.EOF {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}
	var filas []Fila
	for {
		registro, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, nil, err
		}
		fila := make(Fila, len(encabezado))
		for i, col := range encabezado {
			if i < len(registro) {
				fila[col] = registro[i]
			}
		}
		filas = append(filas, fila)
	}
	return encabezado, filas, nil
}

func (m *Metabase) get(url string, timeout time.Duration) ([]byte, error) {
	cli := *m.http
	cli.Timeout = timeout
	resp, err := cli.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, errorHTTP(resp.StatusCode, url)
	}
	return io.ReadAll(resp.Body)
}

// consultarPregunta ejecuta una pregunta de Metabase por API (requiere METABASE_API_KEY).
func (m *Metabase) consultarPregunta(id int) (int, string, []byte, error) {
	url := fmt.Sprintf("%s/api/card/%d/query/csv", m.cfg.MetabaseBaseURL, id)
	fmt.Printf("  POST %s\n", url)
	req, _ := http.NewRequest(http.MethodPost, url, nil)
	req.Header.Set("X-API-KEY", m.cfg.MetabaseAPIKey)
	cli := *m.http
	cli.Timeout = 60 * time.Second
	resp, err := cli.Do(req)
	if err != nil {
		return 0, "", nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	return resp.StatusCode, resp.Header.Get("Content-Type"), data, err
}

// detectarColumna devuelve la primera columna cuyo nombre normalizado coincide con un candidato.
func detectarColumna(columnas []string, candidatos ...string) string {
	norm := map[string]string{}
	for _, c := range columnas {
		norm[strings.ReplaceAll(strings.TrimSpace(strings.ToLower(c)), " ", "_")] = c
	}
	for _, cand := range candidatos {
		if c, ok := norm[cand]; ok {
			return c
		}
	}
	return ""
}

func recortar(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}

// ---------------------------------------------------------------- facturas anteriores

// Factura es la factura anterior de un codigo CO.
type Factura struct {
	URL        string
	ContractID string
}

// FacturasAnteriores devuelve, por codigo CO, la URL de la factura anterior y el
// contract_id (pregunta 71842). Sin METABASE_API_KEY devuelve un mapa vacio.
func (m *Metabase) FacturasAnteriores() map[string]Factura {
	if m.cfg.MetabaseAPIKey == "" {
		fmt.Println("  WARN: METABASE_API_KEY no configurada — sin validacion factura anterior")
		return map[string]Factura{}
	}
	status, ct, data, err := m.consultarPregunta(preguntaFacturas)
	if err != nil {
		fmt.Printf("  ERROR cargando facturas anteriores: %v\n", err)
		return map[string]Factura{}
	}
	fmt.Printf("  Status: %d | Content-Type: %s | size: %d bytes\n", status, ct, len(data))
	if status != 200 {
		fmt.Printf("  Respuesta del servidor: %s\n", recortar(string(data), 300))
		return map[string]Factura{}
	}
	if !strings.Contains(ct, "csv") && !strings.Contains(ct, "text/plain") {
		fmt.Printf("  WARN: Content-Type inesperado. Primeros 200 chars: %s\n", recortar(string(data), 200))
	}
	columnas, filas, err := leerCSV(data, false)
	if err != nil {
		fmt.Printf("  ERROR cargando facturas anteriores: %v\n", err)
		return map[string]Factura{}
	}
	resultado := map[string]Factura{}
	if len(filas) == 0 {
		fmt.Printf("  Hubspot-general: 0 filas | 0 CO unicos | 0 con URL factura | 0 con contract_id.\n")
		return resultado
	}
	fmt.Printf("  Columnas CSV: %q\n", columnas)
	colCodigo := detectarColumna(columnas, "internal_bia_code", "codigo_bia", "bia_code")
	colURL := detectarColumna(columnas, "factura_anterior", "invoice_document_url", "factura_url", "url_factura", "invoice_url")
	colContrato := detectarColumna(columnas, "contract_id", "contractid", "id_contrato")
	fmt.Printf("  Columnas detectadas: code='%s' url='%s' contract_id='%s'\n", colCodigo, colURL, colContrato)
	if colCodigo == "" {
		fmt.Println("  ERROR: no se detecto columna de codigo_bia/internal_bia_code")
		return map[string]Factura{}
	}
	for _, fila := range filas {
		co := strings.TrimSpace(fila[colCodigo])
		if co == "" {
			continue
		}
		url := ""
		if colURL != "" {
			url = strings.TrimSpace(fila[colURL])
		}
		contrato := ""
		if colContrato != "" {
			// Metabase exporta numeros como "17657.0"
			contrato = strings.TrimSuffix(strings.TrimSpace(fila[colContrato]), ".0")
		}
		f := resultado[co]
		if url != "" && f.URL == "" {
			f.URL = url
		}
		if contrato != "" && f.ContractID == "" {
			f.ContractID = contrato
		}
		resultado[co] = f
	}
	conURL, conContrato := 0, 0
	for _, f := range resultado {
		if f.URL != "" {
			conURL++
		}
		if f.ContractID != "" {
			conContrato++
		}
	}
	fmt.Printf("  Hubspot-general: %d filas | %d CO unicos | %d con URL factura | %d con contract_id.\n",
		len(filas), len(resultado), conURL, conContrato)
	return resultado
}

// ---------------------------------------------------------------- estado App Ops

// EstadoAppOps devuelve el electrician_status_id actual por id de OT y por titulo
// (pregunta 15673). No se usa el codigo CO porque mezcla OTs distintas de una cuenta.
func (m *Metabase) EstadoAppOps() (porID, porTitulo map[string]string) {
	porID, porTitulo = map[string]string{}, map[string]string{}
	if m.cfg.MetabaseAPIKey == "" {
		return
	}
	status, _, data, err := m.consultarPregunta(preguntaAppOps)
	if err != nil {
		fmt.Printf("  ERROR cargando estado app ops: %v\n", err)
		return
	}
	fmt.Printf("  Status: %d | size: %d bytes\n", status, len(data))
	if status != 200 {
		return
	}
	columnas, filas, err := leerCSV(data, false)
	if err != nil {
		fmt.Printf("  ERROR cargando estado app ops: %v\n", err)
		return map[string]string{}, map[string]string{}
	}
	if len(filas) > 0 {
		fmt.Printf("  Columnas App Ops (15673): %q\n", columnas)
	}
	colID := detectarColumna(columnas, "id", "ot_id")
	colTitulo := detectarColumna(columnas, "title", "ot_nombre")
	colEstado := detectarColumna(columnas, "electrician_status_id", "electrician_status", "estado_electricista", "status_id")
	if len(filas) > 0 {
		fmt.Printf("  Columnas detectadas: id='%s' title='%s' status='%s'\n", colID, colTitulo, colEstado)
		if colEstado == "" {
			fmt.Println("  ERROR: no se detecto columna de status en 15673")
			return map[string]string{}, map[string]string{}
		}
	}
	for _, fila := range filas {
		estado := strings.TrimSpace(fila[colEstado])
		if estado == "" {
			continue
		}
		if colID != "" {
			if id := strings.TrimSpace(fila[colID]); id != "" {
				porID[id] = estado
			}
		}
		if colTitulo != "" {
			if t := strings.TrimSpace(fila[colTitulo]); t != "" {
				porTitulo[t] = estado
			}
		}
	}
	fmt.Printf("  App Ops cargado: %d OTs por ID | %d OTs por Title.\n", len(porID), len(porTitulo))
	return porID, porTitulo
}

// ---------------------------------------------------------------- inventario WMS

// Equipo es un equipo asignado o instalado en WMS.
type Equipo struct {
	Serial string `json:"serial"`
	Marca  string `json:"marca"`
	Estado string `json:"estado"`
}

// EquiposWMS son los equipos de un codigo CO en WMS.
type EquiposWMS struct {
	Medidor *Equipo  `json:"medidor"`
	TCs     []Equipo `json:"tcs"`
	TPs     []Equipo `json:"tps"`
}

// InventarioWMS devuelve los equipos ASIGNADOS o INSTALADOS por codigo CO.
func (m *Metabase) InventarioWMS() map[string]*EquiposWMS {
	data, err := m.get(m.cfg.WMSCSVURL, 30*time.Second)
	var filas []Fila
	if err == nil {
		_, filas, err = leerCSV(data, false)
	}
	if err != nil {
		fmt.Printf("  ERROR WMS: %v\n", err)
		fmt.Println("  Continuando sin validacion de medidor.")
		return map[string]*EquiposWMS{}
	}
	wms := map[string]*EquiposWMS{}
	for _, fila := range filas {
		codigo := strings.TrimSpace(fila["Bia Code"])
		tipo := strings.ToLower(strings.TrimSpace(fila["Tipo Sku"]))
		estado := strings.ToUpper(strings.TrimSpace(fila["Estado"]))
		serial := strings.TrimSpace(fila["Serial"])
		marca := strings.TrimSpace(fila["Marca"])
		if codigo == "" || serial == "" || (estado != "ASIGNADO" && estado != "INSTALADO") {
			continue
		}
		e := wms[codigo]
		if e == nil {
			e = &EquiposWMS{TCs: []Equipo{}, TPs: []Equipo{}}
			wms[codigo] = e
		}
		item := Equipo{Serial: serial, Marca: marca, Estado: estado}
		switch {
		case tipo == "medidor":
			e.Medidor = &item
		case strings.Contains(tipo, "transformador de corriente"):
			e.TCs = append(e.TCs, item)
		case strings.Contains(tipo, "transformador de potencial") || strings.Contains(tipo, "transformador de potencia"):
			e.TPs = append(e.TPs, item)
		}
	}
	medidores, tcs, tps := 0, 0, 0
	for _, e := range wms {
		if e.Medidor != nil {
			medidores++
		}
		tcs += len(e.TCs)
		tps += len(e.TPs)
	}
	fmt.Printf("  WMS cargado: %d medidores, %d TCs, %d TPs.\n", medidores, tcs, tps)
	return wms
}

// ---------------------------------------------------------------- alcances

// Alcances son los alcances de ingenieria INST mas recientes por codigo CO, en el
// orden en que cada codigo aparece por primera vez en el CSV.
type Alcances struct {
	porCO map[string]Fila
	orden []string
}

// Get devuelve el alcance de un codigo CO, o nil.
func (a Alcances) Get(codigoCO string) Fila { return a.porCO[codigoCO] }

// Codigos devuelve los codigos CO en orden.
func (a Alcances) Codigos() []string { return a.orden }

// Len devuelve la cantidad de codigos con alcance.
func (a Alcances) Len() int { return len(a.orden) }

// Alcances devuelve, por codigo CO, el alcance de ingenieria INST mas reciente.
func (m *Metabase) Alcances() Alcances {
	vacio := Alcances{porCO: map[string]Fila{}}
	data, err := m.get(m.cfg.AlcancesCSVURL, 30*time.Second)
	var filas []Fila
	if err == nil {
		_, filas, err = leerCSV(data, true)
	}
	if err != nil {
		fmt.Printf("  ERROR alcances: %v\n", err)
		return vacio
	}
	alcances := vacio
	for _, fila := range filas {
		co := strings.TrimSpace(fila["Codigo Interno Bia"])
		fecha := strings.TrimSpace(fila["Creado El"])
		tipo := strings.ToUpper(strings.TrimSpace(fila["Tipo De Alcance"]))
		if co == "" || tipo != "INST" {
			continue
		}
		existente, hay := alcances.porCO[co]
		if !hay {
			alcances.orden = append(alcances.orden, co)
		}
		if !hay || fecha > existente["Creado El"] {
			alcances.porCO[co] = fila
		}
	}
	fmt.Printf("  Alcances cargados: %d codigos.\n", alcances.Len())
	return alcances
}

// ---------------------------------------------------------------- actas

// ActasNuevas devuelve las actas con PDF, en estado analizable, desde FECHA_INICIO
// y no procesadas, de la mas antigua a la mas nueva (con el tope por corrida).
func (m *Metabase) ActasNuevas(procesadas []string) []Fila {
	fmt.Printf("[%s] Descargando actas desde Metabase...\n", util.Ahora())
	data, err := m.get(m.cfg.ActasCSVURL, 30*time.Second)
	if err != nil {
		fmt.Printf("  ERROR descargando CSV: %v\n", err)
		return nil
	}
	_, filas, err := leerCSV(data, false)
	if err != nil {
		fmt.Printf("  ERROR descargando CSV: %v\n", err)
		return nil
	}

	yaProcesadas := map[string]bool{}
	for _, id := range procesadas {
		yaProcesadas[id] = true
	}
	fechaInicio, _ := time.Parse("2006-01-02", m.cfg.FechaInicio)
	var pendientes []Fila
	var omTipo, omEstado, omSinActa, omSinPDF, omFecha, omYaProc, omFechaInvalida int

	for _, fila := range filas {
		tipo := strings.TrimSpace(fila["Tipo de servicio"])
		estado := strings.TrimSpace(fila["electrician_status_id"])
		id := strings.TrimSpace(fila["id"])
		pdfURL := strings.TrimSpace(fila["act_pdf_url"])
		fecha := strings.TrimSpace(fila["start"])
		tieneActa := strings.TrimSpace(fila["Tiene Acta"])

		// Se aceptan todos los tipos de servicio: el track de QA decide la profundidad
		switch {
		case tipo == "":
			omTipo++
			continue
		case !m.cfg.EsAnalizable(estado):
			omEstado++
			continue
		case tieneActa != "Con Acta":
			omSinActa++
			continue
		case pdfURL == "":
			omSinPDF++
			continue
		}
		f, err := time.Parse("2006-01-02", recortar(fecha, 10))
		if err != nil {
			omFechaInvalida++
			continue
		}
		if f.Before(fechaInicio) {
			omFecha++
			continue
		}
		if yaProcesadas[id] {
			omYaProc++
			continue
		}
		pendientes = append(pendientes, fila)
	}

	sort.SliceStable(pendientes, func(i, j int) bool {
		a, b := pendientes[i], pendientes[j]
		if a["start"] != b["start"] {
			return a["start"] < b["start"]
		}
		return a["created_at"] < b["created_at"]
	})
	fmt.Printf("  %d acta(s) nueva(s) | filtradas: tipo=%d estado=%d sin_acta=%d sin_pdf=%d fecha=%d fecha_invalida=%d ya_procesadas=%d\n",
		len(pendientes), omTipo, omEstado, omSinActa, omSinPDF, omFecha, omFechaInvalida, omYaProc)

	if tope := m.cfg.MaxActasPorRun; tope > 0 && len(pendientes) > tope {
		fmt.Printf("  Cap por run: tomando %d mas antiguas, %d quedan para proximos runs.\n", tope, len(pendientes)-tope)
		pendientes = pendientes[:tope]
	}
	if m.cfg.ModoPrueba && len(pendientes) > m.cfg.ActasPrueba {
		fmt.Printf("  [MODO PRUEBA] Solo %d de %d.\n", m.cfg.ActasPrueba, len(pendientes))
		pendientes = pendientes[:m.cfg.ActasPrueba]
	}
	return pendientes
}

// errorHTTP replica el mensaje de requests.raise_for_status() de Python, que
// queda guardado en el estado (ej. "404 Client Error: Not Found for url: ...").
func errorHTTP(status int, url string) error {
	tipo := "Client"
	if status >= 500 {
		tipo = "Server"
	}
	return fmt.Errorf("%d %s Error: %s for url: %s", status, tipo, http.StatusText(status), url)
}
