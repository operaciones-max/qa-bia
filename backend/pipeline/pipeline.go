// Package pipeline orquesta el QA: procesa cada acta de punta a punta y corre
// el ciclo principal.
package pipeline

import (
	"context"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"github.com/operaciones-max/qa-bia/backend/catalogo"
	"github.com/operaciones-max/qa-bia/backend/cierre"
	"github.com/operaciones-max/qa-bia/backend/config"
	"github.com/operaciones-max/qa-bia/backend/dato"
	"github.com/operaciones-max/qa-bia/backend/estado"
	"github.com/operaciones-max/qa-bia/backend/facturas"
	"github.com/operaciones-max/qa-bia/backend/ia"
	"github.com/operaciones-max/qa-bia/backend/metabase"
	"github.com/operaciones-max/qa-bia/backend/pdf"
	"github.com/operaciones-max/qa-bia/backend/reportes"
	"github.com/operaciones-max/qa-bia/backend/supabase"
	"github.com/operaciones-max/qa-bia/backend/util"
	"github.com/operaciones-max/qa-bia/backend/validaciones"
	"github.com/operaciones-max/qa-bia/backend/verificacion"
)

// Pipeline tiene las dependencias de una corrida.
type Pipeline struct {
	cfg      config.Config
	estado   *estado.Estado
	metabase *metabase.Metabase
	claude   *ia.Cliente
	supabase *supabase.Cliente // nil si no esta configurado
}

// New arma el pipeline con la configuracion.
func New(cfg config.Config) *Pipeline {
	est := estado.New(cfg)
	return &Pipeline{
		cfg:      cfg,
		estado:   est,
		metabase: metabase.New(cfg),
		claude:   ia.NewCliente(cfg, est),
		supabase: supabase.New(cfg),
	}
}

// fuentes son los datos de Metabase que se cargan al inicio de cada ciclo.
type fuentes struct {
	wms      map[string]*metabase.EquiposWMS
	alcances metabase.Alcances
	facturas map[string]metabase.Factura
}

func (p *Pipeline) cargarFuentes() fuentes {
	return fuentes{
		wms:      p.metabase.InventarioWMS(),
		alcances: p.metabase.Alcances(),
		facturas: p.metabase.FacturasAnteriores(),
	}
}

func dormir(segundos int) {
	if segundos > 0 {
		time.Sleep(time.Duration(segundos) * time.Second)
	}
}

// pyRepr muestra un valor como lo imprimiria Python (None, True, False).
func pyRepr(v any) string {
	switch x := v.(type) {
	case nil:
		return "None"
	case *string:
		if x == nil {
			return "None"
		}
		return *x
	case *bool:
		if x == nil {
			return "None"
		}
		return dato.TextoCrudo(*x)
	default:
		return dato.TextoCrudo(v)
	}
}

// VerificarNuevosAlcances marca en Supabase las visitas previas que ya tienen
// alcance de ingenieria.
func (p *Pipeline) VerificarNuevosAlcances(alcances metabase.Alcances) {
	procesados := map[string]bool{}
	for _, id := range p.estado.AlcancesProcesados() {
		procesados[id] = true
	}
	visitas := p.estado.VisitasPrevias()
	fechaInicio, _ := time.Parse("2006-01-02", p.cfg.FechaInicioAlcances)
	nuevos := 0

	for _, co := range alcances.Codigos() {
		alcance := alcances.Get(co)
		alcanceID := strings.TrimSpace(alcance["ID"])
		if alcanceID == "" || procesados[alcanceID] {
			continue
		}
		fecha := strings.TrimSpace(alcance["Creado El"])
		f, err := time.Parse("2006-01-02", recortar(fecha, 10))
		if err != nil || f.Before(fechaInicio) {
			continue
		}
		vp := "No"
		if visitas[co] {
			vp = "Si"
		}
		fmt.Printf("\n  -> Nuevo alcance: %s (VP almacenada: %s)\n", co, vp)
		if !supabase.ActualizarAlcance(p.supabase, co, alcance) {
			fmt.Println("     No se marca como procesado: se reintenta en la proxima corrida.")
			continue
		}
		p.estado.MarcarAlcanceProcesado(alcanceID)
		nuevos++
		if nuevos < 10 {
			dormir(p.cfg.PausaEntreAlcancesSeg)
		}
	}
	if nuevos == 0 {
		fmt.Println("  Sin nuevos alcances de ingenieria.")
	} else {
		fmt.Printf("  %d alcance(s) nuevo(s) notificado(s).\n", nuevos)
	}
}

