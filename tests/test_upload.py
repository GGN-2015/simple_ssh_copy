import base64
import importlib
import io
import os
import shlex
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from unittest import mock

simple_ssh_client_module = types.ModuleType("simple_ssh_copy.SimpleSSHClient")
simple_ssh_client_module.SimpleSSHClient = object
sys.modules["simple_ssh_copy.SimpleSSHClient"] = simple_ssh_client_module

from simple_ssh_copy.upload import upload_files_with_ssh_client
upload_module = importlib.import_module("simple_ssh_copy.upload")
from simple_ssh_copy.errors import (
    UnsupportedRemoteShellError,
    UnsupportedRemoteSystemError,
    UnusableSSHConnectionError,
)


class FakeSSHClient:
    def __init__(self):
        self.commands = []
        self.remote_files = {}
        self.decoded_files = {}
        self.interrupt_after_appends = None
        self.append_count = 0

    def exec_cmd(self, command):
        self.commands.append(command)

        if command == "printf %s simple_ssh_copy_posix_shell_ok":
            return 0, b"simple_ssh_copy_posix_shell_ok", b""

        if command == "uname -s":
            return 0, b"Linux\n", b""

        if command == "uname -m 2>/dev/null || printf %s unknown":
            return 0, b"x86_64\n", b""

        if command == "printf '' | command base64 -d >/dev/null":
            return 0, b"", b""

        if command.startswith("mkdir -p "):
            return 0, b"", b""

        if command.startswith(": > "):
            path = shlex.split(command[4:])[0]
            self.remote_files[path] = ""
            return 0, b"", b""

        if command.startswith("printf %s ") and " >> " in command:
            self.append_count += 1
            if (
                    self.interrupt_after_appends is not None
                    and self.append_count > self.interrupt_after_appends):
                raise KeyboardInterrupt
            payload_part, path_part = command[len("printf %s "):].split(" >> ", 1)
            payload = shlex.split(payload_part)[0]
            path = shlex.split(path_part)[0]
            self.remote_files[path] = self.remote_files.get(path, "") + payload
            return 0, b"", b""

        if command.startswith("command base64 -d ") and " > " in command:
            source_part, target_part = command[len("command base64 -d "):].split(" > ", 1)
            source = shlex.split(source_part)[0]
            target = shlex.split(target_part)[0]
            self.decoded_files[target] = base64.b64decode(self.remote_files[source])
            return 0, b"", b""

        if command.startswith("rm -f "):
            path = shlex.split(command[len("rm -f "):])[0]
            self.remote_files.pop(path, None)
            return 0, b"", b""

        return 1, b"", f"unexpected command: {command}".encode()


class ProbeContext:
    def __init__(
            self,
            attempts,
            failing_block_sizes,
            too_large_block_sizes=None,
            eof_block_sizes=None):
        self.attempts = attempts
        self.failing_block_sizes = failing_block_sizes
        self.too_large_block_sizes = too_large_block_sizes or set()
        self.eof_block_sizes = eof_block_sizes or set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def exec_cmd(self, command):
        if command == "uname -s":
            return 0, b"Linux\n", b""

        if command == "printf %s simple_ssh_copy_posix_shell_ok":
            return 0, b"simple_ssh_copy_posix_shell_ok", b""

        self.attempts.append(len(command.encode("utf-8")))
        if len(command.encode("utf-8")) in self.failing_block_sizes:
            raise ConnectionResetError(10054, "connection reset")
        if len(command.encode("utf-8")) in self.too_large_block_sizes:
            return 126, b"", b"/bin/bash: Argument list too long"
        if len(command.encode("utf-8")) in self.eof_block_sizes:
            raise EOFError()
        return 0, b"", b""


