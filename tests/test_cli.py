import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

import paramiko

from simple_ssh_copy import __main__ as cli


class CLITests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
