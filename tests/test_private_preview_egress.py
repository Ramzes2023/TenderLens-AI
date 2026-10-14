"""Offline checks: no sockets opened and no permanent hooks in test process."""
import socket
import unittest
from unittest.mock import patch

from ops.private_preview.egress_guard import make_guard


class PreviewEgressTests(unittest.TestCase):
    def setUp(self):
        self.guard = make_guard({('172.30.0.2', 5432), ('172.30.0.3', 1025)})

    def test_only_service_endpoints_and_loopback_connections_allowed(self):
        for address in [('172.30.0.2', 5432), ('172.30.0.3', 1025),
                        ('127.0.0.1', 8000), ('::1', 8000, 0, 0)]:
            self.guard('socket.connect', (None, address))
        for address in [('172.30.0.2', 443), ('172.30.0.3', 8025),
                        ('198.51.100.1', 443), ('example.test', 443), '/tmp/socket']:
            with self.assertRaises(PermissionError):
                self.guard('socket.connect', (None, address))

    def test_external_dns_and_udp_denied(self):
        for host in ('db', 'mailpit', 'localhost', '127.0.0.1', '::1', None):
            self.guard('socket.getaddrinfo', (host, 443))
        for host in ('example.test', '198.51.100.1'):
            with self.assertRaises(PermissionError):
                self.guard('socket.getaddrinfo', (host, 443))
        with self.assertRaises(PermissionError):
            self.guard('socket.sendto', (None, b'test', ('198.51.100.1', 53)))

    def test_install_resolves_services_before_hook_and_is_idempotent(self):
        from ops.private_preview import egress_guard
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('172.30.0.2', 5432))]
        with patch.object(egress_guard, '_installed', False), \
                patch.object(egress_guard.socket, 'getaddrinfo', return_value=records) as resolve, \
                patch.object(egress_guard.sys, 'addaudithook') as add:
            egress_guard.install()
            egress_guard.install()
            self.assertEqual(resolve.call_count, 2)
            add.assert_called_once()

    def test_missing_service_resolution_fails_startup(self):
        from ops.private_preview import egress_guard
        with patch.object(egress_guard, '_installed', False), \
                patch.object(egress_guard.socket, 'getaddrinfo', side_effect=socket.gaierror), \
                patch.object(egress_guard.sys, 'addaudithook') as add:
            with self.assertRaises(socket.gaierror):
                egress_guard.install()
            add.assert_not_called()
            self.assertFalse(egress_guard._installed)

