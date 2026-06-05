import sys
import argparse
import getpass
import paramiko
from . import upload, download
from .errors import UnsupportedRemoteShellError


def _authentication_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return "Error: Authentication failed."
    if message.lower().rstrip(".") == "authentication failed":
        return "Error: Authentication failed."
    return f"Error: Authentication failed: {message}"


def parse_remote_path(path):
    if "@" not in path:
        raise ValueError("remote path must be formatted as: user@host:path or user@host:port:path")

    user_part, remote_path = path.split(":", 1)
    if ":" in user_part:
        user, host_port = user_part.split("@")
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        user, host = user_part.split("@")
        port = 22

    return user, host, port, remote_path


def is_remote(path):
    return ":" in path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SSH file transfer tool mimicking scp command",
        usage="%(prog)s [source] [destination]\nSupported formats:\n"
              "  Local -> Remote:  file.txt user@host:/path/\n"
              "  Remote -> Local:  user@host:/path/file.txt ./\n"
              "  Specify port:     file.txt user@host:22:/path/"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="SSH connection/auth/channel timeout in seconds. Default: 30"
    )
    parser.add_argument(
        "-i",
        "--identity-file",
        default=None,
        help="Private key file to use for SSH authentication"
    )
    parser.add_argument(
        "source_destination",
        nargs="*",
        metavar="path"
    )


    args = parser.parse_args()

    if len(args.source_destination) != 2:
        parser.print_help()
        return 1

    src, dst = args.source_destination

    # Judge transfer direction
    src_remote = is_remote(src)
    dst_remote = is_remote(dst)

    if src_remote and dst_remote:
        print("Error: Remote-to-remote transfer is not supported", file=sys.stderr)
        return 1

    if not src_remote and not dst_remote:
        print("Error: At least one remote path user@host:path is required", file=sys.stderr)
        return 1

    try:
        # Local upload to remote
        if not src_remote and dst_remote:
            user, host, port, remote_path = parse_remote_path(dst)
            password = getpass.getpass(f"{user}@{host}'s password: ")
            upload(
                hostname=host,
                port=port,
                username=user,
                password=password,
                files=[(src, remote_path)],
                timeout=args.timeout,
                key_filename=args.identity_file)
            return 0

        # Remote download to local
        elif src_remote and not dst_remote:
            user, host, port, remote_path = parse_remote_path(src)
            local_path = dst
            password = getpass.getpass(f"{user}@{host}'s password: ")
            download(
                hostname=host,
                port=port,
                username=user,
                password=password,
                files=[(remote_path, local_path)],
                timeout=args.timeout,
                key_filename=args.identity_file)
            return 0
    except paramiko.AuthenticationException as exc:
        print(_authentication_error_message(exc), file=sys.stderr)
        return 1
    except UnsupportedRemoteShellError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Error: Interrupted by user.", file=sys.stderr)
        return 130

    print("Error: Unsupported transfer mode", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
