from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import secrets
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

from simple_ssh_copy import upload


HOSTNAME = "169.254.115.127"
USERNAME = "root"
REMOTE_DIR = "/home/root"
FILE_SIZE = 64 * 1024


def hash_file(path: Path) -> dict[str, str]:
    digests = {
        "MD5": hashlib.md5(),
        "SHA1": hashlib.sha1(),
        "SHA256": hashlib.sha256(),
        "SHA512": hashlib.sha512(),
    }
    with path.open("rb") as fpin:
        for chunk in iter(lambda: fpin.read(1024 * 1024), b""):
            for digest in digests.values():
                digest.update(chunk)
    return {
        name: digest.hexdigest()
        for name, digest in digests.items()
    }


def write_random_file(path: Path) -> None:
    path.write_bytes(os.urandom(FILE_SIZE))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual upload check: generate a 64KB random binary file and upload "
            "it to root@169.254.115.127:~."
        )
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=None,
        help="Override upload block size in bytes"
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
        "--remote-name",
        default=None,
        help="Remote file name under root's home directory"
    )
    args = parser.parse_args()

    remote_name = args.remote_name
    if remote_name is None:
        remote_name = f"simple_ssh_copy_random_64kb_{secrets.token_hex(4)}.bin"
    if "/" in remote_name or "\\" in remote_name:
        print("Error: --remote-name must be a file name, not a path.", file=sys.stderr)
        return 2

    remote_path = f"{REMOTE_DIR}/{remote_name}"

    with tempfile.TemporaryDirectory(prefix="simple_ssh_copy_") as tmpdir:
        local_path = Path(tmpdir) / remote_name
        write_random_file(local_path)
        local_hashes = hash_file(local_path)

        print(f"Local file: {local_path}")
        print(f"Size: {FILE_SIZE} bytes")
        print("Hashes:")
        for name, value in local_hashes.items():
            print(f"  {name}: {value}")
        print(f"Remote target: {USERNAME}@{HOSTNAME}:{remote_path}")

        password = getpass.getpass(f"{USERNAME}@{HOSTNAME}'s password: ")

        upload_kwargs = {}
        if args.block_size is not None:
            upload_kwargs["block_siz"] = args.block_size

        upload(
            hostname=HOSTNAME,
            username=USERNAME,
            password=password,
            files=[(str(local_path), remote_path)],
            timeout=args.timeout,
            key_filename=args.identity_file,
            **upload_kwargs)

    print("Upload complete.")
    print(f"Verify on remote: md5sum {remote_path}")
    print(f"Verify on remote: sha1sum {remote_path}")
    print(f"Verify on remote: sha256sum {remote_path}")
    print(f"Verify on remote: sha512sum {remote_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
