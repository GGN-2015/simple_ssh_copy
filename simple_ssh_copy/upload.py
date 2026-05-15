from tqdm import tqdm
import os

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


def upload_files_with_ssh_client(ssh_client: SimpleSSHClient, files: list[tuple[str, str]], block_siz: int = 12 * 1024):
    for local_path, remote_path in files:
        aim_dir = "/".join(remote_path.split("/")[:-1])
        ssh_client.exec_cmd(f"mkdir -p '{aim_dir}'")
        ssh_client.exec_cmd(f"rm -rf '{remote_path}'")
        ssh_client.exec_cmd(f"touch '{remote_path}'")

        with open(local_path, "rb") as fpin:
            total = get_file_total_size(fpin)

            pbar = None
            if total > 0:
                pbar = tqdm(total=total, unit="B", unit_scale=True, desc=f"{local_path}")
            else:
                print(f"{local_path}: empty file.")

            while True:
                data_buf = fpin.read(block_siz)
                if not data_buf:
                    break

                if pbar is not None:
                    pbar.update(len(data_buf))

                cmd_now = "command printf '" + ("".join([f"\\{chr_val:03o}" for chr_val in data_buf])) + f"' >> '{remote_path}'"
                ssh_client.exec_cmd(cmd_now)

            if pbar is not None:
                pbar.close()


def upload(
        hostname: str,
        username: str,
        password: str,
        files: list[tuple[str, str]],
        block_siz: int = 1024 * 1024,
        port: int = 22,
        timeout: float = 15):

    with SimpleSSHClient(hostname, username, password, port, timeout) as ssh_client:
        upload_files_with_ssh_client(
            ssh_client,
            files,
            block_siz)