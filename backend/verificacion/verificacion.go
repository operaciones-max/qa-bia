// Package verificacion cruza los equipos de medida de las visitas previas
// (VIPE) y las instalaciones (INST) entre tres fuentes:
//   - lo escrito en el acta (el JSON que extrae el QA full);
//   - lo que se ve en las fotos del acta (OCR, ver fotos.go);
//   - lo que dice el sistema: la factura anterior y la visita previa para lo
//     encontrado, y lo asignado en WMS para lo instalado.
//
// Tambien revisa que el acta tenga llenos todos los campos que aplican segun
// el tipo de medida, y que el factor de medida corresponda a las relaciones
// de los TCs y TPs. El resultado se guarda en el QA (verificacion_equipos) y
// es parte de las VALIDACIONES DEL BACKEND que leen los subagentes de cierre.
package verificacion

import (
	"fmt"
	"strings"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

// Entrada son los datos de una OT para verificar sus equipos.
type Entrada struct {
	TipoOT       string      // "VIPE" o "INST"
	Acta         dato.Objeto // JSON extraido del acta (QA full)
	Fotos        *Fotos      // nil = no se leyeron fotos
	Factura      Factura
	VisitaPrevia *VisitaPrevia // INST: lo que encontro la VIPE del mismo cliente
	Asignados    *Asignados    // INST: equipos asignados en WMS
}

// Factura es el serial del medidor leido en la factura anterior del cliente.
type Factura struct {
	Serial string
	Estado string // ok, ok_sin_serial, borrosa, no_disponible
}

// VisitaPrevia es lo que encontro la visita previa del mismo cliente.
type VisitaPrevia struct {
	OT           string
	MedidorSerie string
	TCsSeriales  []string
	RelacionTCs  string
}

// Asignados son los equipos asignados al cliente en WMS.
type Asignados struct {
	Medidor string
	TCs     []string
	TPs     []string
}

// Resultado de la verificacion.
type Resultado struct {
	TipoOT          string   `json:"tipo_ot"`
	TipoMedida      string   `json:"tipo_medida"`
	Aplica          Aplica   `json:"aplica"`
	FotosLeidas     bool     `json:"fotos_leidas"`
	Cruces          []Cruce  `json:"cruces"`
	CamposFaltantes []string `json:"campos_faltantes"`
	Observaciones   []string `json:"observaciones"`
}

// Verificar cruza los equipos del acta con las fotos y el sistema.
func Verificar(e Entrada) Resultado {
	acta := e.Acta
	tipoMedida := strings.ToUpper(dato.Texto(acta["tipo_medida"]))
	aplica := AplicaPara(tipoMedida)
	fotos := e.Fotos
	if fotos == nil {
		fotos = &Fotos{}
	}
	r := Resultado{
		TipoOT:          e.TipoOT,
		TipoMedida:      tipoMedida,
		Aplica:          aplica,
		FotosLeidas:     e.Fotos != nil,
		CamposFaltantes: camposFaltantes(e.TipoOT, acta, aplica),
		Observaciones:   fotos.Observaciones,
	}
	if e.Fotos == nil {
		r.Observaciones = append(r.Observaciones, "No se leyeron fotos de equipos: el cruce con la foto queda sin dato.")
	}
	if e.Factura.Serial == "" {
		r.Observaciones = append(r.Observaciones, "La factura anterior no está disponible o no se leyó su serial (estado: "+estadoFactura(e.Factura)+").")
	}

	// Medidor encontrado: acta, foto y factura anterior (y la VIPE, en una INST).
	medEnc := dato.TextoLimpio(dato.Hijo(acta, "medidor_encontrado")["serie"])
	fotoMedEnc := serieFoto(fotos.MedidorEncontrado)
	r.Cruces = append(r.Cruces, cruceSerie("Medidor encontrado", medEnc, fotoMedEnc, e.Factura.Serial, "factura anterior"))
	if e.VisitaPrevia != nil {
		r.Cruces = append(r.Cruces, cruceSerie("Medidor encontrado", medEnc, fotoMedEnc, e.VisitaPrevia.MedidorSerie, "visita previa "+e.VisitaPrevia.OT))
	}

	// TCs y TPs encontrados: series y relacion.
	var vipeTCs []string
	var vipeRelTCs, fuenteVIPE string
	if e.VisitaPrevia != nil {
		vipeTCs, vipeRelTCs, fuenteVIPE = e.VisitaPrevia.TCsSeriales, e.VisitaPrevia.RelacionTCs, "visita previa "+e.VisitaPrevia.OT
	}
	if aplica.TCs {
		r.Cruces = append(r.Cruces, cruzarGrupo("TCs encontrados", dato.Hijo(acta, "tcs_encontrados"), fotos.TCsEncontrados, vipeTCs, vipeRelTCs, fuenteVIPE)...)
	}
	if aplica.TPs {
		r.Cruces = append(r.Cruces, cruzarGrupo("TPs encontrados", dato.Hijo(acta, "tps_encontrados"), fotos.TPsEncontrados, nil, "", "")...)
	}

	// Lo instalado (INST): acta, foto y lo asignado en WMS.
	relTCs := dato.TextoLimpio(dato.Hijo(acta, "tcs_encontrados")["relacion"])
	relTPs := dato.TextoLimpio(dato.Hijo(acta, "tps_encontrados")["relacion"])
	fotoRelTCs, fotoRelTPs := relacionDe(fotos.TCsEncontrados), relacionDe(fotos.TPsEncontrados)
	if e.TipoOT == "INST" {
		asig := e.Asignados
		if asig == nil {
			asig = &Asignados{}
			r.Observaciones = append(r.Observaciones, "El cliente no tiene equipos asignados en WMS: lo instalado no se puede cruzar con el sistema.")
		}
		medInst := dato.Hijo(acta, "medidor_instalado")
		if dato.EsTrue(medInst["se_instalo"]) {
			r.Cruces = append(r.Cruces, cruceSerie("Medidor instalado", dato.TextoLimpio(medInst["serie"]),
				serieFoto(fotos.MedidorInstalado), asig.Medidor, "WMS asignado"))
		}
		if tcs := dato.Hijo(acta, "tcs_instalados"); aplica.TCs && dato.EsTrue(tcs["se_instalo"]) {
			r.Cruces = append(r.Cruces, cruzarGrupo("TCs instalados", tcs, fotos.TCsInstalados, asig.TCs, "", "WMS asignado")...)
			relTCs, fotoRelTCs = dato.TextoLimpio(tcs["relacion"]), relacionDe(fotos.TCsInstalados)
		}
		if tps := dato.Hijo(acta, "tps_instalados"); aplica.TPs && dato.EsTrue(tps["se_instalo"]) {
			r.Cruces = append(r.Cruces, cruzarGrupo("TPs instalados", tps, fotos.TPsInstalados, asig.TPs, "", "WMS asignado")...)
			relTPs, fotoRelTPs = dato.TextoLimpio(tps["relacion"]), relacionDe(fotos.TPsInstalados)
		}
	}

	// Factor de medida: el escrito contra el que dan las relaciones.
	if aplica.Conocida {
		r.Cruces = append(r.Cruces, cruceFactor(aplica, dato.TextoLimpio(acta["factor_medida"]), relTCs, relTPs, fotoRelTCs, fotoRelTPs))
	}
	return r
}

func cruceSerie(equipo, acta, foto, sistema, fuente string) Cruce {
	return Cruce{Equipo: equipo, Dato: "serie", Acta: acta, Foto: foto, Sistema: sistema, Fuente: fuente,
		ActaVsFoto: compararSerie(acta, foto), ActaVsSistema: compararSerie(acta, sistema)}
}

// cruzarGrupo cruza las series y la relacion de un grupo de TCs o TPs.
func cruzarGrupo(equipo string, bloque dato.Objeto, placas []PlacaFoto, sistema []string, relSistema, fuente string) []Cruce {
	var seriales []string
	for _, serie := range dato.Textos(bloque["seriales"]) {
		if !vacio(serie) {
			seriales = append(seriales, serie)
		}
	}
	cruces := cruzarSeries(equipo, seriales, seriesDe(placas), sistema, fuente)
	relActa, relFoto := dato.TextoLimpio(bloque["relacion"]), relacionDe(placas)
	return append(cruces, Cruce{Equipo: equipo, Dato: "relación", Acta: relActa, Foto: relFoto,
		Sistema: relSistema, Fuente: fuente,
		ActaVsFoto: compararRelacion(relActa, relFoto), ActaVsSistema: compararRelacion(relActa, relSistema)})
}

// cruceFactor compara el factor escrito con el que dan las relaciones del
// acta (columna sistema) y de las fotos (columna foto).
func cruceFactor(aplica Aplica, factorActa, relTCs, relTPs, fotoRelTCs, fotoRelTPs string) Cruce {
	c := Cruce{Equipo: "Factor de medida", Dato: "factor", Acta: factorActa, Fuente: "relaciones escritas en el acta"}
	if !aplica.TCs {
		c.Fuente = "medida directa"
	}
	if f, ok := FactorEsperado(aplica, relTCs, relTPs); ok {
		c.Sistema = formatoFactor(f)
	}
	if f, ok := FactorEsperado(aplica, fotoRelTCs, fotoRelTPs); ok && (aplica.TCs || fotoRelTCs != "") {
		c.Foto = formatoFactor(f)
	}
	c.ActaVsFoto, c.ActaVsSistema = compararFactor(factorActa, c.Foto), compararFactor(factorActa, c.Sistema)
	return c
}

func compararFactor(acta, otro string) Estado {
	o, okO := numero(otro)
	switch {
	case !okO:
		return SinDato
	case acta == "":
		return FaltaEnActa
	}
	if a, ok := numero(acta); ok && casiIgual(a, o) {
		return Coincide
	}
	return NoCoincide
}

func serieFoto(s *SerieFoto) string {
	if s == nil {
		return ""
	}
	return s.Serie
}

func estadoFactura(f Factura) string {
	if f.Estado == "" {
		return "no_disponible"
	}
	return f.Estado
}

// Hallazgos resume en frases lo que no cuadra, para los errores del QA y el dashboard.
func (r Resultado) Hallazgos() []string {
	var out []string
	for _, c := range r.Cruces {
		nombre := c.Equipo + " (" + c.Dato + ")"
		out = append(out, frase(nombre, c.Acta, c.Foto, "la foto", c.ActaVsFoto)...)
		out = append(out, frase(nombre, c.Acta, c.Sistema, c.Fuente, c.ActaVsSistema)...)
	}
	if len(r.CamposFaltantes) > 0 {
		out = append(out, "Campos sin diligenciar: "+strings.Join(r.CamposFaltantes, ", "))
	}
	return out
}

func frase(nombre, acta, otro, fuente string, e Estado) []string {
	switch e {
	case NoCoincide:
		if otro == "" {
			return []string{fmt.Sprintf("%s: %q no está en %s", nombre, acta, fuente)}
		}
		return []string{fmt.Sprintf("%s: el acta dice %q y %s dice %q", nombre, acta, fuente, otro)}
	case ErrorDigitacion:
		return []string{fmt.Sprintf("%s: el acta dice %q y %s dice %q (difieren en 1 o 2 caracteres: posible error de digitación)", nombre, acta, fuente, otro)}
	case FaltaEnActa:
		return []string{fmt.Sprintf("%s: no está en el acta y %s dice %q", nombre, fuente, otro)}
	}
	return nil
}
