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
SSH_RSA_CERT_HOST_KEY_ALGORITHM = f"{SSH_RSA_HOST_KEY_ALGORITHM}-cert-v01@openssh.com"
OPENSSH_CERT_SUFFIX = "-cert-v01@openssh.com"


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


def _dedupe_preserving_order(*algorithm_groups: tuple[str, ...]) -> tuple[str, ...]:
    algorithms = []
    seen = set()

    for group in algorithm_groups:
        for algorithm in group:
            if algorithm not in seen:
                seen.add(algorithm)
                algorithms.append(algorithm)

    return tuple(algorithms)


def _registered_algorithms(transport: paramiko.Transport, info_attribute: str) -> tuple[str, ...]:
    info = getattr(transport, info_attribute, {})
    if not isinstance(info, dict):
        return ()
    return tuple(info.keys())


def _without_openssh_cert_variants(algorithms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        algorithm
        for algorithm in algorithms
        if not algorithm.endswith(OPENSSH_CERT_SUFFIX)
    )


def _set_security_option_to_all_supported(
        security_options,
        option_name: str,
        supported_algorithms: tuple[str, ...]) -> None:
    current_algorithms = tuple(getattr(security_options, option_name))
    setattr(
        security_options,
        option_name,
        _dedupe_preserving_order(current_algorithms, supported_algorithms))


def _add_ssh_rsa_host_key_algorithm(transport: paramiko.Transport) -> None:
    paramiko.RSAKey.HASHES.setdefault(SSH_RSA_HOST_KEY_ALGORITHM, hashes.SHA1)
    paramiko.RSAKey.HASHES.setdefault(
        SSH_RSA_CERT_HOST_KEY_ALGORITHM,
        hashes.SHA1)
    transport._key_info.setdefault(SSH_RSA_HOST_KEY_ALGORITHM, paramiko.RSAKey)
    transport._key_info.setdefault(SSH_RSA_CERT_HOST_KEY_ALGORITHM, paramiko.RSAKey)


def _supported_key_exchange_algorithms(transport: paramiko.Transport) -> tuple[str, ...]:
    algorithms = _registered_algorithms(transport, "_kex_info")
    if getattr(transport, "use_gss_kex", False):
        return algorithms

    gss_kex_algorithms = set(getattr(transport, "_preferred_gsskex", ()) or ())
    return tuple(
        algorithm
        for algorithm in algorithms
        if algorithm not in gss_kex_algorithms
    )


def _supported_host_key_algorithms(transport: paramiko.Transport) -> tuple[str, ...]:
    return _without_openssh_cert_variants(
        _registered_algorithms(transport, "_key_info"))


def _supported_public_key_signature_algorithms(
        transport: paramiko.Transport) -> tuple[str, ...]:
    rsa_signature_algorithms = tuple(getattr(paramiko.RSAKey, "HASHES", {}).keys())
    return _without_openssh_cert_variants(
        _dedupe_preserving_order(
            _registered_algorithms(transport, "_key_info"),
            rsa_signature_algorithms))


def _allow_all_supported_negotiation_algorithms(
        transport: paramiko.Transport) -> None:
    security_options = transport.get_security_options()
    _set_security_option_to_all_supported(
        security_options,
        "kex",
        _supported_key_exchange_algorithms(transport))
    _set_security_option_to_all_supported(
        security_options,
        "ciphers",
        _registered_algorithms(transport, "_cipher_info"))
    _set_security_option_to_all_supported(
        security_options,
        "digests",
        _registered_algorithms(transport, "_mac_info"))
    _set_security_option_to_all_supported(
        security_options,
        "key_types",
        _supported_host_key_algorithms(transport))

    transport._preferred_pubkeys = _dedupe_preserving_order(
        tuple(transport._preferred_pubkeys),
        _supported_public_key_signature_algorithms(transport))


def _transport_factory_with_all_supported_algorithms(*args, **kwargs) -> paramiko.Transport:
    transport = paramiko.Transport(*args, **kwargs)
    _add_ssh_rsa_host_key_algorithm(transport)
    _allow_all_supported_negotiation_algorithms(transport)
    return transport


_transport_factory_with_legacy_algorithms = _transport_factory_with_all_supported_algorithms


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
        connect_kwargs["transport_factory"] = _transport_factory_with_all_supported_algorithms

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
