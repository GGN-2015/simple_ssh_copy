class UnsupportedRemoteShellError(RuntimeError):
    """Raised when the remote SSH server does not provide a POSIX-like shell."""
