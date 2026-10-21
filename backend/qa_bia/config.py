"""Configuracion del motor de QA.

Los valores por defecto son los de produccion (GitHub Actions). Los secretos y
los modos de ejecucion se leen de variables de entorno; en local se pueden
poner en backend/.env (ver backend/.env.example). Las variables ya definidas
en el entorno tienen prioridad sobre el archivo .env.

Supabase (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY) y
METABASE_API_KEY se leen directamente de os.environ en los modulos que las usan.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _cargar_env_local(ruta):
    """Carga un archivo .env simple (CLAVE=valor) sin pisar variables existentes."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def _env_bool(nombre, default):
    valor = os.environ.get(nombre, "").strip().lower()
    if not valor:
        return default
    return valor in ("1", "true", "si", "sí", "yes")


def _env_int(nombre, default):
    valor = os.environ.get(nombre, "").strip()
    return int(valor) if valor else default


_cargar_env_local(BACKEND_DIR / ".env")

# --- Fuentes Metabase (preguntas publicas en CSV) ---
METABASE_CSV_URL     = "https://bia.metabaseapp.com/public/question/5ec265f5-182d-409d-bfbd-45303880da2d.csv"
WMS_CSV_URL          = "https://bia.metabaseapp.com/public/question/67f6d437-6326-415a-a799-1ee34b9648b0.csv"
ALCANCES_CSV_URL     = "https://bia.metabaseapp.com/public/question/52353a69-6510-405b-9bbd-754d762a2597.csv"

# --- IA ---
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY", "").strip()
# claude-haiku-4-5 = cheap+fast; claude-sonnet-4-6 = balanced; claude-opus-4-7 = most capable
CLAUDE_MODEL         = os.environ.get("CLAUDE_MODEL", "").strip() or "claude-haiku-4-5-20251001"

# --- Notificaciones ---
SLACK_WEBHOOK_URL    = ""  # Sin Slack — solo Supabase

# --- Modos de ejecucion ---
MODO_PRUEBA          = _env_bool("QA_MODO_PRUEBA", False)
MODO_UNICO           = _env_bool("QA_MODO_UNICO", True)
MODO_BACKFILL        = False  # False = notificaciones activas en Slack/WhatsApp/Cooldown
ACTAS_PRUEBA         = _env_int("QA_ACTAS_PRUEBA", 2)
FECHA_INICIO          = os.environ.get("QA_FECHA_INICIO", "").strip() or "2026-05-10"
FECHA_INICIO_ALCANCES = os.environ.get("QA_FECHA_INICIO_ALCANCES", "").strip() or "2026-04-30"
PAUSA_GROQ_SEGUNDOS  = 20
INTERVALO_SEGUNDOS   = 300
MAX_ACTAS_POR_RUN    = _env_int("QA_MAX_ACTAS_POR_RUN", 30)

# --- Estado persistente y reportes ---
# QA_STATE_DIR relativo se resuelve contra backend/ (uno absoluto se usa tal cual).
STATE_DIR = BACKEND_DIR / (os.environ.get("QA_STATE_DIR", "").strip() or "state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVO_PROCESADOS          = str(STATE_DIR / "actas_procesadas.json")
ARCHIVO_VISITAS_PREVIAS     = str(STATE_DIR / "visitas_previas.json")
ARCHIVO_ALCANCES_PROCESADOS = str(STATE_DIR / "alcances_procesados.json")
ARCHIVO_FACTURAS_EXTRAIDAS  = str(STATE_DIR / "facturas_extraidas.json")
ARCHIVO_COOLDOWN_LLM        = str(STATE_DIR / "llm_cooldown.json")
CARPETA_REPORTES     = str(BACKEND_DIR / "reportes_qa")

# --- Reglas de negocio ---
TIPOS_SERVICIO_VALIDOS = ["Instalación", "Visita previa"]
ESTADOS_EXITOSOS       = ["CLOSURE_SUCCESSFUL", "COMPLETED"]
ESTADOS_FALLIDOS       = ["CLOSURE_FAILED", "ELECTRICIAN_FAILED_VISIT"]
ESTADOS_ANALIZAR       = ESTADOS_EXITOSOS + ESTADOS_FALLIDOS
OR_PLANNERS = {
    "ESSA":   "Ervison Plata",
    "EPM":    "Ervison Plata",
    "AIRE":   "Ervison Plata",
    "AIR-E":  "Ervison Plata",
    "AFINIA": "Ervison Plata",
}
PLANNER_DEFAULT = "Dinovi Sanchez"
SLACK_USER_IDS = {
    "Ervison Plata":  "U090B8YQMAM",
    "Dinovi Sanchez": "U06NVHEE9GD",
}
