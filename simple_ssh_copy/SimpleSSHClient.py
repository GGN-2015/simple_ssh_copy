import paramiko

try:
    from .key_manager import load_rsa_key, load_ed25519_key
except:
    from key_manager import load_rsa_key, load_ed25519_key

def make_ssh_client(hostname: str, username: str, password:str, port: int = 22, timeout:float=15, algorithm="rsa"):
    if algorithm not in ["rsa", "ed25519"]:
        raise ValueError(f"algorithm '{algorithm}' not allowed.")
    
    if algorithm == "rsa":
        key = load_rsa_key()
    elif algorithm == "ed25519":
        key = load_ed25519_key()
    else:
        key = None

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        timeout=timeout,
        pkey=key,
        look_for_keys=False,
        allow_agent=False
    )
    return ssh

def ssh_exec_command(
    ssh:paramiko.SSHClient,
    command: str,
) -> tuple[int, bytes, bytes]:
    _, stdout, stderr = ssh.exec_command(command)

    output = stdout.read()
    error = stderr.read()
    code = stdout.channel.recv_exit_status()

    return code, output, error


class SimpleSSHClient:
    def __init__(self, hostname: str, username: str, password:str, port: int = 22, timeout:float=15) -> None:
        self.ssh_client = make_ssh_client(hostname, username, password, port, timeout)

    def __enter__(self):
        return self

    def close(self):
        self.ssh_client.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def exec_cmd(self, command: str) -> tuple[int, bytes, bytes]:
        return ssh_exec_command(
            self.ssh_client,
            command)
