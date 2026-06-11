import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

import paramiko

from simple_ssh_copy import __main__ as cli
from simple_ssh_copy.errors import (
    UnsupportedRemoteShellError,
    UnsupportedRemoteSystemError,
    UnusableSSHConnectionError,
)


class CLITests(unittest.TestCase):
    def test_upload_passes_block_size_when_requested(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "--block-size",
                    "2048",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(cli, "upload") as upload_mock:
                    code = cli.main()

        self.assertEqual(code, 0)
        upload_mock.assert_called_once()
        self.assertEqual(upload_mock.call_args.kwargs["block_siz"], 2048)

    def test_download_passes_block_size_when_requested(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "--block-size",
                    "65536",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                    "test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(cli, "download") as download_mock:
                    code = cli.main()

        self.assertEqual(code, 0)
        download_mock.assert_called_once()
        self.assertEqual(download_mock.call_args.kwargs["block_size"], 65536)

    def test_upload_omits_block_size_when_not_requested(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(cli, "upload") as upload_mock:
                    code = cli.main()

        self.assertEqual(code, 0)
        upload_mock.assert_called_once()
        self.assertNotIn("block_siz", upload_mock.call_args.kwargs)

    def test_authentication_error_is_reported_without_traceback(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="bad-password"):
                with mock.patch.object(
                        cli,
                        "upload",
                        side_effect=paramiko.AuthenticationException("Authentication failed.")):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(output, "Error: Authentication failed.\n")
        self.assertNotIn("Traceback", output)

    def test_unsupported_remote_shell_is_reported_without_traceback(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "neko@127.0.0.1:/tmp/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value=""):
                with mock.patch.object(
                        cli,
                        "upload",
                        side_effect=UnsupportedRemoteShellError(
                            "POSIX-like remote shell is required.")):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(output, "Error: POSIX-like remote shell is required.\n")
        self.assertNotIn("Traceback", output)

    def test_keyboard_interrupt_is_reported_without_traceback(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(cli, "upload", side_effect=KeyboardInterrupt):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 130)
        self.assertEqual(output, "Error: Interrupted by user.\n")
        self.assertNotIn("Traceback", output)

    def test_unsupported_remote_system_warning_is_not_duplicated(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(
                        cli,
                        "upload",
                        side_effect=UnsupportedRemoteSystemError(
                            "Warning: Windows remote systems are not supported. "
                            "simple_ssh_copy only supports POSIX-like remote systems. "
                            "Transfer aborted.",
                            warning_printed=True)):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(output, "")
        self.assertNotIn("Traceback", output)

    def test_unsupported_remote_system_warning_is_yellow(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(
                        cli,
                        "upload",
                        side_effect=UnsupportedRemoteSystemError(
                            "Warning: Windows remote systems are not supported. "
                            "simple_ssh_copy only supports POSIX-like remote systems. "
                            "Transfer aborted.")):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(
            output,
            "\033[33mWarning: Windows remote systems are not supported. "
            "simple_ssh_copy only supports POSIX-like remote systems. "
            "Transfer aborted.\033[0m\n")
        self.assertNotIn("Traceback", output)

    def test_unusable_ssh_connection_is_reported_without_traceback(self):
        with mock.patch.object(
                sys,
                "argv",
                [
                    "python -m simple_ssh_copy",
                    "test-file.txt",
                    "ubuntu@example.com:/home/ubuntu/test-file.txt",
                ]):
            with mock.patch.object(cli.getpass, "getpass", return_value="password"):
                with mock.patch.object(
                        cli,
                        "upload",
                        side_effect=UnusableSSHConnectionError(
                            "SSH connection cannot carry upload commands smaller than 64 bytes")):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        code = cli.main()

        output = stderr.getvalue()
        self.assertEqual(code, 1)
        self.assertEqual(
            output,
            "Error: SSH connection cannot carry upload commands smaller than 64 bytes\n")
        self.assertNotIn("Traceback", output)


if __name__ == "__main__":
    unittest.main()
