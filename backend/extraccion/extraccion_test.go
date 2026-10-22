package extraccion

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/ia"
)

// pdfConTexto arma un PDF minimo de una pagina con el texto dado (MuPDF
// reconstruye la tabla xref que falta).
func pdfConTexto(texto string) []byte {
	contenido := ""
	if texto != "" {
		contenido = fmt.Sprintf("BT /F1 12 Tf 72 720 Td (%s) Tj ET", texto)
	}
	return []byte(fmt.Sprintf(`%%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length %d >> stream
%s
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
trailer << /Root 1 0 R >>
%%%%EOF
`, len(contenido), contenido))
}

func pngDePrueba(t *testing.T) []byte {
	img := image.NewRGBA(image.Rect(0, 0, 4, 4))
	img.Set(1, 1, color.Black)
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

const textoRUT = "NIT 901835098 SUPERMERCADOS OPTIMERKA SAS PITALITO HUILA"

func TestPrepararDocumentoPDFConTexto(t *testing.T) {
	doc, err := PrepararDocumento(pdfConTexto(textoRUT))
	if err != nil {
		t.Fatal(err)
	}
	if doc.Tipo != "pdf" || doc.Paginas != 1 || Metodo(doc) != "texto" {
		t.Fatalf("doc = %+v", doc)
	}
	if !strings.Contains(doc.Texto[0].Texto, "OPTIMERKA") {
		t.Errorf("texto = %q", doc.Texto[0].Texto)
	}
}

func TestPrepararDocumentoPDFEscaneadoVaComoImagen(t *testing.T) {
	doc, err := PrepararDocumento(pdfConTexto(""))
	if err != nil {
		t.Fatal(err)
	}
	if Metodo(doc) != "imagenes" || len(doc.Imagenes) != 1 || doc.Imagenes[0].Numero != 1 {
		t.Fatalf("doc = %+v", doc)
	}
	if doc.Imagenes[0].Imagen.Tipo != "image/jpeg" || len(doc.Imagenes[0].Imagen.Datos) == 0 {
		t.Error("la pagina escaneada deberia ir como JPEG")
	}
}

func TestPrepararDocumentoImagenYTiposNoSoportados(t *testing.T) {
	doc, err := PrepararDocumento(pngDePrueba(t))
	if err != nil || doc.Tipo != "imagen" || doc.Imagenes[0].Imagen.Tipo != "image/png" {
		t.Fatalf("doc = %+v, err = %v", doc, err)
	}
	_, err = PrepararDocumento([]byte("hola, esto es texto plano"))
	var e *Error
	if !errors.As(err, &e) || e.Codigo != http.StatusUnsupportedMediaType {
		t.Fatalf("err = %v", err)
	}
}

func TestDescargadorBloqueaDireccionesInternas(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Write([]byte("secreto"))
	}))
	defer srv.Close()

	_, err := NuevoDescargador(false).Descargar(context.Background(), srv.URL)
	var e *Error
	if !errors.As(err, &e) || e.Codigo != http.StatusBadRequest {
		t.Fatalf("deberia rechazar localhost, err = %v", err)
	}
	for _, ip := range []string{"10.0.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "::1", "fd00::1"} {
		if esPublica(net.ParseIP(ip)) {
			t.Errorf("%s no es publica", ip)
		}
	}
	if !esPublica(net.ParseIP("8.8.8.8")) {
		t.Error("8.8.8.8 es publica")
	}
}

func TestDescargadorValidaLinkTamanoYEstado(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/grande":
			w.Write(bytes.Repeat([]byte("x"), 2000))
		case "/no-existe":
			http.NotFound(w, r)
		default:
			w.Write([]byte("ok"))
		}
	}))
	defer srv.Close()
	d := NuevoDescargador(true)
	d.maxBytes = 1000

	casos := map[string]int{
		"ftp://ejemplo.com/a.pdf": http.StatusBadRequest,
		srv.URL + "/grande":       http.StatusRequestEntityTooLarge,
		srv.URL + "/no-existe":    http.StatusBadGateway,
	}
	for link, codigo := range casos {
		_, err := d.Descargar(context.Background(), link)
		var e *Error
		if !errors.As(err, &e) || e.Codigo != codigo {
			t.Errorf("%s: err = %v, esperado %d", link, err, codigo)
		}
	}
	if datos, err := d.Descargar(context.Background(), srv.URL+"/ok"); err != nil || string(datos) != "ok" {
		t.Errorf("datos = %q, err = %v", datos, err)
	}
}

type extractorFalso struct {
	instruccion string
	doc         ia.Documento
	err         error
}

func (f *extractorFalso) ExtraerInformacion(_ context.Context, instruccion string, doc ia.Documento, _ string) (ia.RespuestaExtraccion, error) {
	f.instruccion, f.doc = instruccion, doc
	if f.err != nil {
		return ia.RespuestaExtraccion{}, f.err
	}
	return ia.RespuestaExtraccion{
		JSON:   json.RawMessage(`{"nombre_cliente": "SUPERMERCADOS OPTIMERKA SAS", "numero_documento": "901835098"}`),
		Modelo: "claude-opus-5-5", TokensEntrada: 900, TokensSalida: 120,
	}, nil
}

