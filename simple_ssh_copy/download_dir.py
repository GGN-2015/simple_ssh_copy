from tqdm import tqdm
import os

try:
    from .SimpleSSHClient import SimpleSSHClient
    from . import utils
except:
    from SimpleSSHClient import SimpleSSHClient
    import utils


def check_remote_dir_exists(ssh_client: SimpleSSHClient, remote_dir: str) -> bool:
    cmd = f"test -d '{remote_dir}'"
    code, _, _ = ssh_client.exec_cmd(cmd)
    return code == 0


def list_remote_files_recursive(ssh_client: SimpleSSHClient, remote_dir: str, encoding:str) -> list[str]:
    cmd = f"find '{remote_dir}' -type f"
    _, out, _ = ssh_client.exec_cmd(cmd)
    file_list = [f.strip().decode(encoding=encoding) for f in out.strip().splitlines() if f.strip()]
    return file_list


def download_single_file(ssh_client: SimpleSSHClient,
                         remote_path: str,
                         local_path: str,
                         block_size: int = 1024 * 1024):

    if not os.path.isabs(local_path):
        local_path = os.path.abspath(local_path)

    local_dir = os.path.dirname(local_path)
    os.makedirs(local_dir, exist_ok=True)

    total_size = utils.get_remote_file_size(ssh_client, remote_path)
    pbar = None

    if total_size > 0:
        pbar = tqdm(total=total_size, unit="B", unit_scale=True, desc=f"{remote_path}")
    else:
        print(f"{remote_path}: empty file.")

    with open(local_path, "wb") as fout:
        offset = 0
        while True:
            cmd = (f"command dd skip={offset} count=1 bs={block_size} if='{remote_path}' 2>/dev/null")
            code, out, err = ssh_client.exec_cmd(cmd)
            data_buf = out

            if not data_buf:
                break

            fout.write(data_buf)

            if pbar:
                pbar.update(len(data_buf))

            offset += 1
            if len(data_buf) < block_size:
                break

    if pbar:
        pbar.close()


def download_directory_recursive(ssh_client: SimpleSSHClient,
                                 remote_root: str,
                                 local_root: str,
                                 encoding:str = "utf-8",
                                 block_size: int = 1024 * 1024):

    if not check_remote_dir_exists(ssh_client, remote_root):
        raise FileNotFoundError(f"Remote directory does not exist: {remote_root}")

    remote_files = list_remote_files_recursive(ssh_client, remote_root, encoding)

    for remote_file in remote_files:
        rel_path = os.path.relpath(remote_file, remote_root)
        local_file = os.path.join(local_root, rel_path)
        download_single_file(ssh_client, remote_file, local_file, block_size)


def download_dir(
        hostname: str,
        username: str,
        password: str,
        remote_dir: str,
        local_dir: str,
        encoding:str="utf-8",
        block_size: int = 1024 * 1024,
        port: int = 22,
        timeout: float = 15
):
    with SimpleSSHClient(hostname, username, password, port, timeout) as ssh_client:
        download_directory_recursive(
            ssh_client,
            remote_dir,
            local_dir,
            encoding,
            block_size
        )