// ProcesarActa audita un acta y guarda el resultado. Devuelve true si quedo
// guardada (y marcada como procesada).
func (p *Pipeline) ProcesarActa(ctx context.Context, acta metabase.Fila, f fuentes) bool {
	otNombre, ok := acta["title"]
	if !ok {
		otNombre = acta["id"]
	}
	pdfURL := acta["act_pdf_url"]
	tipo := acta["Tipo de servicio"]
	estadoElectricista := acta["electrician_status_id"]
	orNorm := acta["OR_NORM"]
	codigo := acta["internal_bia_code"]
	planner := catalogo.Planner(p.cfg, orNorm)

	equipos := f.wms[codigo]
	var serialAsignado, marcaAsignada string
	var tcsAsignados, tpsAsignados []string
	if equipos != nil {
		if equipos.Medidor != nil {
			serialAsignado, marcaAsignada = equipos.Medidor.Serial, equipos.Medidor.Marca
		}
		for _, t := range equipos.TCs {
			if t.Serial != "" {
				tcsAsignados = append(tcsAsignados, t.Serial)
			}
		}
		for _, t := range equipos.TPs {
			if t.Serial != "" {
				tpsAsignados = append(tpsAsignados, t.Serial)
			}
		}
	}

	exitosa := p.cfg.EsExitoso(estadoElectricista)
	esVisita := strings.Contains(strings.ToLower(tipo), "previa")
	debeComparar := exitosa && !esVisita && serialAsignado != ""
	track := catalogo.QATrack(tipo)
	usaFull := track == "Activacion" || catalogo.RequiereComparacionWMS(tipo, track)

	nivel := "lite"
	if usaFull {
		nivel = "full"
	}
	fmt.Printf("\n  -> Procesando: %s\n", otNombre)
	fmt.Printf("     Tipo: %s | Estado: %s | Track: %s | QA: %s\n", tipo, estadoElectricista, track, nivel)
	fmt.Printf("     OR: %s | Planner: %s\n", orNorm, planner)
	if serialAsignado != "" {
		fmt.Printf("     WMS: medidor=%s | TCs=%d | TPs=%d | Comparar=%s\n",
			serialAsignado, len(tcsAsignados), len(tpsAsignados), dato.TextoCrudo(debeComparar))
	} else {
		fmt.Printf("     WMS: No encontrado para %s\n", codigo)
	}

	textoPDF, imagenesPDF, pdfBytes := pdf.DescargarYLeer(pdfURL)
	if textoPDF == "" {
		fmt.Println("     No se pudo leer el PDF. Se omite.")
		return false
	}

	var qa dato.Objeto
	if usaFull {
		fmt.Printf("     Analizando con Claude full (%s) | imagenes: %d\n", p.claude.Modelo(), len(imagenesPDF))
		asignacion := ia.AsignacionWMS{}
		if debeComparar {
			asignacion = ia.AsignacionWMS{SerialMedidor: serialAsignado, MarcaMedidor: marcaAsignada, TCs: tcsAsignados, TPs: tpsAsignados}
		}
		qa = p.claude.AnalizarActa(ctx, textoPDF, tipo, exitosa, codigo, asignacion, imagenesPDF)
	} else {
		// PQR / VICO / Emergencia tienen el acta fisica manuscrita fotografiada en
		// el PDF: se mandan las primeras 4 paginas como imagen para que Claude la lea.
		var imagenesLite [][]byte
		if catalogo.NecesitaVisionLite(tipo) {
			imagenesLite = pdf.RenderizarPaginas(pdfBytes, 4, 150)
			fmt.Printf("     Vision lite habilitada (%s): %d paginas a dpi=150\n", tipo, len(imagenesLite))
		}
		fmt.Printf("     Analizando con Claude lite (%s) — track %s\n", p.claude.Modelo(), track)
		qa = p.claude.AnalizarActaLite(ctx, textoPDF, tipo, exitosa, codigo, imagenesLite)
	}
	if len(qa) == 0 {
		return false
	}

	// El estado lo manda App Ops (electrician_status_id), no la IA.
	if exitosa {
		qa["estado_ot"] = "EXITOSA"
		qa["tipificacion_falla"] = nil // no aplica en una OT exitosa
	} else {
		qa["estado_ot"] = "FALLIDA"
	}
	qa["qa_track"] = track
	// Cierre de gestion solo si la OT esta cerrada formalmente en App Ops
	// (COMPLETED = el tecnico termino pero la OT sigue sin cerrar).
	if estadoElectricista == "CLOSURE_SUCCESSFUL" || estadoElectricista == "CLOSURE_FAILED" {
		qa["estado_revision"] = "cerrada"
	} else {
		qa["estado_revision"] = "pendiente"
	}
	switch estadoElectricista {
	case "CLOSURE_SUCCESSFUL":
		qa["estado_app_ops"] = "Exitosa"
	case "CLOSURE_FAILED":
		qa["estado_app_ops"] = "Fallida"
	default:
		qa["estado_app_ops"] = nil
	}

	// Post-validaciones defensivas
	validaciones.AplicarReglasMedidaServicio(qa, tipo)
	validaciones.CorregirSerieFoto(dato.Hijo(qa, "medidor_encontrado"))
	validaciones.CorregirSerieFoto(dato.Hijo(qa, "medidor_instalado"))
	if debeComparar {
		validaciones.ValidarCoincidenciaWMS(qa, serialAsignado, tcsAsignados, tpsAsignados, true)
	} else {
		validaciones.ValidarCoincidenciaWMS(qa, "", nil, nil, false)
	}
	validaciones.LimpiarErroresFantasma(qa, tipo)
	// No se fuerza FALLIDA por datos incompletos: se respeta el estado del tecnico.
	// El revisor puede marcar FALLIDA desde el dashboard (frontend/).
	// Lo que el subagente de cierre ve del acta: antes de simplificar las
	// fallidas, que borran sus errores.
	actaExtraida := copiar(qa)
	validaciones.SimplificarFallida(qa)
	catalogo.ValidarTipificacion(qa)

	qa["planner"] = planner
	qa["or_norm"] = orNorm
	qa["internal_bia_code"] = codigo
	// WMS: serial, marca y el detalle completo para el dashboard
	qa["medidor_wms_asignado"] = nilSiVacio(serialAsignado)
	qa["medidor_wms_marca"] = nilSiVacio(marcaAsignada)
	qa["tcs_wms_asignados"] = dato.TextosAny(tcsAsignados)
	qa["tps_wms_asignados"] = dato.TextosAny(tpsAsignados)
	qa["wms_asignado"] = serialAsignado != ""
	if equipos != nil {
		qa["wms_completo"] = equipos
	} else {
		qa["wms_completo"] = nil
	}

	// Tecnico y contratista: la fuente de verdad es Metabase, no la IA.
	// contractor_name "BIA" = empleado de BIA; otro valor = contratista; vacio = desconocido.
	if tecnico := strings.TrimSpace(acta["Electrician Visits__name"]); tecnico != "" {
		qa["tecnico_nombre"] = tecnico
	}
	switch contratista := strings.TrimSpace(acta["contractor_name"]); {
	case contratista == "":
		qa["tecnico_empresa"], qa["contratista_nombre"] = nil, nil
	case strings.ToUpper(contratista) == "BIA":
		qa["tecnico_empresa"], qa["contratista_nombre"] = "BIA", nil
	default:
		qa["tecnico_empresa"], qa["contratista_nombre"] = "CONTRATISTA", contratista
	}

	// Marca asignada en WMS vs marca del alcance
	alcance := f.alcances.Get(codigo)
	marcaAlcance := strings.TrimSpace(alcance["Marca Del Medidor"])
	if marcaAsignada != "" && marcaAlcance != "" && strings.ToUpper(marcaAlcance) != "N/A" && marcaAlcance != "-" {
		qa["wms_marca_coincide_alcance"] = strings.ToUpper(strings.TrimSpace(marcaAsignada)) == strings.ToUpper(marcaAlcance)
	} else {
		qa["wms_marca_coincide_alcance"] = nil
	}

	p.compararFacturaAnterior(ctx, qa, codigo, f.facturas)

	// VIPE e INST: cruce de los equipos entre acta, fotos y sistema.
	if tipoOT, ok := catalogo.TipoOTDe(otNombre, tipo); ok && usaFull && (tipoOT.Codigo == "VIPE" || tipoOT.Codigo == "INST") {
		p.verificarEquipos(ctx, qa, tipoOT.Codigo, pdfBytes, equipos, codigo, exitosa)
	}

	// Subagente de cierre del tipo de OT: segundo veredicto, independiente del de App Ops.
	if p.cfg.SubagentesCierre {
		p.evaluarCierre(ctx, qa, cierre.Caso{
			TipoServicio:    tipo,
			EstadoReportado: estadoElectricista,
			CodigoCO:        codigo,
			Acta:            actaExtraida,
			TextoActa:       textoPDF,
			Alcance:         alcance,
			Equipos:         equipos,
		}, otNombre)
	}

	fmt.Printf("     Resultado: %s | Medida: %s\n", pyRepr(qa["estado_ot"]), pyRepr(qa["tipo_medida"]))
	if dato.EsFalse(qa["medidor_coincide_wms"]) {
		fmt.Printf("     ALERTA: Medidor instalado != WMS asignado %s\n", serialAsignado)
	}
	if dato.EsFalse(qa["tcs_coinciden_wms"]) {
		fmt.Println("     ALERTA: TCs instalados != WMS asignados")
	}
	if dato.EsFalse(qa["tps_coinciden_wms"]) {
		fmt.Println("     ALERTA: TPs instalados != WMS asignados")
	}
	if errores := dato.Textos(dato.Hijo(qa, "validaciones")["errores_encontrados"]); len(errores) > 0 {
		fmt.Printf("     Errores QA: %s\n", strings.Join(errores, ", "))
	}

	// Hallazgos de la visita previa, para compararlos despues con el alcance
	if esVisita && codigo != "" {
		medEnc := qa["medidor_encontrado"]
		p.estado.GuardarVisitaPrevia(codigo, estado.VisitaPrevia{
			OTNombre:                   otNombre,
			FechaProcesada:             util.Ahora(),
			TipoMedida:                 qa["tipo_medida"],
			FactorMedida:               qa["factor_medida"],
			MedidorEncontrado:          medEnc,
			MedidorEncSerie:            dato.Mapa(medEnc)["serie"],
			TCsEncontrados:             qa["tcs_encontrados"],
			TPsEncontrados:             qa["tps_encontrados"],
			TecnicoNombre:              qa["tecnico_nombre"],
			TecnicoEmpresa:             qa["tecnico_empresa"],
			ContratistaNombre:          qa["contratista_nombre"],
			ObservacionTecnicoVerbatim: qa["observacion_tecnico_verbatim"],
		})
	}

	if _, err := reportes.Guardar(p.cfg.CarpetaReportes, acta, qa); err != nil {
		fmt.Printf("  ERROR guardando reporte: %v\n", err)
	}
	// Si Supabase falla, el acta NO se marca como procesada: se reintenta en la proxima corrida.
	if !supabase.Guardar(p.supabase, supabase.Registro(acta, qa, alcance)) {
		fmt.Printf("     %s no se guardo en Supabase; se reintenta en la proxima corrida.\n", otNombre)
		return false
	}
	p.estado.MarcarProcesada(acta["id"])

	// La visita previa ya viajo con su alcance: se marca para no volver a enviarlo.
	if esVisita && alcance != nil {
		if alcanceID := strings.TrimSpace(alcance["ID"]); alcanceID != "" && !contiene(p.estado.AlcancesProcesados(), alcanceID) {
			fmt.Printf("     Alcance de %s registrado en Supabase junto con la visita previa.\n", codigo)
			p.estado.MarcarAlcanceProcesado(alcanceID)
		}
	}
	fmt.Printf("     OK: %s auditada.\n", otNombre)
	return true
}

