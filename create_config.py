import os

groq_key  = os.environ.get('GROQ_API_KEY', '')
slack_url = os.environ.get('SLACK_WEBHOOK_URL', '')

config_text = (
    'METABASE_CSV_URL = "https://bia.metabaseapp.com/public/question/5ec265f5-182d-409d-bfbd-45303880da2d.csv"\n'
    f'GROQ_API_KEY = "{groq_key}"\n'
    'GROQ_MODEL = "llama-3.1-8b-instant"\n'
    f'SLACK_WEBHOOK_URL = "{slack_url}"\n'
    'TWILIO_ACCOUNT_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n'
    'TWILIO_AUTH_TOKEN = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"\n'
    'TWILIO_FROM_WHATSAPP = "whatsapp:+14155238886"\n'
    'TWILIO_TO_WHATSAPP = "whatsapp:+57TUNUMERODECELULAR"\n'
    'MODO_PRUEBA = False\n'
    'MODO_UNICO = True\n'
    'ACTAS_PRUEBA = 2\n'
    'FECHA_INICIO = "2026-04-27"\n'
    'PAUSA_GROQ_SEGUNDOS = 5\n'
    'INTERVALO_SEGUNDOS = 300\n'
    'ARCHIVO_PROCESADOS = "actas_procesadas.json"\n'
    'CARPETA_REPORTES = "reportes_qa"\n'
    'TIPOS_SERVICIO_VALIDOS = ["Instalaci\u00f3n", "Visita previa"]\n'
    'ESTADOS_ANALIZAR = ["CLOSURE_SUCCESSFUL", "CLOSURE_FAILED"]\n'
    'OR_PLANNERS = {"ESSA": "Ervison Plata", "EPM": "Ervison Plata", "AIRE": "Ervison Plata", "AIR-E": "Ervison Plata", "AFINIA": "Ervison Plata"}\n'
    'PLANNER_DEFAULT = "Dinovi Sanchez"\n'
)

with open('config.py', 'w') as f:
    f.write(config_text)

print("config.py creado OK")