package estado

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/config"
)

func nuevo(t *testing.T) (*Estado, config.Config) {
	t.Helper()
	dir := t.TempDir()
	cfg := config.Config{
		StateDir:                  dir,
		ArchivoProcesados:         filepath.Join(dir, "actas_procesadas.json"),
		ArchivoVisitasPrevias:     filepath.Join(dir, "visitas_previas.json"),
		ArchivoAlcancesProcesados: filepath.Join(dir, "alcances_procesados.json"),
		ArchivoFacturasExtraidas:  filepath.Join(dir, "facturas_extraidas.json"),
		ArchivoCooldownLLM:        filepath.Join(dir, "llm_cooldown.json"),
	}
	return New(cfg), cfg
}

// El formato debe ser el de json.dump(indent=2, ensure_ascii=False) de Python,
// y reescribir no debe cambiar el orden de las claves existentes.
func TestFormatoYOrdenComoPython(t *testing.T) {
	e, cfg := nuevo(t)
	original := "{\n  \"CO2\": {\n    \"b\": 1,\n    \"a\": \"Medición\"\n  },\n  \"CO1\": {}\n}"
	os.WriteFile(cfg.ArchivoVisitasPrevias, []byte(original), 0o644)
	if err := e.GuardarVisitaPrevia("CO1", VisitaPrevia{OTNombre: "VIPE_1 <&>"}); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(cfg.ArchivoVisitasPrevias)
	esperado := "{\n  \"CO2\": {\n    \"b\": 1,\n    \"a\": \"Medición\"\n  },\n  \"CO1\": {\n    \"ot_nombre\": \"VIPE_1 <&>\",\n" +
		"    \"fecha_procesada\": \"\",\n    \"tipo_medida\": null,\n    \"factor_medida\": null,\n    \"medidor_encontrado\": null,\n" +
		"    \"medidor_enc_serie\": null,\n    \"tcs_encontrados\": null,\n    \"tps_encontrados\": null,\n    \"tecnico_nombre\": null,\n" +
		"    \"tecnico_empresa\": null,\n    \"contratista_nombre\": null,\n    \"observacion_tecnico_verbatim\": null\n  }\n}"
	if string(data) != esperado {
		t.Fatalf("archivo:\n%s", data)
	}
}

func TestProcesadasSinDuplicadosYLimpieza(t *testing.T) {
	e, cfg := nuevo(t)
	e.MarcarProcesada("a")
	e.MarcarProcesada("b")
	e.MarcarProcesada("a")
	data, _ := os.ReadFile(cfg.ArchivoProcesados)
	if string(data) != "[\n  \"a\",\n  \"b\"\n]" {
		t.Fatalf("archivo: %s", data)
	}
	antes, despues, existe, _ := e.QuitarProcesadas(map[string]bool{"a": true})
	if antes != 2 || despues != 1 || !existe {
		t.Fatalf("antes=%d despues=%d existe=%v", antes, despues, existe)
	}
}

func TestCooldownSeActivaYSeLee(t *testing.T) {
	e, _ := nuevo(t)
	c := e.ActivarCooldown("rate limit, try again in 30 seconds")
	if c.Razon != "per_minute" || e.CooldownActivo() == nil {
		t.Fatalf("cooldown no activo: %+v", c)
	}
	if e.ActivarCooldown("tokens per day exceeded").Razon != "daily_quota" {
		t.Fatal("deberia ser cuota diaria")
	}
}