// verificarEquipos cruza los equipos de una VIPE o INST entre lo escrito en el
// acta, lo que se ve en sus fotos (OCR) y el sistema: la factura anterior y la
// visita previa para lo encontrado, lo asignado en WMS para lo instalado.
// Deja el resultado en qa["verificacion_equipos"] y, si el tecnico reporto la
// OT exitosa, suma lo que no cuadra a los errores del QA.
func (p *Pipeline) verificarEquipos(ctx context.Context, qa dato.Objeto, codigoOT string, pdfBytes []byte,
	equipos *metabase.EquiposWMS, codigoCO string, exitosa bool) {

	entrada := verificacion.Entrada{
		TipoOT: codigoOT,
		Acta:   qa,
		Factura: verificacion.Factura{
			Serial: dato.TextoLimpio(qa["serial_medidor_factura_anterior"]),
			Estado: dato.TextoLimpio(qa["factura_anterior_estado"]),
		},
	}
	if codigoOT == "INST" {
		if equipos != nil {
			asignados := &verificacion.Asignados{}
			if equipos.Medidor != nil {
				asignados.Medidor = equipos.Medidor.Serial
			}
			for _, t := range equipos.TCs {
				asignados.TCs = append(asignados.TCs, t.Serial)
			}
			for _, t := range equipos.TPs {
				asignados.TPs = append(asignados.TPs, t.Serial)
			}
			entrada.Asignados = asignados
		}
		if vp, ok := p.estado.VisitaPreviaDe(codigoCO); ok {
			tcs := dato.Mapa(vp.TCsEncontrados)
			entrada.VisitaPrevia = &verificacion.VisitaPrevia{
				OT:           vp.OTNombre,
				MedidorSerie: dato.TextoLimpio(vp.MedidorEncSerie),
				TCsSeriales:  dato.Textos(tcs["seriales"]),
				RelacionTCs:  dato.TextoLimpio(tcs["relacion"]),
			}
		}
	}
	if p.cfg.OCRFotos {
		fotos, err := verificacion.LeerFotos(ctx, p.claude, pdfBytes, codigoOT, dato.Texto(qa["tipo_medida"]))
		if err != nil {
			fmt.Printf("     OCR de fotos: %v\n", err)
		}
		entrada.Fotos = fotos
	}

	resultado := verificacion.Verificar(entrada)
	qa["verificacion_equipos"] = resultado
	hallazgos := resultado.Hallazgos()
	fmt.Printf("     Verificacion de equipos (%s, %s): %d cruces, %d hallazgos, fotos leidas: %v\n",
		codigoOT, resultado.TipoMedida, len(resultado.Cruces), len(hallazgos), resultado.FotosLeidas)
	if !exitosa || len(hallazgos) == 0 {
		return
	}
	val := dato.Hijo(qa, "validaciones")
	if val == nil {
		val = dato.Objeto{}
		qa["validaciones"] = val
	}
	errores := dato.Lista(val["errores_encontrados"])
	for _, h := range hallazgos {
		errores = append(errores, h)
	}
	val["errores_encontrados"] = errores
}

