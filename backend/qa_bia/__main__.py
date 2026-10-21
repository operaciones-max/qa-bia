import sys

from . import config
from .pipeline import main

if not config.ANTHROPIC_API_KEY:
    sys.exit("ERROR: falta ANTHROPIC_API_KEY (variable de entorno o backend/.env).")

main()
