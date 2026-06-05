class UnsupportedRemoteShellError(RuntimeError):
    """Raised when the remote SSH server does not provide a POSIX-like shell."""


class UnusableSSHConnectionError(RuntimeError):
    """Raised when SSH cannot carry even the minimum upload command size."""
