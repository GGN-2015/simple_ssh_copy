from tqdm import tqdm
import os

try:
    from .SimpleSSHClient import SimpleSSHClient
    from . import utils
except:
    from SimpleSSHClient import SimpleSSHClient
    import utils


def download_files_with_ssh_client(ssh_client: SimpleSSHClient, files: list[tuple[str, str]], block_size: int = 1024 * 1024):
    for remote_path, local_path in files:
        # Get absolute path
        if not os.path.isabs(local_path):
            local_path = os.path.abspath(local_path)

        # Create local directory
        local_dir = os.path.dirname(local_path)
        os.makedirs(local_dir, exist_ok=True)

        # Get remote file size
        total_size = utils.get_remote_file_size(ssh_client, remote_path)

        pbar = None
        if total_size > 0:
            pbar = tqdm(total=total_size, unit="B", unit_scale=True, desc=f"{remote_path}")
        else:
            print(f"{remote_path}: empty file.")

        # Open local file for writing
        with open(local_path, "wb") as fout:
            offset = 0
            while True:
                # Read a block of binary data from remote
                cmd = f"command dd skip={offset} count=1 bs={block_size} if='{remote_path}' 2>/dev/null"
                code, out, err = ssh_client.exec_cmd(cmd)

                # Received data buffer
                data_buf = out
                if not data_buf:
                    break

                # Write to local file
                fout.write(data_buf)

                # Update progress bar
                if pbar is not None:
                    pbar.update(len(data_buf))

                offset += 1

                # End of file
                if len(data_buf) < block_size:
                    break

        if pbar is not None:
            pbar.close()


def download(
        hostname: str,
        username: str,
        password: str,
        files: list[tuple[str, str]],
        block_size: int = 1024 * 1024,
        port: int = 22,
        timeout: float = 15
):
    with SimpleSSHClient(hostname, username, password, port, timeout) as ssh_client:
        download_files_with_ssh_client(
            ssh_client,
            files,
            block_size
        )