// evaluarCierre manda el caso al subagente de su tipo de OT y deja el
// resultado en qa["cierre_ia"]. No toca estado_ot: el revisor compara los dos.
func (p *Pipeline) evaluarCierre(ctx context.Context, qa dato.Objeto, caso cierre.Caso, otNombre string) {
	tipoOT, ok := catalogo.TipoOTDe(otNombre, caso.TipoServicio)
	if !ok {
		fmt.Printf("     Sin subagente de cierre para %q (%s)\n", otNombre, caso.TipoServicio)
		return
	}
	caso.Tipo = tipoOT
	caso.Validaciones = dato.Objeto{}
	for _, k := range []string{"medidor_coincide_wms", "tcs_coinciden_wms", "tps_coinciden_wms",
		"serial_medidor_factura_anterior", "factura_anterior_estado", "medidor_coincide_factura_anterior",
		"verificacion_equipos"} {
		if v, hay := qa[k]; hay {
			caso.Validaciones[k] = v
		}
	}
	resultado, err := cierre.Evaluar(ctx, p.claude, caso)
	if err != nil {
		fmt.Printf("     Subagente %s: ERROR %v\n", tipoOT.Codigo, err)
		qa["cierre_ia"] = dato.Objeto{"subagente": tipoOT.Codigo, "error": err.Error()}
		return
	}
	qa["cierre_ia"] = resultado
	fmt.Printf("     Subagente %s: %s | acta completa: %v\n", tipoOT.Codigo, resultado["veredicto"], resultado["acta_completa"])
}

