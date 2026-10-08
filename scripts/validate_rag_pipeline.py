"""Explicit focused offline validation using the existing socket/DNS guard."""
import os
import runpy
from pathlib import Path

os.environ['VALYQON_EMAIL_MODE'] = 'disabled'
os.environ['VALYQON_AI_FALLBACK_ENABLED'] = 'false'
runpy.run_path(str(Path(__file__).with_name('validate_ai_gateway.py')), run_name='__main__')
