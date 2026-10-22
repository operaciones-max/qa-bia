package extraccion

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"syscall"
	"time"
)

// MaxBytesArchivo es el tamano maximo del archivo a descargar.
const MaxBytesArchivo = 20 << 20

// Descargador baja el archivo del link. Como el link lo manda quien llama al
// servicio, solo se conecta a IPs publicas: no puede usarse para leer servicios
// internos (localhost, red privada, metadatos de la nube).
type Descargador struct {
	cliente  *http.Client
	maxBytes int64
}

// NuevoDescargador crea el descargador. permitirRedLocal solo es para pruebas.
func NuevoDescargador(permitirRedLocal bool) *Descargador {
	dialer := &net.Dialer{Timeout: 10 * time.Second}
	if !permitirRedLocal {
		dialer.Control = soloIPsPublicas
	}
	transporte := &http.Transport{
		Proxy:                 nil, // conexion directa: el control de IPs mira el destino real
		DialContext:           dialer.DialContext,
		TLSHandshakeTimeout:   10 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
	}
	return &Descargador{
		cliente:  &http.Client{Transport: transporte, Timeout: 2 * time.Minute},
		maxBytes: MaxBytesArchivo,
	}
}

// Descargar baja el archivo. Los errores ya traen el codigo HTTP para responder.
func (d *Descargador) Descargar(ctx context.Context, link string) ([]byte, error) {
	u, err := url.Parse(link)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return nil, nuevoError(http.StatusBadRequest, err, "el link debe ser una URL http o https")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, nuevoError(http.StatusBadRequest, err, "link invalido")
	}
	resp, err := d.cliente.Do(req)
	if err != nil {
		if errors.Is(err, errDestinoNoPermitido) {
			return nil, nuevoError(http.StatusBadRequest, err, "el link apunta a una direccion interna; debe ser publico")
		}
		return nil, nuevoError(http.StatusBadGateway, err, "no se pudo descargar el link")
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, nuevoError(http.StatusBadGateway, nil, "el link respondio %d %s", resp.StatusCode, http.StatusText(resp.StatusCode))
	}
	if resp.ContentLength > d.maxBytes {
		return nil, archivoMuyGrande(d.maxBytes)
	}
	datos, err := io.ReadAll(io.LimitReader(resp.Body, d.maxBytes+1))
	if err != nil {
		return nil, nuevoError(http.StatusBadGateway, err, "se corto la descarga del link")
	}
	if int64(len(datos)) > d.maxBytes {
		return nil, archivoMuyGrande(d.maxBytes)
	}
	if len(datos) == 0 {
		return nil, nuevoError(http.StatusUnprocessableEntity, nil, "el link devolvio un archivo vacio")
	}
	return datos, nil
}

func archivoMuyGrande(max int64) *Error {
	return nuevoError(http.StatusRequestEntityTooLarge, nil, "el archivo supera los %d MB", max>>20)
}

var errDestinoNoPermitido = errors.New("destino no permitido")

// cgnat es el rango 100.64.0.0/10 (red compartida de operadores), que no es publico.
var cgnat = &net.IPNet{IP: net.IPv4(100, 64, 0, 0), Mask: net.CIDRMask(10, 32)}

// soloIPsPublicas se ejecuta en cada conexion (tambien en las redirecciones),
// ya con la IP resuelta.
func soloIPsPublicas(_, direccion string, _ syscall.RawConn) error {
	host, _, err := net.SplitHostPort(direccion)
	if err != nil {
		return err
	}
	ip := net.ParseIP(host)
	if ip == nil || !esPublica(ip) {
		return fmt.Errorf("%w: %s", errDestinoNoPermitido, host)
	}
	return nil
}

func esPublica(ip net.IP) bool {
	return !(ip.IsLoopback() || ip.IsPrivate() || ip.IsUnspecified() ||
		ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() ||
		ip.IsInterfaceLocalMulticast() || ip.IsMulticast() || cgnat.Contains(ip))
}
