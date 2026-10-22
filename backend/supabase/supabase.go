// Package supabase escribe los resultados en la tabla actas_qa de Supabase, que
// es la que lee el dashboard (frontend). Ver docs/contrato-supabase.md.
package supabase

import (
	"bytes"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/util"
)

// TamPagina es el maximo de filas que PostgREST devuelve por consulta (config. por defecto de Supabase).
const TamPagina = 1000

// Cliente habla con la API REST (PostgREST) de Supabase con la service role key.
type Cliente struct {
	base string
	key  string
	http *http.Client
}

// New devuelve nil si Supabase no esta configurado.
func New(cfg config.Config) *Cliente {
	if !cfg.SupabaseConfigurado() {
		return nil
	}
	return &Cliente{base: cfg.SupabaseURL, key: cfg.SupabaseKey, http: &http.Client{}}
}

func (c *Cliente) pedir(metodo, ruta string, params url.Values, cuerpo any, prefer string, timeout time.Duration) (int, []byte, error) {
	u := c.base + "/rest/v1/" + ruta
	if len(params) > 0 {
		u += "?" + params.Encode()
	}
	var body io.Reader
	if cuerpo != nil {
		data, err := dato.Codificar(cuerpo, false)
		if err != nil {
			return 0, nil, err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequest(metodo, u, body)
	if err != nil {
		return 0, nil, err
	}
	req.Header.Set("apikey", c.key)
	req.Header.Set("Authorization", "Bearer "+c.key)
	req.Header.Set("Content-Type", "application/json")
	if prefer != "" {
		req.Header.Set("Prefer", prefer)
	}
	cli := *c.http
	cli.Timeout = timeout
	resp, err := cli.Do(req)
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	return resp.StatusCode, data, err
}

// LeerTodas lee todas las filas de actas_qa paginando de a TamPagina.
func (c *Cliente) LeerTodas(seleccion string) ([]dato.Objeto, error) {
	var filas []dato.Objeto
	for {
		params := url.Values{
			"select": {seleccion},
			"order":  {"ot_id"},
			"limit":  {strconv.Itoa(TamPagina)},
			"offset": {strconv.Itoa(len(filas))},
		}
		status, data, err := c.pedir(http.MethodGet, "actas_qa", params, nil, "", 30*time.Second)
		if err != nil {
			return nil, err
		}
		if status >= 400 {
			return nil, fmt.Errorf("HTTP %d", status)
		}
		var pagina []dato.Objeto
		if err := dato.Decodificar(data, &pagina); err != nil {
			return nil, err
		}
		filas = append(filas, pagina...)
		if len(pagina) < TamPagina {
			return filas, nil
		}
	}
}

// ReconciliarEstadoAppOps recalcula estado_app_ops y estado_revision de cada
// acta guardada segun el estado actual en App Ops (match por ot_id y, si no,
// por titulo):
//
//	CLOSURE_SUCCESSFUL -> Exitosa / cerrada
//	CLOSURE_FAILED     -> Fallida / cerrada
//	otros              -> null    / pendiente
func ReconciliarEstadoAppOps(c *Cliente, porID, porTitulo map[string]string) {
	if len(porID) == 0 && len(porTitulo) == 0 {
		fmt.Println("  Reconciliacion: no hay estados de App Ops cargados, se omite.")
		return
	}
	if c == nil {
		fmt.Println("  Reconciliacion: sin Supabase, se omite.")
		return
	}
	actas, err := c.LeerTodas("ot_id,ot_nombre,internal_bia_code,estado_app_ops,estado_revision")
	if err != nil {
		fmt.Printf("  Reconciliacion: error consultando Supabase: %v\n", err)
		return
	}

	cambios, fallidos, porIDOk, porTituloOk := 0, 0, 0, 0
	var sinMatch []string
	for _, acta := range actas {
		otID := dato.Texto(acta["ot_id"])
		otNombre := dato.Texto(acta["ot_nombre"])
		if otID == "" {
			continue
		}
		estadoReal := porID[otID]
		switch {
		case estadoReal != "":
			porIDOk++
		case otNombre != "":
			estadoReal = porTitulo[otNombre]
			if estadoReal == "" {
				sinMatch = append(sinMatch, otNombre)
				continue
			}
			porTituloOk++
		default:
			sinMatch = append(sinMatch, otID)
			continue
		}

		var nuevaApp any
		nuevaRev := "pendiente"
		switch estadoReal {
		case "CLOSURE_SUCCESSFUL":
			nuevaApp, nuevaRev = "Exitosa", "cerrada"
		case "CLOSURE_FAILED":
			nuevaApp, nuevaRev = "Fallida", "cerrada"
		}
		if acta["estado_app_ops"] == nuevaApp && acta["estado_revision"] == nuevaRev {
			continue
		}
		status, _, err := c.pedir(http.MethodPatch, "actas_qa", url.Values{"ot_id": {"eq." + otID}},
			map[string]any{"estado_app_ops": nuevaApp, "estado_revision": nuevaRev}, "return=minimal", 10*time.Second)
		if err != nil || status >= 400 {
			fallidos++
			continue
		}
		cambios++
	}
	conError := ""
	if fallidos > 0 {
		conError = fmt.Sprintf(", %d con error", fallidos)
	}
	fmt.Printf("  Reconciliacion App Ops: %d/%d actualizadas%s. Match por ot_id=%d, por Title=%d, sin match=%d.\n",
		cambios, len(actas), conError, porIDOk, porTituloOk, len(sinMatch))
	if len(sinMatch) > 0 {
		if len(sinMatch) > 5 {
			sinMatch = sinMatch[:5]
		}
		fmt.Printf("  Sin match (primeras 5): %q\n", sinMatch)
	}
}

// Registro arma la fila de actas_qa para un acta auditada.
func Registro(acta map[string]string, qa dato.Objeto, alcance map[string]string) dato.Objeto {
	medEnc := dato.Hijo(qa, "medidor_encontrado")
	medInst := dato.Hijo(qa, "medidor_instalado")
	tcsEnc := dato.Hijo(qa, "tcs_encontrados")
	tpsEnc := dato.Hijo(qa, "tps_encontrados")
	val := dato.Hijo(qa, "validaciones")
	falla := dato.Hijo(qa, "tipificacion_falla")

	var pdfURL any
	if acta["act_pdf_url"] != "" {
		pdfURL = acta["act_pdf_url"]
	}
	errores := val["errores_encontrados"]
	if !dato.Verdadero(errores) {
		errores = []any{}
	}
	alertas := qa["alertas_qa"]
	if !dato.Verdadero(alertas) {
		alertas = []any{}
	}
	estadoRevision := qa["estado_revision"]
	if !dato.Verdadero(estadoRevision) {
		estadoRevision = "pendiente"
	}
	var alcanceViable, alcanceMedida, alcanceCompleto any
	if alcance != nil {
		alcanceViable = util.Av(alcance, "Viable Para Instalar")
		alcanceMedida = util.Av(alcance, "Tipo De Medida A Instalar")
		alcanceCompleto = alcance
	}

	return dato.Objeto{
		"procesado_en":                      util.AhoraUTCISO(),
		"ot_nombre":                         campo(acta, "title"),
		"ot_id":                             campo(acta, "id"),
		"tipo_servicio":                     campo(acta, "Tipo de servicio"),
		"estado_ot":                         qa["estado_ot"],
		"fecha_ejecucion":                   campo(acta, "start"),
		"pdf_url":                           pdfURL,
		"internal_bia_code":                 campo(acta, "internal_bia_code"),
		"contract_id":                       qa["contract_id"],
		"or_norm":                           campo(acta, "OR_NORM"),
		"planner":                           qa["planner"],
		"empresa":                           campo(acta, "company_name"),
		"direccion":                         campo(acta, "address"),
		"tipo_medida":                       qa["tipo_medida"],
		"factor_medida":                     dato.Texto(qa["factor_medida"]),
		"tecnico_nombre":                    qa["tecnico_nombre"],
		"tecnico_empresa":                   qa["tecnico_empresa"],
		"contratista_nombre":                qa["contratista_nombre"],
		"medidor_encontrado_serie":          medEnc["serie"],
		"medidor_encontrado_marca":          medEnc["marca"],
		"medidor_instalado_serie":           medInst["serie"],
		"medidor_instalado_marca":           medInst["marca"],
		"medidor_coincide_wms":              qa["medidor_coincide_wms"],
		"tcs_coinciden_wms":                 qa["tcs_coinciden_wms"],
		"tps_coinciden_wms":                 qa["tps_coinciden_wms"],
		"sellos_medidor_encontrado":         qa["sellos_medidor_encontrado"],
		"sellos_medidor_instalado":          qa["sellos_medidor_instalado"],
		"sellos_tcs_encontrados":            qa["sellos_tcs_encontrados"],
		"sellos_tcs_instalados":             qa["sellos_tcs_instalados"],
		"tiene_tcs":                         dato.Verdadero(tcsEnc["aplica"]) && dato.Verdadero(tcsEnc["tiene"]),
		"tiene_tps":                         dato.Verdadero(tpsEnc["aplica"]) && dato.Verdadero(tpsEnc["tiene"]),
		"tiene_telemedida":                  dato.Verdadero(dato.Hijo(qa, "telemedida_encontrada")["tiene"]),
		"tiene_diagrama_unifilar":           dato.Verdadero(dato.Hijo(qa, "diagrama_unifilar")["tiene_foto"]),
		"or_firma":                          qa["or_firma"],
		"validacion_coherente":              val["coherencia"],
		"errores_qa":                        errores,
		"alertas_qa":                        alertas,
		"tipificacion_causa_raiz":           falla["causa_raiz"],
		"tipificacion_responsable":          falla["responsable"],
		"wms_asignado":                      dato.Verdadero(qa["wms_asignado"]),
		"wms_medidor_serial":                qa["medidor_wms_asignado"],
		"wms_medidor_marca":                 qa["medidor_wms_marca"],
		"wms_completo":                      qa["wms_completo"],
		"wms_marca_coincide_alcance":        qa["wms_marca_coincide_alcance"],
		"serial_medidor_factura_anterior":   qa["serial_medidor_factura_anterior"],
		"medidor_coincide_factura_anterior": qa["medidor_coincide_factura_anterior"],
		"factura_anterior_express":          qa["factura_anterior_express"],
		"factura_anterior_estado":           qa["factura_anterior_estado"],
		"qa_track":                          qa["qa_track"],
		"estado_app_ops":                    qa["estado_app_ops"],
		"estado_revision":                   estadoRevision,
		"tiene_alcance":                     alcance != nil,
		"alcance_viable":                    alcanceViable,
		"alcance_medida_instalar":           alcanceMedida,
		"alcance_completo":                  alcanceCompleto,
		"resultado_qa_completo":             qa,
	}
}

// Guardar hace upsert del registro (por ot_id). Devuelve false solo si hubo un
// error; sin Supabase configurado (corrida local) no guarda nada y devuelve true.
func Guardar(c *Cliente, registro dato.Objeto) bool {
	if c == nil {
		return true
	}
	status, data, err := c.pedir(http.MethodPost, "actas_qa", url.Values{"on_conflict": {"ot_id"}}, registro,
		"resolution=merge-duplicates,return=minimal", 15*time.Second)
	if err != nil {
		fmt.Printf("  ERROR Supabase: %v\n", err)
		return false
	}
	if status >= 200 && status < 300 {
		fmt.Println("  Supabase: registro guardado.")
		return true
	}
	fmt.Printf("  ERROR Supabase: %d %s\n", status, recortar(string(data), 200))
	return false
}

// ActualizarAlcance marca con el alcance las visitas previas del codigo CO.
// Devuelve false solo si hubo un error.
func ActualizarAlcance(c *Cliente, codigoCO string, alcance map[string]string) bool {
	if c == nil {
		return true
	}
	cuerpo := map[string]any{
		"tiene_alcance":           true,
		"alcance_viable":          util.Av(alcance, "Viable Para Instalar"),
		"alcance_medida_instalar": util.Av(alcance, "Tipo De Medida A Instalar"),
		"alcance_completo":        alcance,
	}
	params := url.Values{"internal_bia_code": {"eq." + codigoCO}, "tipo_servicio": {"eq.Visita previa"}}
	status, data, err := c.pedir(http.MethodPatch, "actas_qa", params, cuerpo, "return=minimal", 15*time.Second)
	if err != nil {
		fmt.Printf("  ERROR Supabase alcance: %v\n", err)
		return false
	}
	if status >= 200 && status < 300 {
		fmt.Printf("  Supabase: VIPE %s marcada con alcance.\n", codigoCO)
		return true
	}
	fmt.Printf("  ERROR Supabase alcance: %d %s\n", status, recortar(string(data), 200))
	return false
}

// campo replica acta.get(clave) de Python: nil si la columna no existe.
func campo(acta map[string]string, clave string) any {
	if v, ok := acta[clave]; ok {
		return v
	}
	return nil
}

func recortar(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}

// Consultar lee filas de actas_qa con los filtros de PostgREST dados.
func (c *Cliente) Consultar(params url.Values) ([]dato.Objeto, error) {
	status, data, err := c.pedir(http.MethodGet, "actas_qa", params, nil, "", 60*time.Second)
	if err != nil {
		return nil, err
	}
	if status != 200 {
		return nil, fmt.Errorf("%d %s", status, recortar(string(data), 200))
	}
	var filas []dato.Objeto
	err = dato.Decodificar(data, &filas)
	return filas, err
}

// ActualizarOT cambia columnas de una OT por ot_id.
func (c *Cliente) ActualizarOT(otID string, cambios map[string]any) error {
	status, data, err := c.pedir(http.MethodPatch, "actas_qa", url.Values{"ot_id": {"eq." + otID}}, cambios,
		"return=minimal", 15*time.Second)
	if err != nil {
		return err
	}
	if status >= 400 {
		return fmt.Errorf("%d %s", status, recortar(string(data), 200))
	}
	return nil
}
