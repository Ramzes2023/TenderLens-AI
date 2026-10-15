"""Run explicit focused test files with email disabled and external sockets blocked.

Loopback is necessary for Windows asyncio socketpair construction and local API
tests. Provider calls are mocked; external DNS and TCP connections fail closed.
"""
import ipaddress
import os
import socket
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

os.environ['VALYQON_EMAIL_MODE'] = 'disabled'
if not sys.argv[1:] or any(not arg.startswith('tests/test_') or not arg.endswith('.py') for arg in sys.argv[1:]):
    raise SystemExit('Supply explicit focused tests/test_*.py files; no full-suite default.')

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
            raise AssertionError('External network forbidden in AI validation')
        return original(sock, address)
    return connect

original_resolve = socket.getaddrinfo
def resolve(host, *args, **kwargs):
    if not local(host):
        raise AssertionError('External DNS forbidden in AI validation')
    return original_resolve(host, *args, **kwargs)

with patch.object(socket.socket, 'connect', guarded_connect(socket.socket.connect)), \
        patch.object(socket.socket, 'connect_ex', guarded_connect(socket.socket.connect_ex)), \
        patch.object(socket, 'getaddrinfo', resolve):
    raise SystemExit(pytest.main(['-q', *sys.argv[1:]]))
