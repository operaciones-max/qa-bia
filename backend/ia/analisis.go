package ia

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/anthropics/anthropic-sdk-go"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

// EtiquetaTipo es el tipo de servicio que ve el prompt full.
func EtiquetaTipo(tipoServicio string) string {
	t := strings.TrimSpace(tipoServicio)
	if strings.Contains(strings.ToLower(t), "previa") {
		return "VISITA PREVIA"
	}
	if strings.Contains(t, "nstala") {
		return "INSTALACION"
	}
	if t == "" {
		return "SIN TIPO"
	}
	return strings.ToUpper(t)
}

func resultadoApp(exitosa bool) string {
	if exitosa {
		return "EXITOSA"
	}
	return "FALLIDA"
}

// AnalizarActaLite hace el QA lite (Retencion / Energy Solutions). Si hay
// imagenes (actas fisicas de PQR/VICO/Emergencia) se mandan hasta 4.
// Devuelve nil si no hay resultado.
func (c *Cliente) AnalizarActaLite(ctx context.Context, textoPDF, tipoServicio string, exitosa bool,
	codigoBIA string, imagenes [][]byte) dato.Objeto {

	textoMsg := fmt.Sprintf("TIPO DE SERVICIO: %s\nRESULTADO EN APP: %s\nCODIGO INTERNO BIA: %s\n\n--- TEXTO DEL ACTA ---\n%s",
		tipoServicio, resultadoApp(exitosa), codigoBIA, recortar(textoPDF, 8000))
	if len(imagenes) > 4 {
		imagenes = imagenes[:4]
	}
	contenido := append(bloquesImagen(imagenes), anthropic.NewTextBlock(textoMsg))

	if cd := c.estado.CooldownActivo(); cd != nil {
		fmt.Printf("  Claude en cooldown (%s) - se omite analisis lite.\n", cd.Razon)
		return nil
	}

	maxTokens := int64(1500)
	if len(imagenes) > 0 {
		maxTokens = 2000
	}
	texto, err := c.llamar(ctx, "lite", SystemPromptLite(), contenido, maxTokens)
	if err != nil {
		if EsLimiteDeUso(err) {
			c.estado.ActivarCooldown(err.Error())
			return nil
		}
		fmt.Printf("  ERROR Claude lite: %v\n", err)
		return nil
	}
	resultado, err := ExtraerJSON(texto)
	if err != nil {
		fmt.Printf("  JSON invalido lite de %s\n", c.modelo)
		return nil
	}
	return resultado
}

// AsignacionWMS son los equipos asignados en WMS contra los que se compara el acta.
type AsignacionWMS struct {
	SerialMedidor string
	MarcaMedidor  string
	TCs           []string
	TPs           []string
}

