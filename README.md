# simple_ssh_copy

Transfer files to and from small or old POSIX-like devices over SSH.

This package intentionally avoids SFTP/SCP subsystems. It only needs a working
SSH login and a few basic POSIX shell commands, so it is useful for minimal
Linux systems, embedded devices, rescue environments, and older SSH servers.

## Features

- Upload a local file to a remote host.
- Download a remote file to the local machine.
- Download a remote directory recursively.
- Aborts with a yellow warning when the remote system is detected as Windows.
- Prints the remote architecture detected with `uname -m` before transfers.
- Password, empty-password, SSH agent, `~/.ssh` key, and explicit private-key
  authentication.
- Broad SSH algorithm compatibility enabled by default. During Paramiko
  transport setup, the client allows every currently supported key exchange,
  cipher, MAC/digest, server host key, and public-key signature algorithm that
  can be used by the active Paramiko transport.

For implementation notes, transfer flow, block sizes, and compatibility
details, see [Technical Details](docs/technical-details.md).

## Install

```bash
pip install simple_ssh_copy
```

For local development:

```bash
pip install -e .
```

## Command Line

Upload a file:

```bash
python -m simple_ssh_copy ./test-file.txt root@192.168.1.10:/home/root/test-file.txt
```

Download a file:

```bash
python -m simple_ssh_copy root@192.168.1.10:/home/root/test-file.txt ./test-file.txt
```

Use a non-default port:

```bash
python -m simple_ssh_copy ./test-file.txt root@192.168.1.10:2222:/home/root/test-file.txt
```

Use an explicit private key:

```bash
python -m simple_ssh_copy -i ~/.ssh/id_rsa ./test-file.txt root@192.168.1.10:/home/root/test-file.txt
```

On Windows:

```powershell
python -m simple_ssh_copy -i C:\Users\neko\.ssh\id_rsa .\test-file.txt root@169.254.115.127:/home/root/test-file.txt
```

Increase the SSH timeout:

```bash
python -m simple_ssh_copy --timeout 60 ./test-file.txt root@192.168.1.10:/home/root/test-file.txt
```

When prompted for a password, press Enter for empty-password or key-only login.
In that case the client also tries SSH agent and keys discoverable in `~/.ssh`.

## Python API

```python
import simple_ssh_copy

hostname = "192.168.1.10"
username = "root"
password = ""

simple_ssh_copy.upload(
    hostname=hostname,
    username=username,
    password=password,
    files=[("./test-file.txt", "/home/root/test-file.txt")],
    key_filename="~/.ssh/id_rsa",
)

simple_ssh_copy.download(
    hostname=hostname,
    username=username,
    password=password,
    files=[("/home/root/test-file.txt", "./test-file.txt")],
    key_filename="~/.ssh/id_rsa",
)

simple_ssh_copy.download_dir(
    hostname=hostname,
    username=username,
    password=password,
    remote_dir="/home/root/logs",
    local_dir="./logs",
    key_filename="~/.ssh/id_rsa",
)
```

Run a remote command with the low-level client:

```python
from simple_ssh_copy import SimpleSSHClient

with SimpleSSHClient(
    hostname="192.168.1.10",
    username="root",
    password="",
    key_filename="~/.ssh/id_rsa",
) as ssh:
    code, stdout, stderr = ssh.exec_cmd("uname -a")
```

## SSH Algorithm Compatibility

Some old devices require options like:

```bash
ssh -o HostKeyAlgorithms=+ssh-rsa \
    -o MACs=+hmac-sha1-96,hmac-sha1,hmac-md5 \
    -i ~/.ssh/id_rsa root@192.168.1.10
```

`simple_ssh_copy` enables a broader Paramiko-side compatibility mode by
default. It advertises all key exchange, cipher, MAC/digest, server host key,
and public-key signature algorithms registered by the active Paramiko transport,
while preserving Paramiko's default preference order first. It also restores
`ssh-rsa` host keys and RSA public-key signatures when Paramiko can use them.

The matching file-transfer command is usually:

```bash
python -m simple_ssh_copy -i ~/.ssh/id_rsa ./file root@192.168.1.10:/tmp/file
```

If you need stricter modern SSH behavior, pass
`allow_ssh_rsa_host_key=False` from the Python API. The parameter name is kept
for API compatibility, but disabling it skips the broader compatibility
transport setup.

## Path Format

Remote paths use one of these formats:

```text
user@host:/remote/path
user@host:port:/remote/path
```

Only local-to-remote and remote-to-local transfers are supported. Remote-to-
remote transfers are not supported.

## Limitations

- The remote host must provide a POSIX-like shell.
- Non-POSIX SSH servers, such as Windows command-shell SSH sessions, are not
  supported. Windows remotes are detected after SSH connection setup and abort
  with a yellow warning before file operations begin.
- Transfer startup reports the remote architecture with `uname -m`.
- Upload uses `mkdir` and `base64` on the remote host.
- Upload sends base64 fragments through bounded remote commands, then decodes
  the assembled temporary file on the remote host.
- Download uses `stat`, `dd`, and `find` for directory downloads.
- Directory upload is not implemented.
- Very large uploads may be slower than real SCP/SFTP because data is written
  through remote shell commands.