// copiar hace una copia profunda de un objeto JSON.
func copiar(o dato.Objeto) dato.Objeto {
	data, err := dato.Codificar(o, false)
	if err != nil {
		return dato.Objeto{}
	}
	var copia dato.Objeto
	if err := dato.Decodificar(data, &copia); err != nil {
		return dato.Objeto{}
	}
	return copia
}

// compararFacturaAnterior extrae (o toma del cache) el serial del medidor de la
// factura anterior y lo compara con el medidor encontrado en el acta.
func (p *Pipeline) compararFacturaAnterior(ctx context.Context, qa dato.Objeto, codigo string, todas map[string]metabase.Factura) {
	var serial *string
	var express *bool
	estadoFactura := "no_disponible" // el CO no tiene URL de factura en HubSpot

	factura, hay := todas[codigo]
	if hay && factura.ContractID != "" {
		qa["contract_id"] = factura.ContractID
	} else {
		qa["contract_id"] = nil
	}
	if factura.URL != "" {
		estadoFactura = "borrosa"
		cache, enCache := p.estado.FacturaCacheada(codigo)
		// El cache se descarta si cambio la URL, si no tiene serial o si la
		// extraccion anterior no termino en "ok" (para reintentar con patrones nuevos).
		invalido := enCache && ((cache.URL != "" && cache.URL != factura.URL) ||
			cache.Serial == nil || *cache.Serial == "" ||
			(cache.Estado != "ok" && cache.Estado != ""))
		if enCache && !invalido {
			serial, express = cache.Serial, cache.Express
			switch {
			case serial != nil && *serial != "":
				estadoFactura = "ok"
			case cache.Estado == "ok":
				estadoFactura = "ok_sin_serial"
			}
		} else {
			fmt.Printf("     Extrayendo medidor de factura anterior para %s...\n", codigo)
			r := facturas.ExtraerSerial(ctx, p.claude, factura.URL)
			if r.Serial != "" {
				serial = &r.Serial
			}
			express = r.Express
			p.estado.GuardarFactura(codigo, estado.FacturaExtraida{
				Serial: serial, Express: express, URL: factura.URL, Estado: r.Estado, Fecha: util.Ahora(),
			})
			switch {
			case serial != nil:
				estadoFactura = "ok"
			case r.Estado == "ok":
				estadoFactura = "ok_sin_serial"
			}
			fmt.Printf("     Factura anterior: serial=%s express=%s (%s)\n", pyRepr(serial), pyRepr(express), r.Estado)
		}
	}
	qa["serial_medidor_factura_anterior"] = nilSiNil(serial)
	qa["factura_anterior_express"] = nilSiNilBool(express)
	qa["factura_anterior_estado"] = estadoFactura

	serialActa := dato.TextoLimpio(dato.Hijo(qa, "medidor_encontrado")["serie"])
	if serial != nil && *serial != "" && serialActa != "" {
		qa["medidor_coincide_factura_anterior"] = util.NormalizarSerial(*serial) == util.NormalizarSerial(serialActa)
	} else {
		qa["medidor_coincide_factura_anterior"] = nil
	}
}

