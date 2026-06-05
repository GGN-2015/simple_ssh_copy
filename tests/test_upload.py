import os
import sys
import tempfile
import types
import unittest

simple_ssh_client_module = types.ModuleType("simple_ssh_copy.SimpleSSHClient")
simple_ssh_client_module.SimpleSSHClient = object
sys.modules["simple_ssh_copy.SimpleSSHClient"] = simple_ssh_client_module

from simple_ssh_copy.upload import upload_files_with_ssh_client


class FakeChannel:
    def __init__(self):
        self.data = bytearray()
        self.send_sizes = []
        self.write_closed = False

    def sendall(self, data):
        self.send_sizes.append(len(data))
        self.data.extend(data)

    def shutdown_write(self):
        self.write_closed = True

    def recv_exit_status(self):
        return 0


class FakeStdin:
    def __init__(self, channel):
        self.channel = channel


class FakeStream:
    def __init__(self, channel, data=b""):
        self.channel = channel
        self._data = data

    def read(self):
        return self._data


class FakeParamikoClient:
    def __init__(self):
        self.commands = []
        self.channel = FakeChannel()

    def exec_command(self, command):
        self.commands.append(command)
        return (
            FakeStdin(self.channel),
            FakeStream(self.channel),
            FakeStream(self.channel),
        )


class FakeSSHClient:
    def __init__(self):
        self.mkdir_commands = []
        self.ssh_client = FakeParamikoClient()

    def exec_cmd(self, command):
        self.mkdir_commands.append(command)
        return 0, b"", b""


class UploadTests(unittest.TestCase):
    def test_large_upload_streams_file_content_over_stdin(self):
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

        self.assertEqual(ssh_client.mkdir_commands, ["mkdir -p /tmp"])
        self.assertEqual(
            ssh_client.ssh_client.commands,
            ["command cat > '/tmp/target file.bin'"])
        self.assertEqual(bytes(ssh_client.ssh_client.channel.data), content)
        self.assertTrue(ssh_client.ssh_client.channel.write_closed)

    def test_upload_uses_1kb_default_block_size(self):
        ssh_client = FakeSSHClient()
        content = b"x" * 2500

        with tempfile.NamedTemporaryFile(delete=False) as fpin:
            fpin.write(content)
            local_path = fpin.name

        try:
            upload_files_with_ssh_client(
                ssh_client,
                [(local_path, "/tmp/target.bin")])
        finally:
            os.unlink(local_path)

        self.assertEqual(ssh_client.ssh_client.channel.send_sizes, [1024, 1024, 452])


if __name__ == "__main__":
    unittest.main()
