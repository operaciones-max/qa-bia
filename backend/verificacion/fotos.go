package verificacion

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"

	"github.com/operaciones-max/qa-bia/backend/ia"
	"github.com/operaciones-max/qa-bia/backend/pdf"
)

const (
	// MaxPaginasFotos es el maximo de paginas con fotos que se mandan al OCR.
	MaxPaginasFotos = 12
	// DPIFotos: resolucion para que se lean series y placas dentro de las fotos.
	DPIFotos = 150
)

// Fotos es lo que el OCR leyo en las fotos del acta (prompts/fotos_equipos.md).
type Fotos struct {
	MedidorEncontrado *SerieFoto  `json:"medidor_encontrado"`
	MedidorInstalado  *SerieFoto  `json:"medidor_instalado"`
	TCsEncontrados    []PlacaFoto `json:"tcs_encontrados"`
	TCsInstalados     []PlacaFoto `json:"tcs_instalados"`
	TPsEncontrados    []PlacaFoto `json:"tps_encontrados"`
	TPsInstalados     []PlacaFoto `json:"tps_instalados"`
	Observaciones     []string    `json:"observaciones"`
}

// SerieFoto es la serie de un medidor leida en una foto.
type SerieFoto struct {
	Serie  string `json:"serie"`
	Pagina int    `json:"pagina"`
}

// PlacaFoto es la placa de un TC o TP leida en una foto.
type PlacaFoto struct {
	Serie    string `json:"serie"`
	Relacion string `json:"relacion"`
	Pagina   int    `json:"pagina"`
}

// LectorFotos lee las fotos de los equipos. Hoy es Claude (ia.Cliente); cuando
// el OCR propio pase al backend se conecta aqui, con la misma interfaz.
type LectorFotos interface {
	LeerFotosEquipos(ctx context.Context, paginas []ia.PaginaImagen, tipoOT, tipoMedida string) (json.RawMessage, error)
}

var (
	// Cada foto del acta lleva un sello "Bia 2 may 2026 09:52:45".
	reSelloFoto = regexp.MustCompile(`(?i)\bbia\s+\d{1,2}\s+\p{L}{3,}\.?\s+\d{4}`)
	reEquipos   = regexp.MustCompile(`(?i)medidor|\btcs?\b|\btps?\b|transformador|placa|celda`)
)

// PaginasConFotos elige las paginas del acta que tienen fotos de equipos de
// medida (sello de foto + mencion de medidor, TC, TP…), hasta MaxPaginasFotos.
func PaginasConFotos(textos []string) (paginas []int, recortadas bool) {
	for i, t := range textos {
		if reSelloFoto.MatchString(t) && reEquipos.MatchString(t) {
			if len(paginas) == MaxPaginasFotos {
				return paginas, true
			}
			paginas = append(paginas, i)
		}
	}
	return paginas, false
}

// LeerFotos manda al OCR las paginas del acta con fotos de equipos. Devuelve
// nil si el acta no tiene fotos de equipos reconocibles.
func LeerFotos(ctx context.Context, lector LectorFotos, pdfBytes []byte, tipoOT, tipoMedida string) (*Fotos, error) {
	textos, err := pdf.TextoPorPagina(pdfBytes)
	if err != nil {
		return nil, err
	}
	indices, recortadas := PaginasConFotos(textos)
	if len(indices) == 0 {
		return nil, nil
	}
	imagenes, err := pdf.RenderizarSeleccion(pdfBytes, indices, DPIFotos)
	if err != nil {
		return nil, err
	}
	paginas := make([]ia.PaginaImagen, len(imagenes))
	for i, img := range imagenes {
		paginas[i] = ia.PaginaImagen{Numero: indices[i] + 1, Imagen: ia.Imagen{Tipo: "image/jpeg", Datos: img}}
	}
	crudo, err := lector.LeerFotosEquipos(ctx, paginas, tipoOT, tipoMedida)
	if err != nil {
		return nil, err
	}
	var fotos Fotos
	if err := json.Unmarshal(crudo, &fotos); err != nil {
		return nil, fmt.Errorf("respuesta del OCR de fotos: %w", err)
	}
	if recortadas {
		fotos.Observaciones = append(fotos.Observaciones,
			fmt.Sprintf("Se leyeron solo las primeras %d páginas con fotos.", MaxPaginasFotos))
	}
	return &fotos, nil
}

func seriesDe(placas []PlacaFoto) []string {
	var series []string
	for _, p := range placas {
		if p.Serie != "" {
			series = append(series, p.Serie)
		}
	}
	return series
}

// relacionDe devuelve la relacion de un grupo de placas, o "" si no se leyo.
// Si las placas muestran relaciones distintas las devuelve juntas.
func relacionDe(placas []PlacaFoto) string {
	var distintas []string
	for _, p := range placas {
		if p.Relacion == "" {
			continue
		}
		repetida := false
		for _, d := range distintas {
			repetida = repetida || mismaRelacion(d, p.Relacion)
		}
		if !repetida {
			distintas = append(distintas, p.Relacion)
		}
	}
	switch len(distintas) {
	case 0:
		return ""
	case 1:
		return distintas[0]
	}
	todas := distintas[0]
	for _, d := range distintas[1:] {
		todas += " | " + d
	}
	return todas
}
