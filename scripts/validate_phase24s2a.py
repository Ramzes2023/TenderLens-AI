"""Run focused or full regression offline, without project dotenv files.

Loopback is allowed for Windows asyncio and multiprocessing; providers remain
mocked. Explicit temporary dotenv fixtures retain their original test behavior.
"""
import ipaddress
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Retain only OS/runtime settings, without reading inherited provider/database
# credential values. Tests supply their own synthetic application settings.
runtime_names = {
    'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
    'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA', 'LOCALAPPDATA',
    'PROGRAMDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'OS',
    'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'PYTHONPATH',
}
runtime_environment = {name: value for name in runtime_names
                       if (value := os.environ.get(name)) is not None}
os.environ.clear()
os.environ.update(runtime_environment)
import dotenv

original_dotenv = dotenv.load_dotenv
def safe_dotenv(dotenv_path=None, *args, **kwargs):
    if dotenv_path is None:
        return False
    path = Path(dotenv_path).resolve()
    if path.name.startswith('.env') and ROOT in path.parents:
        return False
    return original_dotenv(dotenv_path, *args, **kwargs)

dotenv.load_dotenv = safe_dotenv
os.environ['VALYQON_EMAIL_MODE'] = 'disabled'
os.environ['VALYQON_AI_FALLBACK_ENABLED'] = 'false'

def local(host):
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

def guarded_connect(original):
    def connect(sock, address):
        if not isinstance(address, tuple) or not local(address[0]):
            raise AssertionError('External network forbidden in offline stability validation')
        return original(sock, address)
    return connect

original_resolve = socket.getaddrinfo
def resolve(host, *args, **kwargs):
    if not local(host):
        raise AssertionError('External DNS forbidden in offline stability validation')
    return original_resolve(host, *args, **kwargs)

if __name__ == '__main__':
    import pytest
    with patch.object(socket.socket, 'connect', guarded_connect(socket.socket.connect)), \
            patch.object(socket.socket, 'connect_ex', guarded_connect(socket.socket.connect_ex)), \
            patch.object(socket, 'getaddrinfo', resolve):
        raise SystemExit(pytest.main(['-q', *(sys.argv[1:] or ['tests'])]))
