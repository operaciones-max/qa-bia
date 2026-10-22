package validaciones

import (
	"reflect"
	"testing"

	"github.com/operaciones-max/qa-bia/backend/dato"
)

func TestDirectaDesactivaTCsTPsYVisitaPreviaDesactivaInstalados(t *testing.T) {
	qa := dato.Objeto{
		"tipo_medida":       "DIRECTA",
		"tcs_encontrados":   dato.Objeto{"aplica": true},
		"medidor_instalado": dato.Objeto{"aplica": true},
		"fotos_tcs":         3,
	}
	AplicarReglasMedidaServicio(qa, "Visita previa")
	if dato.Hijo(qa, "tcs_encontrados")["aplica"] != false || dato.Hijo(qa, "medidor_instalado")["aplica"] != false {
		t.Fatalf("aplica deberia quedar en false: %v", qa)
	}
	if qa["fotos_tcs"] != nil {
		t.Fatalf("fotos_tcs deberia ser nil")
	}
}

func TestCoincidenciaWMSPorConjuntoNormalizado(t *testing.T) {
	qa := dato.Objeto{
		"tipo_medida":       "SEMIDIRECTA",
		"medidor_instalado": dato.Objeto{"serie": "000123456"},
		"tcs_instalados":    dato.Objeto{"seriales": []any{"tc 2", "TC-1", "TC-3"}},
	}
	ValidarCoincidenciaWMS(qa, "123456", []string{"TC-1", "TC2"}, nil, true)
	if qa["medidor_coincide_wms"] != true || qa["tcs_coinciden_wms"] != true || qa["tps_coinciden_wms"] != nil {
		t.Fatalf("coincidencias inesperadas: %v %v %v", qa["medidor_coincide_wms"], qa["tcs_coinciden_wms"], qa["tps_coinciden_wms"])
	}
}

func TestErroresFantasmaYFallidaSimplificada(t *testing.T) {
	qa := dato.Objeto{
		"tipo_medida":        "DIRECTA",
		"estado_ot":          "FALLIDA",
		"or_firma":           "NO",
		"validaciones":       dato.Objeto{"errores_encontrados": []any{"No se reporta lectura", "TCs sin sellos", "Error real"}},
		"alertas_qa":         []any{"Error real", "Alerta menor"},
		"tipificacion_falla": dato.Objeto{"cinco_por_que": []any{"1"}},
	}
	LimpiarErroresFantasma(qa, "Instalación")
	if got := dato.Hijo(qa, "validaciones")["errores_encontrados"]; !reflect.DeepEqual(got, []any{"Error real"}) {
		t.Fatalf("errores = %v", got)
	}
	if got := qa["alertas_qa"]; !reflect.DeepEqual(got, []any{"Alerta menor"}) {
		t.Fatalf("alertas = %v", got)
	}
	SimplificarFallida(qa)
	if got := dato.Hijo(qa, "validaciones")["errores_encontrados"]; !reflect.DeepEqual(got, []any{}) {
		t.Fatalf("errores tras simplificar = %v", got)
	}
	if got := qa["alertas_qa"]; !reflect.DeepEqual(got, []any{"El Operador de Red NO firmó el acta."}) {
		t.Fatalf("alertas tras simplificar = %v", got)
	}
	if got := dato.Hijo(qa, "tipificacion_falla")["cinco_por_que"]; !reflect.DeepEqual(got, []any{}) {
		t.Fatalf("cinco_por_que = %v", got)
	}
}

func TestCorregirSerieFotoCuandoLaObservacionTraeLaMismaSerie(t *testing.T) {
	item := dato.Objeto{"serie": "123-456", "serie_coincide_foto": false, "observacion_serie_foto": "se ve 0123456"}
	CorregirSerieFoto(item)
	if item["serie_coincide_foto"] != true || item["observacion_serie_foto"] != nil {
		t.Fatalf("no se corrigio: %v", item)
	}
}