// AnalizarActa hace el QA full (Activacion y normalizaciones con WMS).
// Devuelve nil si no hay resultado.
func (c *Cliente) AnalizarActa(ctx context.Context, textoPDF, tipoServicio string, exitosa bool,
	codigoBIA string, wms AsignacionWMS, imagenes [][]byte) dato.Objeto {

	esVisita := strings.Contains(strings.ToLower(tipoServicio), "previa")
	debeComparar := exitosa && !esVisita && wms.SerialMedidor != ""
	wmsInfo, marcaWMS := "No aplica", ""
	if debeComparar {
		wmsInfo, marcaWMS = wms.SerialMedidor, wms.MarcaMedidor
	}
	tcsInfo, tpsInfo := "No aplica", "No aplica"
	if debeComparar && len(wms.TCs) > 0 {
		tcsInfo = strings.Join(wms.TCs, ", ")
	}
	if debeComparar && len(wms.TPs) > 0 {
		tpsInfo = strings.Join(wms.TPs, ", ")
	}
	marca := ""
	if marcaWMS != "" {
		marca = "(" + marcaWMS + ")"
	}
	lineaImagenes := "SIN IMAGENES: solo el texto del acta.\n"
	if len(imagenes) > 0 {
		lineaImagenes = fmt.Sprintf("SE ADJUNTAN IMAGENES: %d pagina(s) del acta.\n", len(imagenes))
	}

	userMsg := fmt.Sprintf("TIPO DE SERVICIO: %s\n"+
		"RESULTADO EN APP: %s\n"+
		"CODIGO INTERNO BIA: %s\n"+
		"MEDIDOR ASIGNADO EN SISTEMA WMS: %s %s\n"+
		"TCs ASIGNADOS EN WMS (semidirecta/indirecta): %s\n"+
		"TPs ASIGNADOS EN WMS (solo indirecta): %s\n"+
		"%s"+
		"\n--- TEXTO DEL ACTA ---\n%s",
		EtiquetaTipo(tipoServicio), resultadoApp(exitosa), codigoBIA, wmsInfo, marca,
		tcsInfo, tpsInfo, lineaImagenes, recortar(textoPDF, 12000))
	contenido := append(bloquesImagen(imagenes), anthropic.NewTextBlock(userMsg))

	if cd := c.estado.CooldownActivo(); cd != nil {
		fmt.Printf("  Claude en cooldown (%s) hasta %s - se omite analisis.\n", cd.Razon, cd.Until)
		return nil
	}

	texto, err := c.llamar(ctx, "full", SystemPromptFull(), contenido, 4096)
	if err != nil {
		if EsLimiteDeUso(err) {
			cd := c.estado.ActivarCooldown(err.Error())
			fmt.Printf("  Limite Claude detectado (%s). Cooldown hasta %s. Se aborta.\n", cd.Razon, cd.Until)
			return nil
		}
		fmt.Printf("  ERROR Claude: %v\n", err)
		return nil
	}
	resultado, err := ExtraerJSON(texto)
	if errors.Is(err, errJSONInvalido) {
		fmt.Printf("  JSON invalido de Claude: %s\n", recortar(texto, 150))
		return nil
	}
	return resultado
}

// instruccionFactura es lo que se le pide al OCR sobre la factura anterior.
const instruccionFactura = `Factura de energía eléctrica colombiana. Extrae el número (serial) del medidor del cliente.
Dónde suele estar, por comercializador:
- Enel: "No. Medidor"
- Air-e / Aire: "Número de Medidor"
- Enel X: "Medidor No"
- ERCO: "Código medidor"
- Celsia: cuadro "Medidor" con el número abajo
- EPM: "medidor" junto al cuadro de consumos
- CENS: "Medidor Activa"
No lo confundas con el NIU, NIC, número de cuenta, de contrato o de factura.
"menciona_express" es true si la palabra "express" aparece en la factura.
Estructura: {"serial_medidor": "", "menciona_express": false}`

// LeerSerialDeFactura lee con el OCR (texto de las paginas y, las escaneadas,
// como imagen) el serial del medidor de la factura anterior. Devuelve el
// serial ("" si no aparece), si menciona "express" (nil si no se pudo leer) y
// el estado: "ok", "cooldown", "rate_limit" o "error_claude: ...".
func (c *Cliente) LeerSerialDeFactura(ctx context.Context, doc Documento) (string, *bool, string) {
	if c.estado != nil && c.estado.CooldownActivo() != nil {
		return "", nil, "cooldown"
	}
	r, err := c.ExtraerInformacion(ctx, instruccionFactura, doc, "")
	if err != nil {
		if EsLimiteDeUso(err) {
			if c.estado != nil {
				c.estado.ActivarCooldown(err.Error())
			}
			return "", nil, "rate_limit"
		}
		return "", nil, "error_claude: " + recortar(err.Error(), 120)
	}
	data, err := ExtraerJSON(string(r.JSON))
	if err != nil {
		return "", nil, "error_claude: " + err.Error()
	}
	express := dato.EsTrue(data["menciona_express"])
	return dato.TextoLimpio(data["serial_medidor"]), &express, "ok"
}
