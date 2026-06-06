import importlib
import io
import os
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

simple_ssh_client_module = types.ModuleType("simple_ssh_copy.SimpleSSHClient")
simple_ssh_client_module.SimpleSSHClient = object
sys.modules["simple_ssh_copy.SimpleSSHClient"] = simple_ssh_client_module

download_module = importlib.import_module("simple_ssh_copy.download")


class FakeSSHClient:
    def __init__(self, content: bytes):
        self.commands = []
        self.content = content
        self.sent_content = False

    def exec_cmd(self, command):
        self.commands.append(command)

        if command == "uname -s":
            return 0, b"Linux\n", b""

        if command == "uname -m 2>/dev/null || printf %s unknown":
            return 0, b"aarch64\n", b""

        if command.startswith("command dd "):
            if self.sent_content:
                return 0, b"", b""
            self.sent_content = True
            return 0, self.content, b""

        return 1, b"", f"unexpected command: {command}".encode()


class DownloadTests(unittest.TestCase):
    def test_download_reports_remote_architecture_before_transfer(self):
        content = b"downloaded data"
        ssh_client = FakeSSHClient(content)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, "file.bin")
            stderr = io.StringIO()

            with mock.patch.object(download_module.utils, "get_remote_file_size", return_value=0):
                with redirect_stderr(stderr), redirect_stdout(io.StringIO()):
                    download_module.download_files_with_ssh_client(
                        ssh_client,
                        [("/tmp/source.bin", local_path)],
                        block_size=1024)

            with open(local_path, "rb") as fpin:
                self.assertEqual(fpin.read(), content)

        self.assertEqual(stderr.getvalue(), "Remote architecture: aarch64\n")
        self.assertLess(
            ssh_client.commands.index("uname -m 2>/dev/null || printf %s unknown"),
            next(
                index
                for index, command in enumerate(ssh_client.commands)
                if command.startswith("command dd ")))
        self.assertLess(
            ssh_client.commands.index("uname -s"),
            ssh_client.commands.index("uname -m 2>/dev/null || printf %s unknown"))


if __name__ == "__main__":
    unittest.main()