// Main corre el QA: una pasada (MODO_UNICO) o en bucle cada INTERVALO_SEGUNDOS.
func (p *Pipeline) Main(ctx context.Context) {
	modo := "AUTOMATICO"
	if p.cfg.ModoPrueba {
		modo = "PRUEBA"
	}
	linea := strings.Repeat("=", 58)
	fmt.Println(linea)
	fmt.Println("   SISTEMA QA BIA ENERGY  -  Motor: Anthropic Claude")
	fmt.Println("   Modo: " + modo)
	fmt.Println(linea)
	fmt.Println("   Fecha inicio : " + p.cfg.FechaInicio)
	fmt.Printf("   Pausa        : %ds entre actas\n", p.cfg.PausaEntreActasSeg)
	if p.cfg.ModoPrueba {
		fmt.Printf("   Actas prueba : %d\n", p.cfg.ActasPrueba)
	}
	fmt.Println(linea)

	fmt.Println("\n  Cargando inventario WMS...")
	wms := p.metabase.InventarioWMS()
	fmt.Println("\n  Cargando alcances de ingenieria...")
	alcances := p.metabase.Alcances()
	fmt.Println("\n  Cargando facturas anteriores (HubSpot vía Metabase)...")
	fact := p.metabase.FacturasAnteriores()
	f := fuentes{wms: wms, alcances: alcances, facturas: fact}

	fmt.Println("\n  Reconciliando estado_app_ops desde Metabase (question 15673)...")
	porID, porTitulo := p.metabase.EstadoAppOps()
	supabase.ReconciliarEstadoAppOps(p.supabase, porID, porTitulo)

	if p.cfg.ModoPrueba {
		fmt.Println()
		actas := p.metabase.ActasNuevas(p.estado.Procesadas())
		procesadas := 0
		for i, acta := range actas {
			if p.ProcesarActa(ctx, acta, f) {
				procesadas++
			}
			if i < len(actas)-1 {
				fmt.Printf("     Pausa %ds...\n", p.cfg.PausaEntreActasSeg)
				dormir(p.cfg.PausaEntreActasSeg)
			}
		}
		fmt.Println()
		fmt.Println(linea)
		fmt.Printf("   PRUEBA TERMINADA - %d acta(s) auditada(s)\n", procesadas)
		abs, _ := filepath.Abs(p.cfg.CarpetaReportes)
		fmt.Println("   Reportes en: " + abs)
		fmt.Println(linea)
		return
	}

	for {
		p.procesarPendientes(ctx, f)
		fmt.Printf("\n[%s] Verificando nuevos alcances de ingenieria...\n", util.Ahora())
		p.VerificarNuevosAlcances(f.alcances)
		if p.cfg.ModoUnico {
			return
		}
		dormir(p.cfg.IntervaloSegundos)
		f = p.cargarFuentes()
	}
}

func (p *Pipeline) procesarPendientes(ctx context.Context, f fuentes) {
	actas := p.metabase.ActasNuevas(p.estado.Procesadas())
	if len(actas) == 0 {
		fmt.Printf("[%s] Sin actas nuevas.\n", util.Ahora())
		return
	}
	for i, acta := range actas {
		p.ProcesarActa(ctx, acta, f)
		if i < len(actas)-1 {
			dormir(p.cfg.PausaEntreActasSeg)
		}
	}
}

func nilSiVacio(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func nilSiNil(s *string) any {
	if s == nil {
		return nil
	}
	return *s
}

func nilSiNilBool(b *bool) any {
	if b == nil {
		return nil
	}
	return *b
}

func contiene(lista []string, v string) bool {
	for _, x := range lista {
		if x == v {
			return true
		}
	}
	return false
}

func recortar(s string, n int) string {
	r := []rune(s)
	if len(r) > n {
		return string(r[:n])
	}
	return s
}
