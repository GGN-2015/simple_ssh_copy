# Technical Details

`simple_ssh_copy` is built for POSIX-like machines where an SSH login works but
SFTP or SCP may be missing, disabled, too new, or too old for the target system.
The library uses Paramiko for SSH transport and authentication, then moves file
data through ordinary POSIX shell commands.

## Transport Model

The package does not request the SFTP subsystem and does not invoke the SCP
protocol. Each operation opens an SSH command channel with Paramiko and relies
on a small set of POSIX-like commands on the remote host.

The remote SSH server must provide a POSIX-like shell. Non-POSIX SSH servers,
such as Windows command-shell sessions, are not supported. Upload checks this
before transferring data and raises a clear error if the remote shell does not
behave like POSIX:

```sh
printf %s simple_ssh_copy_posix_shell_ok
```

```text
POSIX-like remote shell is required.
```

The remote host must also provide:

- `mkdir` and `base64` for uploads
- `stat` and `dd` for file downloads
- `find` for recursive directory downloads

This makes the transfer path slower than optimized SFTP/SCP for large files,
but it keeps the dependency surface small for minimal Linux systems, embedded
devices, rescue shells, and legacy SSH servers.

## Upload Flow

Uploads are implemented in `simple_ssh_copy/upload.py`.

Before uploading each file, the client creates the destination directory with:

```sh
mkdir -p <remote-dir>
```

Before the first upload, the client checks that the remote host can decode
base64 input. The POSIX-shell check runs before this step:

```sh
printf '' | command base64 -d >/dev/null
```

The upload does not stream file data through stdin. Instead, the local file is
base64-encoded and sent through a sequence of short remote commands.

First, a temporary base64 file is created in the destination directory:

```sh
: > <remote-temp-path>
```

Then each base64 fragment is appended to that temporary file:

```sh
printf %s <base64-fragment> >> <remote-temp-path>
```

After all fragments have been appended, the remote host decodes the temporary
file into the requested target path:

```sh
command base64 -d <remote-temp-path> > <remote-path>
```

Finally, the temporary base64 file is removed:

```sh
rm -f <remote-temp-path>
```

If the upload is interrupted or fails before the final decode completes, the
client still attempts to remove the temporary base64 file. It does not try to
roll back every remote-side effect.

The local file is opened in binary mode and encoded as a continuous base64
stream. The implementation preserves 3-byte alignment between reads, so padding
is only emitted at the end of the file.

The default upload `block_siz` is `4096`, and it means the maximum length of one
remote upload command string. It is not a `channel.sendall(...)` size limit.
Payload fragments are sized so the complete `printf %s ... >> <temp>` command
stays within that limit.

The high-level `upload()` API probes this limit before opening the real upload
connection. It creates a separate experimental SSH connection and runs a
no-op command whose UTF-8 length is exactly the requested `block_siz`. If that
probe command resets the SSH connection or the remote shell reports
`Argument list too long`, the client closes that experimental connection,
halves `block_siz`, and retries with a new experimental connection. This
continues until a probe succeeds. If the probe still fails after `block_siz`
falls below `64`, the upload is rejected as unusable for this SSH connection.

When the successful probed value differs from the requested or default
`block_siz`, the client prints a warning to stderr with the actual value it will
use for the upload.

The lower-level `upload_files_with_ssh_client()` API receives an already-open
SSH client and therefore does not open extra probe connections. Callers using
that lower-level API are responsible for choosing a suitable `block_siz`.

Upload progress is based on the local file size. Empty files are detected and
reported without creating a progress bar.

## Download Flow

File downloads are implemented in `simple_ssh_copy/download.py`.

The client first asks the remote host for the file size:

```sh
stat -c %s <remote-path> 2>/dev/null || echo 0
```

The file is then read block by block with `dd`:

```sh
command dd skip=<offset> count=1 bs=<block-size> if=<remote-path> 2>/dev/null
```

The default download block size is `1024 * 1024` bytes. The `offset` is a block
index, not a byte index. The loop stops when `dd` returns no data or when the
returned block is smaller than the requested block size.

Downloaded data is written to the local destination in binary mode. Local
parent directories are created automatically.

## Recursive Directory Downloads

Recursive directory downloads are implemented in `simple_ssh_copy/download_dir.py`.

The client checks that the remote directory exists:

```sh
test -d <remote-dir>
```

It then lists files with:

```sh
find <remote-dir> -type f
```

Each discovered remote file is downloaded using the same `dd`-based file
download routine. The relative path under the remote root is preserved under
the local destination directory.

Directory upload is not currently implemented.

## Authentication Behavior

`SimpleSSHClient` wraps Paramiko's `SSHClient`.

When the password is `None` or an empty string, agent and discoverable key
authentication are enabled by default. Empty-password login also tries
Paramiko's `auth_none` path before normal password/key authentication.

An explicit private key can be passed through `key_filename`. The command-line
interface exposes this with `-i` or `--identity-file`.

The command-line entry point catches Paramiko authentication failures and prints
a short user-facing error instead of exposing a Python traceback:

```text
Error: Authentication failed.
```

The Python API still raises exceptions normally so callers can handle them in
their own code.

## Legacy SSH Compatibility

Legacy compatibility is enabled by default because many target devices expose
old SSH servers. The transport setup adds support for:

- `ssh-rsa` host keys
- RSA public-key signing with `ssh-rsa`
- legacy MACs when Paramiko supports them:
  - `hmac-sha1-96`
  - `hmac-sha1`
  - `hmac-md5`

For stricter modern SSH behavior, pass `allow_ssh_rsa_host_key=False` from the
Python API.

## Block Size Defaults

The transfer block sizes are intentionally different:

- upload command length default: `4096` UTF-8 bytes
- file download default: `1024 * 1024` bytes
- recursive directory download file block default: `1024 * 1024` bytes

Upload uses a small default command length because some target shells and SSH
servers have limited command-line handling. Download uses larger `dd` blocks to
reduce the number of remote command executions.

The Python API exposes these values as `block_siz` for upload and `block_size`
for download. The command-line interface currently does not expose block-size
options.

## Error Handling Boundaries

Remote setup commands are checked for non-zero exit status where required. A
failed upload raises a `RuntimeError` with remote stderr/stdout content when
available.

For command-line use, `KeyboardInterrupt` is caught and reported as a short
user-facing interruption message instead of a Python traceback. Upload cleanup
still runs before that error reaches the CLI boundary.

If repeated upload command-size probes fail down to the minimum size, the CLI
prints a short SSH-connection usability error instead of exposing the Paramiko
or socket traceback.

Download loops treat an empty `dd` result as end-of-file. The remote file size
is used for progress reporting, but the data loop is driven by bytes returned
from the remote command.

## Path and Shell Notes

Remote paths are interpreted by the remote shell. Upload paths are shell-quoted
before being used in `mkdir` and `base64 -d` commands. Some download and directory
commands currently build single-quoted shell snippets, so remote paths
containing single quotes are not recommended.

Only local-to-remote and remote-to-local transfers are supported. Remote-to-
remote transfers are intentionally rejected by the CLI.
