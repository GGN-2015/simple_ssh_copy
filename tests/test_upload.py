import base64
import os
import shlex
import sys
import tempfile
import types
import unittest

simple_ssh_client_module = types.ModuleType("simple_ssh_copy.SimpleSSHClient")
simple_ssh_client_module.SimpleSSHClient = object
sys.modules["simple_ssh_copy.SimpleSSHClient"] = simple_ssh_client_module

from simple_ssh_copy.upload import upload_files_with_ssh_client
from simple_ssh_copy.errors import UnsupportedRemoteShellError


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
        self.assertTrue(any(command.startswith("printf %s ") for command in ssh_client.commands))
        self.assertTrue(any(
            command.startswith("command base64 -d ")
            and command.endswith(" > '/tmp/target file.bin'")
            for command in ssh_client.commands))

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

        self.assertEqual(ssh_client.commands, ["printf %s simple_ssh_copy_posix_shell_ok"])

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


if __name__ == "__main__":
    unittest.main()
