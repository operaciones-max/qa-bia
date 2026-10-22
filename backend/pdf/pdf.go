// Package pdf descarga y lee los PDFs de actas y facturas con MuPDF (go-fitz):
// texto de todas las paginas e imagenes JPEG de las primeras.
package pdf

import (
	"bytes"
	"fmt"
	"image/jpeg"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gen2brain/go-fitz"
)

// Paginas que se mandan como imagen en el QA full. 0 = solo texto (ahorra tokens).
// PQR/VICO/Emergencia usan su propia vision en el QA lite (RenderizarPaginas).
const (
	MaxPaginasVision = 0
	DPIVision        = 60 // resolucion de las imagenes: mas bajo = menos tokens
)

var clienteHTTP = &http.Client{Timeout: 30 * time.Second}

// Descargar baja un archivo por HTTP GET.
func Descargar(url string) ([]byte, error) {
	resp, err := clienteHTTP.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, errorHTTP(resp.StatusCode, url)
	}
	return io.ReadAll(resp.Body)
}

// Texto extrae el texto de todas las paginas, una tras otra.
func Texto(pdfBytes []byte) (string, error) {
	doc, err := fitz.NewFromMemory(pdfBytes)
	if err != nil {
		return "", err
	}
	defer doc.Close()
	var texto strings.Builder
	for i := 0; i < doc.NumPage(); i++ {
		t, err := doc.Text(i)
		if err != nil {
			continue
		}
		if t = strings.TrimRight(t, "\n"); t != "" {
			texto.WriteString(t)
			texto.WriteString("\n")
		}
	}
	return texto.String(), nil
}

// DescargarYLeer devuelve el texto (sin espacios a los costados), las imagenes
// para el QA full y los bytes del PDF. Si falla devuelve texto vacio.
func DescargarYLeer(url string) (string, [][]byte, []byte) {
	pdfBytes, err := Descargar(url)
	if err != nil {
		fmt.Printf("  ERROR leyendo PDF: %v\n", err)
		return "", nil, nil
	}
	texto, err := Texto(pdfBytes)
	if err != nil {
		fmt.Printf("  ERROR leyendo PDF: %v\n", err)
		return "", nil, nil
	}
	imagenes := RenderizarPaginas(pdfBytes, MaxPaginasVision, DPIVision)
	return strings.TrimSpace(texto), imagenes, pdfBytes
}

// RenderizarPaginas convierte las primeras n paginas en JPEG.
func RenderizarPaginas(pdfBytes []byte, n int, dpi float64) [][]byte {
	if n <= 0 || len(pdfBytes) == 0 {
		return nil
	}
	doc, err := fitz.NewFromMemory(pdfBytes)
	if err != nil {
		fmt.Printf("  WARN: no se pudieron renderizar paginas para vision: %v\n", err)
		return nil
	}
	defer doc.Close()
	var imagenes [][]byte
	for i := 0; i < doc.NumPage() && i < n; i++ {
		img, err := doc.ImageDPI(i, dpi)
		if err != nil {
			fmt.Printf("  WARN: no se pudieron renderizar paginas para vision: %v\n", err)
			break
		}
		var buf bytes.Buffer
		if err := jpeg.Encode(&buf, img, &jpeg.Options{Quality: 95}); err != nil {
			break
		}
		imagenes = append(imagenes, buf.Bytes())
	}
	return imagenes
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
