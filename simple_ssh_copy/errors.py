class UnsupportedRemoteShellError(RuntimeError):
    """Raised when the remote SSH server does not provide a POSIX-like shell."""


class UnsupportedRemoteSystemError(RuntimeError):
    """Raised when the remote SSH server appears to run an unsupported OS."""

    def __init__(self, message: str, warning_printed: bool = False) -> None:
        super().__init__(message)
        self.warning_printed = warning_printed


class UnusableSSHConnectionError(RuntimeError):
    """Raised when SSH cannot carry even the minimum upload command size."""
