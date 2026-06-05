from tqdm import tqdm
import os
import posixpath
import shlex

try:
    from .SimpleSSHClient import SimpleSSHClient
except:
    from SimpleSSHClient import SimpleSSHClient


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


def _upload_file_with_stdin(
        ssh_client: SimpleSSHClient,
        local_path: str,
        remote_path: str,
        block_siz: int) -> None:
    with open(local_path, "rb") as fpin:
        total = get_file_total_size(fpin)

        pbar = None
        if total > 0:
            pbar = tqdm(total=total, unit="B", unit_scale=True, desc=f"{local_path}")
        else:
            print(f"{local_path}: empty file.")

        stdin, stdout, stderr = ssh_client.ssh_client.exec_command(
            f"command cat > {shlex.quote(remote_path)}"
        )
        channel = stdin.channel

        try:
            while True:
                data_buf = fpin.read(block_siz)
                if not data_buf:
                    break

                channel.sendall(data_buf)
                if pbar is not None:
                    pbar.update(len(data_buf))

            channel.shutdown_write()
            output = stdout.read()
            error = stderr.read()
            code = stdout.channel.recv_exit_status()
        finally:
            if pbar is not None:
                pbar.close()

        if code != 0:
            message = error.decode(errors="replace").strip()
            if output:
                output_text = output.decode(errors="replace").strip()
                message = f"{message}\n{output_text}".strip()
            raise RuntimeError(message or f"failed to upload {local_path} to {remote_path}")


def upload_files_with_ssh_client(ssh_client: SimpleSSHClient, files: list[tuple[str, str]], block_siz: int = 1024):
    block_siz = max(1, block_siz)

    for local_path, remote_path in files:
        aim_dir = posixpath.dirname(remote_path)
        if aim_dir:
            _check_remote_command(ssh_client, f"mkdir -p {shlex.quote(aim_dir)}")

        _upload_file_with_stdin(
            ssh_client,
            local_path,
            remote_path,
            block_siz)


def upload(
        hostname: str,
        username: str,
        password: str | None,
        files: list[tuple[str, str]],
        block_siz: int = 1024,
        port: int = 22,
        timeout: float = 15,
        allow_ssh_rsa_host_key: bool = True,
        allow_agent: bool | None = None,
        look_for_keys: bool | None = None,
        key_filename: str | list[str] | None = None):
    
    block_siz = max(1, block_siz)
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
