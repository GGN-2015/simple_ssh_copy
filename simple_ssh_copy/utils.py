
try:
    from .SimpleSSHClient import SimpleSSHClient
except:
    from SimpleSSHClient import SimpleSSHClient

def get_remote_file_size(ssh_client: SimpleSSHClient, remote_path: str) -> int:
    cmd = f"stat -c %s '{remote_path}' 2>/dev/null || echo 0"
    _, out, _ = ssh_client.exec_cmd(cmd)
    try:
        return int(out.strip())
    except:
        return 0