type repoFalso struct{ registros []Registro }

func (r *repoFalso) Guardar(_ context.Context, reg Registro) (int64, error) {
	r.registros = append(r.registros, reg)
	return int64(len(r.registros)), nil
}

func servidorDeArchivos(t *testing.T) *httptest.Server {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Write(pdfConTexto(textoRUT))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func pedir(h http.Handler, cuerpo string, cabeceras map[string]string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, RutaExtraccion, strings.NewReader(cuerpo))
	for k, v := range cabeceras {
		req.Header.Set(k, v)
	}
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestHandlerDevuelveElJSONYGuardaLaSolicitud(t *testing.T) {
	archivos := servidorDeArchivos(t)
	ext, repo := &extractorFalso{}, &repoFalso{}
	h := NuevoHandler(NuevoServicio(NuevoDescargador(true), ext, repo, ""), "")

	cuerpo := fmt.Sprintf(`{"link": %q, "prompt": "Extrae {\"nombre_cliente\": \"\", \"numero_documento\": \"\"}"}`, archivos.URL+"/rut.pdf")
	rec := pedir(h, cuerpo, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("status %d: %s", rec.Code, rec.Body)
	}
	// El cuerpo es el JSON tal como lo devolvio Claude (mismo orden de claves).
	if !strings.HasPrefix(rec.Body.String(), `{"nombre_cliente"`) {
		t.Errorf("cuerpo = %s", rec.Body)
	}
	if rec.Header().Get("X-Extraccion-Id") != "1" || rec.Header().Get("X-Extraccion-Metodo") != "texto" {
		t.Errorf("cabeceras = %v", rec.Header())
	}
	if !strings.Contains(ext.instruccion, "nombre_cliente") || ext.doc.Tipo != "pdf" {
		t.Errorf("Claude recibio %q / %+v", ext.instruccion, ext.doc)
	}
	if len(repo.registros) != 1 {
		t.Fatalf("registros = %d", len(repo.registros))
	}
	reg := repo.registros[0]
	if reg.Solicitud.Link != archivos.URL+"/rut.pdf" || reg.Error != "" || reg.Modelo != "claude-opus-5-5" || reg.TokensSalida != 120 {
		t.Errorf("registro = %+v", reg)
	}
	fila, _ := json.Marshal(Fila(reg))
	for _, columna := range []string{`"respuesta":{"nombre_cliente"`, `"solicitud":{"link"`, `"tipo_archivo":"pdf"`, `"metodo":"texto"`} {
		if !strings.Contains(string(fila), columna) {
			t.Errorf("fila sin %s: %s", columna, fila)
		}
	}
}

func TestHandlerErrores(t *testing.T) {
	archivos := servidorDeArchivos(t)
	repo := &repoFalso{}
	conClave := NuevoHandler(NuevoServicio(NuevoDescargador(true), &extractorFalso{}, repo, ""), "clave-secreta")
	cuerpoOK := fmt.Sprintf(`{"link": %q, "prompt": "Extrae {}"}`, archivos.URL)

	if rec := pedir(conClave, cuerpoOK, nil); rec.Code != http.StatusUnauthorized {
		t.Errorf("sin clave: %d", rec.Code)
	}
	if rec := pedir(conClave, cuerpoOK, map[string]string{"Authorization": "Bearer clave-secreta"}); rec.Code != http.StatusOK {
		t.Errorf("con Bearer: %d %s", rec.Code, rec.Body)
	}
	if rec := pedir(conClave, cuerpoOK, map[string]string{"X-API-Key": "clave-secreta"}); rec.Code != http.StatusOK {
		t.Errorf("con X-API-Key: %d %s", rec.Code, rec.Body)
	}

	sinClave := NuevoHandler(NuevoServicio(NuevoDescargador(true), &extractorFalso{}, nil, ""), "")
	if rec := pedir(sinClave, `{"link": ""}`, nil); rec.Code != http.StatusBadRequest || !strings.Contains(rec.Body.String(), `"error"`) {
		t.Errorf("sin link: %d %s", rec.Code, rec.Body)
	}
	if rec := pedir(sinClave, `no es json`, nil); rec.Code != http.StatusBadRequest {
		t.Errorf("cuerpo invalido: %d", rec.Code)
	}

	// Un fallo de Claude tambien queda registrado, con su error.
	repo = &repoFalso{}
	conFallo := NuevoHandler(NuevoServicio(NuevoDescargador(true), &extractorFalso{err: ia.ErrSinJSON}, repo, ""), "")
	if rec := pedir(conFallo, cuerpoOK, nil); rec.Code != http.StatusUnprocessableEntity {
		t.Errorf("sin JSON: %d %s", rec.Code, rec.Body)
	}
	if len(repo.registros) != 1 || repo.registros[0].Error == "" || repo.registros[0].Respuesta != nil {
		t.Errorf("registros = %+v", repo.registros)
	}
}
