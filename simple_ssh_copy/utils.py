import os
import sys

try:
    from .errors import UnsupportedRemoteSystemError
except:
    from errors import UnsupportedRemoteSystemError

DIRNOW = os.path.dirname(os.path.abspath(__file__))
KEY_FOLDER = os.path.join(DIRNOW, "keys")

if not os.path.isdir(KEY_FOLDER):
    os.makedirs(KEY_FOLDER, exist_ok=True)

REMOTE_SYSTEM_CHECK_ATTR = "_simple_ssh_copy_remote_system_name"
REMOTE_SYSTEM_UNAME_COMMAND = "uname -s"
REMOTE_SYSTEM_WINDOWS_COMMAND = "cmd.exe /c ver"
WINDOWS_REMOTE_WARNING = (
    "Warning: Windows remote systems are not supported. "
    "simple_ssh_copy only supports POSIX-like remote systems. "
    "Transfer aborted."
)
ANSI_YELLOW = "\033[33m"
ANSI_RESET = "\033[0m"


def _first_non_empty_line(data: bytes) -> str:
    for line in data.decode(errors="replace").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def format_warning(message: str) -> str:
    return f"{ANSI_YELLOW}{message}{ANSI_RESET}"


def is_windows_remote_system(system_name: str) -> bool:
    normalized = system_name.strip().lower()
    return any(
        marker in normalized
        for marker in ("windows", "cygwin", "mingw", "msys")
    )


def get_remote_system_name(ssh_client) -> str:
    code, out, _ = ssh_client.exec_cmd(REMOTE_SYSTEM_UNAME_COMMAND)
    system_name = _first_non_empty_line(out)
    if code == 0 and system_name:
        return system_name

    code, out, err = ssh_client.exec_cmd(REMOTE_SYSTEM_WINDOWS_COMMAND)
    system_name = _first_non_empty_line(out) or _first_non_empty_line(err)
    if code == 0 and system_name:
        return system_name

    return "unknown"


def ensure_remote_is_not_windows(ssh_client, stream=None) -> str:
    system_name = getattr(ssh_client, REMOTE_SYSTEM_CHECK_ATTR, None)
    if system_name is None:
        system_name = get_remote_system_name(ssh_client)
        setattr(ssh_client, REMOTE_SYSTEM_CHECK_ATTR, system_name)

    if not is_windows_remote_system(system_name):
        return system_name

    if stream is None:
        stream = sys.stderr

    print(format_warning(WINDOWS_REMOTE_WARNING), file=stream)
    raise UnsupportedRemoteSystemError(
        WINDOWS_REMOTE_WARNING,
        warning_printed=True)


def get_remote_file_size(ssh_client, remote_path: str) -> int:
    try:
        from .SimpleSSHClient import SimpleSSHClient
    except:
        from SimpleSSHClient import SimpleSSHClient

    assert isinstance(ssh_client, SimpleSSHClient)

    cmd = f"stat -c %s '{remote_path}' 2>/dev/null || echo 0"
    _, out, _ = ssh_client.exec_cmd(cmd)
    try:
        return int(out.strip())
    except:
        return 0


def get_remote_architecture(ssh_client) -> str:
    cmd = "uname -m 2>/dev/null || printf %s unknown"
    code, out, _ = ssh_client.exec_cmd(cmd)
    if code != 0:
        return "unknown"

    lines = out.decode(errors="replace").strip().splitlines()
    if not lines:
        return "unknown"

    return lines[0] or "unknown"


def report_remote_architecture(ssh_client, stream=None) -> str:
    if stream is None:
        stream = sys.stderr

    architecture = get_remote_architecture(ssh_client)
    print(f"Remote architecture: {architecture}", file=stream)
    return architecture
