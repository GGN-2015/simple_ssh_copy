import importlib
import socket
import sys
import unittest

import paramiko

sys.modules.pop("simple_ssh_copy.SimpleSSHClient", None)

simple_ssh_client_module = importlib.import_module("simple_ssh_copy.SimpleSSHClient")

OPENSSH_CERT_SUFFIX = simple_ssh_client_module.OPENSSH_CERT_SUFFIX
SSH_RSA_HOST_KEY_ALGORITHM = simple_ssh_client_module.SSH_RSA_HOST_KEY_ALGORITHM
_transport_factory_with_all_supported_algorithms = (
    simple_ssh_client_module._transport_factory_with_all_supported_algorithms)


class SSHAlgorithmCompatibilityTests(unittest.TestCase):
    def _make_transport(self):
        client_socket, server_socket = socket.socketpair()
        transport = _transport_factory_with_all_supported_algorithms(client_socket)
        self.addCleanup(transport.close)
        self.addCleanup(client_socket.close)
        self.addCleanup(server_socket.close)
        return transport

    def _plain_key_algorithms(self, transport):
        return {
            algorithm
            for algorithm in transport._key_info
            if not algorithm.endswith(OPENSSH_CERT_SUFFIX)
        }

    def test_transport_allows_all_supported_negotiation_algorithms(self):
        transport = self._make_transport()
        security_options = transport.get_security_options()

        expected_kex = set(transport._kex_info)
        if not getattr(transport, "use_gss_kex", False):
            expected_kex -= set(getattr(transport, "_preferred_gsskex", ()) or ())

        self.assertTrue(expected_kex.issubset(set(security_options.kex)))
        self.assertTrue(set(transport._cipher_info).issubset(set(security_options.ciphers)))
        self.assertTrue(set(transport._mac_info).issubset(set(security_options.digests)))
        self.assertTrue(self._plain_key_algorithms(transport).issubset(
            set(security_options.key_types)))

    def test_transport_allows_all_supported_public_key_signature_algorithms(self):
        transport = self._make_transport()

        expected_pubkeys = self._plain_key_algorithms(transport)
        expected_pubkeys.update(
            algorithm
            for algorithm in paramiko.RSAKey.HASHES
            if not algorithm.endswith(OPENSSH_CERT_SUFFIX)
        )

        self.assertTrue(expected_pubkeys.issubset(set(transport.preferred_pubkeys)))

    def test_transport_restores_ssh_rsa_when_paramiko_can_use_it(self):
        transport = self._make_transport()

        self.assertIn(SSH_RSA_HOST_KEY_ALGORITHM, paramiko.RSAKey.HASHES)
        self.assertIn(SSH_RSA_HOST_KEY_ALGORITHM, transport._key_info)
        self.assertIn(
            SSH_RSA_HOST_KEY_ALGORITHM,
            transport.get_security_options().key_types)
        self.assertIn(SSH_RSA_HOST_KEY_ALGORITHM, transport.preferred_pubkeys)


if __name__ == "__main__":
    unittest.main()
