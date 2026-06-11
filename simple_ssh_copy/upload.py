from tqdm import tqdm
import base64
import os
import posixpath
import shlex
import socket
import sys
import uuid

try:
    from .SimpleSSHClient import SimpleSSHClient
    from . import utils
    from .errors import UnsupportedRemoteShellError, UnusableSSHConnectionError
except:
    from SimpleSSHClient import SimpleSSHClient
    import utils
    from errors import UnsupportedRemoteShellError, UnusableSSHConnectionError


def get_file_total_size(fpin) -> int:
    """Get total file size without changing current file pointer position"""
    old_pos = fpin.tell()
    fpin.seek(0, os.SEEK_END)
    total = fpin.tell()
    fpin.seek(old_pos, os.SEEK_SET)
    return total


def _check_remote_command(ssh_client: SimpleSSHClient, command: str) -> None:
    code, _, error = ssh_client.exec_cmd(command)
    if code != 0:
        message = error.decode(errors="replace").strip()
        raise RuntimeError(message or f"remote command failed with exit code {code}: {command}")


def _check_posix_remote_shell(ssh_client: SimpleSSHClient) -> None:
    command = "printf %s simple_ssh_copy_posix_shell_ok"
    code, output, _ = ssh_client.exec_cmd(command)
    if code != 0 or output.strip() != b"simple_ssh_copy_posix_shell_ok":
        raise UnsupportedRemoteShellError("POSIX-like remote shell is required.")


def _check_remote_base64_decoder(ssh_client: SimpleSSHClient) -> None:
    command = "printf '' | command base64 -d >/dev/null"
    code, _, error = ssh_client.exec_cmd(command)
    if code != 0:
        message = error.decode(errors="replace").strip()
        if message:
            raise RuntimeError(f"remote base64 decoder is required for upload: {message}")
        raise RuntimeError("remote base64 decoder is required for upload")


def _run_remote_command(ssh_client: SimpleSSHClient, command: str) -> tuple[bytes, bytes]:
    code, output, error = ssh_client.exec_cmd(command)
    if code != 0:
        message = error.decode(errors="replace").strip()
        if output:
            output_text = output.decode(errors="replace").strip()
            message = f"{message}\n{output_text}".strip()
        raise RuntimeError(message or f"remote command failed with exit code {code}: {command}")

    return output, error


def _run_bounded_remote_command(
        ssh_client: SimpleSSHClient,
        command: str,
        block_siz: int) -> tuple[bytes, bytes]:
    command_len = len(command.encode("utf-8"))
    if command_len > block_siz:
        raise RuntimeError(f"upload command exceeded block_siz={block_siz}: {command_len}")
    return _run_remote_command(ssh_client, command)


def _is_connection_reset_error(exc: BaseException) -> bool:
    if isinstance(exc, EOFError):
        return True
    if isinstance(exc, ConnectionResetError):
        return True
    if isinstance(exc, socket.error) and getattr(exc, "errno", None) in (10054, 104):
        return True
    return any(_is_connection_reset_error(arg) for arg in getattr(exc, "args", ()) if isinstance(arg, BaseException))


def _is_upload_command_too_large_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "argument list too long" in message


def _make_block_size_probe_command(block_siz: int) -> str:
    prefix = "true # "
    filler_len = block_siz - len(prefix.encode("utf-8"))
    if filler_len < 0:
        raise ValueError("block_siz is too small for upload command overhead")
    return prefix + ("x" * filler_len)


def probe_upload_block_size(
        hostname: str,
        username: str,
        password: str | None,
        block_siz: int,
        port: int = 22,
        timeout: float = 15,
        allow_ssh_rsa_host_key: bool = True,
        allow_agent: bool | None = None,
        look_for_keys: bool | None = None,
        key_filename: str | list[str] | None = None,
        minimum_block_siz: int = 64) -> int:
    block_siz = max(1, block_siz)
    while block_siz >= minimum_block_siz:
        try:
            with SimpleSSHClient(
                    hostname,
                    username,
                    password,
                    port,
                    timeout,
                    allow_ssh_rsa_host_key,
                    allow_agent,
                    look_for_keys,
                    key_filename) as ssh_client:
                utils.ensure_remote_is_not_windows(ssh_client)
                _check_posix_remote_shell(ssh_client)
                _run_bounded_remote_command(
                    ssh_client,
                    _make_block_size_probe_command(block_siz),
                    block_siz)
            return block_siz
        except Exception as exc:
            if not (
                    _is_connection_reset_error(exc)
                    or _is_upload_command_too_large_error(exc)):
                raise
            block_siz //= 2

    raise UnusableSSHConnectionError(
        f"SSH connection cannot carry upload commands smaller than {minimum_block_siz} bytes")


def _report_adjusted_block_size(requested_block_siz: int, actual_block_siz: int) -> None:
    if actual_block_siz != requested_block_siz:
        print(
            f"Warning: using upload block_siz={actual_block_siz} "
            f"after SSH command-size probe; requested block_siz={requested_block_siz}.",
            file=sys.stderr)


def _cleanup_remote_temp_file(
        ssh_client: SimpleSSHClient,
        remote_tmp_path: str,
        block_siz: int,
        raise_on_failure: bool) -> None:
    quoted_tmp_path = shlex.quote(remote_tmp_path)
    try:
        _run_bounded_remote_command(ssh_client, f"rm -f {quoted_tmp_path}", block_siz)
    except Exception:
        if raise_on_failure:
            raise


