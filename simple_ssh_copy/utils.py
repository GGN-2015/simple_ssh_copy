import os
DIRNOW = os.path.dirname(os.path.abspath(__file__))
KEY_FOLDER = os.path.join(DIRNOW, "keys")

if not os.path.isdir(KEY_FOLDER):
    os.makedirs(KEY_FOLDER, exist_ok=True)

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
