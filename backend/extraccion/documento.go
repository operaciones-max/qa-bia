package extraccion

import (
	"net/http"
	"strings"
	"unicode"

	"github.com/operaciones-max/qa-bia/backend/ia"
	"github.com/operaciones-max/qa-bia/backend/pdf"
)

const (
	// MaxBytesImagen es el maximo que acepta la API de Claude por imagen.
	MaxBytesImagen = 5 << 20
	// MaxPaginasImagen es el maximo de paginas escaneadas que se mandan como imagen.
	MaxPaginasImagen = 20
	// DPIOCR: Claude reduce las imagenes de mas de 1568 px; a 130 DPI una
	// pagina carta o A4 queda por debajo y se lee bien.
	DPIOCR = 130
	// Una pagina con menos letras y numeros que esto se trata como escaneada.
	minCaracteresTexto = 40
)

// tiposImagen son las imagenes que Claude acepta tal cual.
var tiposImagen = map[string]bool{"image/jpeg": true, "image/png": true, "image/gif": true, "image/webp": true}

// PrepararDocumento detecta el tipo de archivo por su contenido y lo deja listo
// para Claude. De un PDF se usa el texto de cada pagina y las paginas sin texto
// (escaneadas) se mandan como imagen para que Claude las lea.
func PrepararDocumento(datos []byte) (ia.Documento, error) {
	tipo := http.DetectContentType(datos)
	if i := strings.Index(tipo, ";"); i != -1 {
		tipo = tipo[:i]
	}
	switch {
	case tipo == "application/pdf":
		return prepararPDF(datos)
	case tiposImagen[tipo]:
		if len(datos) > MaxBytesImagen {
			return ia.Documento{}, nuevoError(http.StatusRequestEntityTooLarge, nil,
				"la imagen supera los %d MB que acepta Claude", MaxBytesImagen>>20)
		}
		return ia.Documento{
			Tipo:     "imagen",
			Paginas:  1,
			Imagenes: []ia.PaginaImagen{{Numero: 1, Imagen: ia.Imagen{Tipo: tipo, Datos: datos}}},
		}, nil
	default:
		return ia.Documento{}, nuevoError(http.StatusUnsupportedMediaType, nil,
			"tipo de archivo no soportado (%s): se aceptan PDF, JPEG, PNG, GIF y WEBP", tipo)
	}
}

func prepararPDF(datos []byte) (ia.Documento, error) {
	paginas, err := pdf.TextoPorPagina(datos)
	if err != nil {
		return ia.Documento{}, nuevoError(http.StatusUnprocessableEntity, err, "no se pudo abrir el PDF")
	}
	if len(paginas) == 0 {
		return ia.Documento{}, nuevoError(http.StatusUnprocessableEntity, nil, "el PDF no tiene paginas")
	}
	doc := ia.Documento{Tipo: "pdf", Paginas: len(paginas)}
	var escaneadas []int
	for i, texto := range paginas {
		if caracteresUtiles(texto) >= minCaracteresTexto {
			doc.Texto = append(doc.Texto, ia.PaginaTexto{Numero: i + 1, Texto: strings.TrimSpace(texto)})
		} else {
			escaneadas = append(escaneadas, i)
		}
	}
	if len(escaneadas) > MaxPaginasImagen {
		return ia.Documento{}, nuevoError(http.StatusUnprocessableEntity, nil,
			"el PDF tiene %d paginas escaneadas; el maximo es %d", len(escaneadas), MaxPaginasImagen)
	}
	if len(escaneadas) > 0 {
		imagenes, err := pdf.RenderizarSeleccion(datos, escaneadas, DPIOCR)
		if err != nil {
			return ia.Documento{}, nuevoError(http.StatusUnprocessableEntity, err, "no se pudieron convertir en imagen las paginas escaneadas")
		}
		for j, img := range imagenes {
			doc.Imagenes = append(doc.Imagenes, ia.PaginaImagen{
				Numero: escaneadas[j] + 1,
				Imagen: ia.Imagen{Tipo: "image/jpeg", Datos: img},
			})
		}
	}
	return doc, nil
}

// Metodo dice como llego el documento a Claude: "texto", "imagenes" o "mixto".
func Metodo(doc ia.Documento) string {
	switch {
	case len(doc.Imagenes) == 0:
		return "texto"
	case len(doc.Texto) == 0:
		return "imagenes"
	default:
		return "mixto"
	}
}

func caracteresUtiles(s string) int {
	n := 0
	for _, r := range s {
		if unicode.IsLetter(r) || unicode.IsDigit(r) {
			n++
		}
	}
	return n
}
