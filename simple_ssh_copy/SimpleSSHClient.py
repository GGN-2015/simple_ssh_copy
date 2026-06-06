import inspect

import paramiko
from cryptography.hazmat.primitives import hashes

try:
    from . import utils
    from .key_manager import load_rsa_key, load_ed25519_key
except:
    import utils
    from key_manager import load_rsa_key, load_ed25519_key


SSH_RSA_HOST_KEY_ALGORITHM = "ssh-rsa"
LEGACY_MACS = ("hmac-sha1-96", "hmac-sha1", "hmac-md5")


class SimpleParamikoSSHClient(paramiko.SSHClient):
    def _auth(
            self,
            username,
            password,
            pkey,
            key_filenames,
            allow_agent,
            look_for_keys,
            passphrase):
        if password == "":
            try:
                self._transport.auth_none(username)
                return
            except paramiko.AuthenticationException:
                pass

        return super()._auth(
            username,
            password,
            pkey,
            key_filenames,
            allow_agent,
            look_for_keys,
            passphrase)


def _add_ssh_rsa_host_key_algorithm(transport: paramiko.Transport) -> None:
    paramiko.RSAKey.HASHES.setdefault(SSH_RSA_HOST_KEY_ALGORITHM, hashes.SHA1)
    paramiko.RSAKey.HASHES.setdefault(
        f"{SSH_RSA_HOST_KEY_ALGORITHM}-cert-v01@openssh.com",
        hashes.SHA1)
    transport._key_info.setdefault(SSH_RSA_HOST_KEY_ALGORITHM, paramiko.RSAKey)
    security_options = transport.get_security_options()
    key_types = tuple(security_options.key_types)

    if SSH_RSA_HOST_KEY_ALGORITHM not in key_types:
        security_options.key_types = key_types + (SSH_RSA_HOST_KEY_ALGORITHM,)


def _add_ssh_rsa_public_key_algorithm(transport: paramiko.Transport) -> None:
    pubkeys = tuple(transport._preferred_pubkeys)

    if SSH_RSA_HOST_KEY_ALGORITHM not in pubkeys:
        transport._preferred_pubkeys = pubkeys + (SSH_RSA_HOST_KEY_ALGORITHM,)


def _add_legacy_macs(transport: paramiko.Transport) -> None:
    security_options = transport.get_security_options()
    digests = tuple(security_options.digests)
    available_macs = set(transport._mac_info.keys())
    macs_to_add = tuple(
        mac
        for mac in LEGACY_MACS
        if mac in available_macs and mac not in digests
    )

    if macs_to_add:
        security_options.digests = digests + macs_to_add


def _transport_factory_with_legacy_algorithms(*args, **kwargs) -> paramiko.Transport:
    transport = paramiko.Transport(*args, **kwargs)
    _add_ssh_rsa_host_key_algorithm(transport)
    _add_ssh_rsa_public_key_algorithm(transport)
    _add_legacy_macs(transport)
    return transport


def _ssh_client_connect_accepts_transport_factory() -> bool:
    try:
        return "transport_factory" in inspect.signature(paramiko.SSHClient.connect).parameters
    except (TypeError, ValueError):
        return True


def make_ssh_client(
        hostname: str,
        username: str,
        password: str | None,
        port: int = 22,
        timeout: float = 15,
        algorithm: str | None = "rsa",
        allow_ssh_rsa_host_key: bool = True,
        allow_agent: bool | None = None,
        look_for_keys: bool | None = None,
        key_filename: str | list[str] | None = None):
    if algorithm not in ["rsa", "ed25519", None]:
        raise ValueError(f"algorithm '{algorithm}' not allowed.")
    
    if key_filename is not None:
        key = None
    elif algorithm == "rsa":
        key = load_rsa_key()
    elif algorithm == "ed25519":
        key = load_ed25519_key()
    else:
        key = None

    ssh = SimpleParamikoSSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    use_default_ssh_auth = password in (None, "")
    if allow_agent is None:
        allow_agent = use_default_ssh_auth
    if look_for_keys is None:
        look_for_keys = use_default_ssh_auth

    connect_kwargs = dict(
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        timeout=timeout,
        pkey=key,
        key_filename=key_filename,
        look_for_keys=look_for_keys,
        allow_agent=allow_agent,
        banner_timeout=timeout,
        auth_timeout=timeout,
        channel_timeout=timeout
    )
    if allow_ssh_rsa_host_key and _ssh_client_connect_accepts_transport_factory():
        connect_kwargs["transport_factory"] = _transport_factory_with_legacy_algorithms

    ssh.connect(**connect_kwargs)
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
    def __init__(
            self,
            hostname: str,
            username: str,
            password: str | None,
            port: int = 22,
            timeout: float = 15,
            allow_ssh_rsa_host_key: bool = True,
            allow_agent: bool | None = None,
            look_for_keys: bool | None = None,
            key_filename: str | list[str] | None = None) -> None:
        self.ssh_client = make_ssh_client(
            hostname,
            username,
            password,
            port,
            timeout,
            allow_ssh_rsa_host_key=allow_ssh_rsa_host_key,
            allow_agent=allow_agent,
            look_for_keys=look_for_keys,
            key_filename=key_filename)
        try:
            utils.ensure_remote_is_not_windows(self)
        except Exception:
            self.ssh_client.close()
            raise

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