class UploadTests(unittest.TestCase):
    def test_large_upload_sends_base64_through_bounded_commands(self):
        ssh_client = FakeSSHClient()
        content = bytes(range(256)) * 80

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(content)
            local_path = fpin.name

        try:
            upload_files_with_ssh_client(
                ssh_client,
                [(local_path, "/tmp/target file.bin")],
                block_siz=1024)
        finally:
            os.unlink(local_path)

        self.assertEqual(ssh_client.decoded_files["/tmp/target file.bin"], content)
        self.assertEqual(ssh_client.remote_files, {})
        self.assertTrue(all(len(command.encode("utf-8")) <= 1024 for command in ssh_client.commands))
        self.assertIn("mkdir -p /tmp", ssh_client.commands)
        self.assertIn("uname -m 2>/dev/null || printf %s unknown", ssh_client.commands)
        self.assertTrue(any(command.startswith("printf %s ") for command in ssh_client.commands))
        self.assertTrue(any(
            command.startswith("command base64 -d ")
            and command.endswith(" > '/tmp/target file.bin'")
            for command in ssh_client.commands))

    def test_upload_reports_remote_architecture_before_transfer(self):
        ssh_client = FakeSSHClient()

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            local_path = fpin.name

        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                upload_files_with_ssh_client(
                    ssh_client,
                    [(local_path, "/tmp/target.bin")],
                    block_siz=1024)
        finally:
            os.unlink(local_path)

        self.assertEqual(stderr.getvalue(), "Remote architecture: x86_64\n")
        self.assertLess(
            ssh_client.commands.index("uname -m 2>/dev/null || printf %s unknown"),
            ssh_client.commands.index("printf '' | command base64 -d >/dev/null"))

    def test_upload_warns_and_aborts_on_windows_remote(self):
        ssh_client = FakeSSHClient()

        def windows_exec_cmd(command):
            ssh_client.commands.append(command)
            if command == "uname -s":
                return 1, b"", b"'uname' is not recognized"
            if command == "cmd.exe /c ver":
                return 0, b"Microsoft Windows [Version 10.0.19045.0]\r\n", b""
            return 0, b"", b""

        ssh_client.exec_cmd = windows_exec_cmd

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            local_path = fpin.name

        try:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                with self.assertRaises(UnsupportedRemoteSystemError):
                    upload_files_with_ssh_client(
                        ssh_client,
                        [(local_path, "/tmp/target.bin")],
                        block_siz=1024)
        finally:
            os.unlink(local_path)

        self.assertEqual(
            stderr.getvalue(),
            "\033[33mWarning: Windows remote systems are not supported. "
            "simple_ssh_copy only supports POSIX-like remote systems. "
            "Transfer aborted.\033[0m\n")
        self.assertEqual(ssh_client.commands, ["uname -s", "cmd.exe /c ver"])

    def test_upload_uses_4096b_default_command_size(self):
        ssh_client = FakeSSHClient()
        content = b"x" * 10000

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(content)
            local_path = fpin.name

        try:
            upload_files_with_ssh_client(
                ssh_client,
                [(local_path, "/tmp/target.bin")])
        finally:
            os.unlink(local_path)

        self.assertEqual(ssh_client.decoded_files["/tmp/target.bin"], content)
        self.assertTrue(all(len(command.encode("utf-8")) <= 4096 for command in ssh_client.commands))
        self.assertTrue(any(len(command.encode("utf-8")) == 4096 for command in ssh_client.commands))

    def test_upload_rejects_command_size_too_small_for_overhead(self):
        ssh_client = FakeSSHClient()

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(b"x")
            local_path = fpin.name

        try:
            with self.assertRaisesRegex(RuntimeError, "upload command exceeded block_siz=8"):
                upload_files_with_ssh_client(
                    ssh_client,
                    [(local_path, "/tmp/target.bin")],
                    block_siz=8)
        finally:
            os.unlink(local_path)

    def test_upload_rejects_non_posix_remote_shell(self):
        ssh_client = FakeSSHClient()

        def non_posix_exec_cmd(command):
            ssh_client.commands.append(command)
            if command == "uname -s":
                return 0, b"Linux\n", b""
            if command == "printf %s simple_ssh_copy_posix_shell_ok":
                return 1, b"", b"'printf' is not recognized"
            return 0, b"", b""

        ssh_client.exec_cmd = non_posix_exec_cmd

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(b"x")
            local_path = fpin.name

        try:
            with self.assertRaisesRegex(UnsupportedRemoteShellError, "POSIX-like remote shell is required"):
                upload_files_with_ssh_client(
                    ssh_client,
                    [(local_path, "/tmp/target.bin")])
        finally:
            os.unlink(local_path)

        self.assertEqual(
            ssh_client.commands,
            ["uname -s", "printf %s simple_ssh_copy_posix_shell_ok"])

    def test_keyboard_interrupt_removes_remote_temp_file(self):
        ssh_client = FakeSSHClient()
        ssh_client.interrupt_after_appends = 1
        content = b"x" * 10000

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(content)
            local_path = fpin.name

        try:
            with self.assertRaises(KeyboardInterrupt):
                upload_files_with_ssh_client(
                    ssh_client,
                    [(local_path, "/tmp/target.bin")],
                    block_siz=4096)
        finally:
            os.unlink(local_path)

        self.assertEqual(ssh_client.remote_files, {})
        self.assertNotIn("/tmp/target.bin", ssh_client.decoded_files)
        self.assertTrue(any(command.startswith("rm -f /tmp/.ssc-") for command in ssh_client.commands))

    def test_upload_halves_block_size_after_connection_reset_probe(self):
        attempts = []
        used_block_sizes = []

        def fake_simple_ssh_client(*args, **kwargs):
            return ProbeContext(attempts, {4096, 2048})

        def fake_upload_files_with_ssh_client(ssh_client, files, block_siz):
            used_block_sizes.append(block_siz)

        with mock.patch.object(upload_module, "SimpleSSHClient", side_effect=fake_simple_ssh_client):
            with mock.patch.object(
                    upload_module,
                    "upload_files_with_ssh_client",
                    side_effect=fake_upload_files_with_ssh_client):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    upload_module.upload(
                        hostname="example.com",
                        username="ubuntu",
                        password="password",
                        files=[("local.txt", "/tmp/remote.txt")],
                        block_siz=4096)

        self.assertEqual(attempts, [4096, 2048, 1024])
        self.assertEqual(used_block_sizes, [1024])
        self.assertEqual(
            stderr.getvalue(),
            "Warning: using upload block_siz=1024 after SSH command-size probe; "
            "requested block_siz=4096.\n")

    def test_upload_does_not_report_block_size_when_probe_keeps_requested_size(self):
        attempts = []

        def fake_simple_ssh_client(*args, **kwargs):
            return ProbeContext(attempts, set())

        def fake_upload_files_with_ssh_client(ssh_client, files, block_siz):
            self.assertEqual(block_siz, 4096)

        with mock.patch.object(upload_module, "SimpleSSHClient", side_effect=fake_simple_ssh_client):
            with mock.patch.object(
                    upload_module,
                    "upload_files_with_ssh_client",
                    side_effect=fake_upload_files_with_ssh_client):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    upload_module.upload(
                        hostname="example.com",
                        username="ubuntu",
                        password="password",
                        files=[("local.txt", "/tmp/remote.txt")],
                        block_siz=4096)

        self.assertEqual(attempts, [4096])
        self.assertEqual(stderr.getvalue(), "")

    def test_upload_halves_block_size_after_argument_list_too_long_probe(self):
        attempts = []
        used_block_sizes = []

        def fake_simple_ssh_client(*args, **kwargs):
            return ProbeContext(attempts, set(), too_large_block_sizes={4096, 2048})

        def fake_upload_files_with_ssh_client(ssh_client, files, block_siz):
            used_block_sizes.append(block_siz)

        with mock.patch.object(upload_module, "SimpleSSHClient", side_effect=fake_simple_ssh_client):
            with mock.patch.object(
                    upload_module,
                    "upload_files_with_ssh_client",
                    side_effect=fake_upload_files_with_ssh_client):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    upload_module.upload(
                        hostname="example.com",
                        username="ubuntu",
                        password="password",
                        files=[("local.txt", "/tmp/remote.txt")],
                        block_siz=4096)

        self.assertEqual(attempts, [4096, 2048, 1024])
        self.assertEqual(used_block_sizes, [1024])
        self.assertEqual(
            stderr.getvalue(),
            "Warning: using upload block_siz=1024 after SSH command-size probe; "
            "requested block_siz=4096.\n")

    def test_upload_halves_block_size_after_eof_probe(self):
        attempts = []
        used_block_sizes = []

        def fake_simple_ssh_client(*args, **kwargs):
            return ProbeContext(attempts, set(), eof_block_sizes={4096, 2048})

        def fake_upload_files_with_ssh_client(ssh_client, files, block_siz):
            used_block_sizes.append(block_siz)

        with mock.patch.object(upload_module, "SimpleSSHClient", side_effect=fake_simple_ssh_client):
            with mock.patch.object(
                    upload_module,
                    "upload_files_with_ssh_client",
                    side_effect=fake_upload_files_with_ssh_client):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    upload_module.upload(
                        hostname="example.com",
                        username="ubuntu",
                        password="password",
                        files=[("local.txt", "/tmp/remote.txt")],
                        block_siz=4096)

        self.assertEqual(attempts, [4096, 2048, 1024])
        self.assertEqual(used_block_sizes, [1024])
        self.assertEqual(
            stderr.getvalue(),
            "Warning: using upload block_siz=1024 after SSH command-size probe; "
            "requested block_siz=4096.\n")

    def test_upload_reports_unusable_connection_below_minimum_block_size(self):
        attempts = []

        def fake_simple_ssh_client(*args, **kwargs):
            return ProbeContext(attempts, {4096, 2048, 1024, 512, 256, 128, 64})

        with mock.patch.object(upload_module, "SimpleSSHClient", side_effect=fake_simple_ssh_client):
            with self.assertRaisesRegex(
                    UnusableSSHConnectionError,
                    "SSH connection cannot carry upload commands smaller than 64 bytes"):
                upload_module.upload(
                    hostname="example.com",
                    username="ubuntu",
                    password="password",
                    files=[("local.txt", "/tmp/remote.txt")],
                    block_siz=4096)

        self.assertEqual(attempts, [4096, 2048, 1024, 512, 256, 128, 64])


if __name__ == "__main__":
    unittest.main()