def _max_base64_payload_length(command_prefix: str, command_suffix: str, block_siz: int) -> int:
    overhead = len(command_prefix.encode("utf-8")) + len(command_suffix.encode("utf-8"))
    available = block_siz - overhead
    if available < 4:
        raise ValueError("block_siz is too small for upload command overhead")
    return available - (available % 4)


def _append_base64_to_remote_file(
        ssh_client: SimpleSSHClient,
        remote_tmp_path: str,
        encoded_data: bytes,
        block_siz: int) -> None:
    quoted_tmp_path = shlex.quote(remote_tmp_path)
    command_prefix = "printf %s "
    command_suffix = f" >> {quoted_tmp_path}"
    max_payload_len = _max_base64_payload_length(command_prefix, command_suffix, block_siz)
    encoded_text = encoded_data.decode("ascii")

    for offset in range(0, len(encoded_text), max_payload_len):
        payload = encoded_text[offset:offset + max_payload_len]
        command = f"{command_prefix}{shlex.quote(payload)}{command_suffix}"
        _run_bounded_remote_command(ssh_client, command, block_siz)


def _write_base64_temp_file(
        ssh_client: SimpleSSHClient,
        fpin,
        remote_tmp_path: str,
        block_siz: int,
        pbar) -> None:
    pending = b""

    while True:
        data_buf = fpin.read(block_siz)
        if not data_buf:
            break

        data_buf = pending + data_buf
        encodable_len = len(data_buf) - (len(data_buf) % 3)

        if encodable_len:
            raw_chunk = data_buf[:encodable_len]
            _append_base64_to_remote_file(
                ssh_client,
                remote_tmp_path,
                base64.b64encode(raw_chunk),
                block_siz)
            if pbar is not None:
                pbar.update(len(raw_chunk))

        pending = data_buf[encodable_len:]

    if pending:
        _append_base64_to_remote_file(
            ssh_client,
            remote_tmp_path,
            base64.b64encode(pending),
            block_siz)
        if pbar is not None:
            pbar.update(len(pending))


def _make_remote_tmp_path(remote_path: str) -> str:
    remote_dir = posixpath.dirname(remote_path) or "."
    token = uuid.uuid4().hex
    return posixpath.join(remote_dir, f".ssc-{token}.b64")


def _upload_file_with_commands(
        ssh_client: SimpleSSHClient,
        local_path: str,
        remote_path: str,
        block_siz: int) -> None:
    remote_tmp_path = _make_remote_tmp_path(remote_path)
    quoted_tmp_path = shlex.quote(remote_tmp_path)
    quoted_remote_path = shlex.quote(remote_path)

    with open(local_path, "rb") as fpin:
        total = get_file_total_size(fpin)

        pbar = None
        if total > 0:
            pbar = tqdm(total=total, unit="B", unit_scale=True, desc=f"{local_path}")
        else:
            print(f"{local_path}: empty file.")

        completed = False
        try:
            _run_bounded_remote_command(ssh_client, f": > {quoted_tmp_path}", block_siz)
            _write_base64_temp_file(ssh_client, fpin, remote_tmp_path, block_siz, pbar)
            _run_bounded_remote_command(
                ssh_client,
                f"command base64 -d {quoted_tmp_path} > {quoted_remote_path}",
                block_siz)
            completed = True
        finally:
            if pbar is not None:
                pbar.close()
            _cleanup_remote_temp_file(
                ssh_client,
                remote_tmp_path,
                block_siz,
                raise_on_failure=completed)


def upload_files_with_ssh_client(ssh_client: SimpleSSHClient, files: list[tuple[str, str]], block_siz: int = 4096):
    block_siz = max(1, block_siz)
    if files:
        utils.ensure_remote_is_not_windows(ssh_client)
        _check_posix_remote_shell(ssh_client)
        utils.report_remote_architecture(ssh_client)
        _check_remote_base64_decoder(ssh_client)

    for local_path, remote_path in files:
        aim_dir = posixpath.dirname(remote_path)
        if aim_dir:
            _check_remote_command(ssh_client, f"mkdir -p {shlex.quote(aim_dir)}")

        _upload_file_with_commands(
            ssh_client,
            local_path,
            remote_path,
            block_siz)


def upload(
        hostname: str,
        username: str,
        password: str | None,
        files: list[tuple[str, str]],
        block_siz: int = 4096,
        port: int = 22,
        timeout: float = 15,
        allow_ssh_rsa_host_key: bool = True,
        allow_agent: bool | None = None,
        look_for_keys: bool | None = None,
        key_filename: str | list[str] | None = None):
    
    requested_block_siz = max(1, block_siz)
    block_siz = probe_upload_block_size(
        hostname,
        username,
        password,
        requested_block_siz,
        port,
        timeout,
        allow_ssh_rsa_host_key,
        allow_agent,
        look_for_keys,
        key_filename)
    _report_adjusted_block_size(requested_block_siz, block_siz)

    with SimpleSSHClient(
            hostname,
            username,
            password,
            port,
            timeout,
            allow_ssh_rsa_host_key,
            allow_agent,
            look_for_keys,
            key_filename) as ssh_client:
        upload_files_with_ssh_client(
            ssh_client,
            files,
            block_siz)
