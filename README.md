# simple_ssh_copy
Transfer files to/from a minimal machine with SSH access.

## Install

```bash
pip install simple_ssh_copy
```

## Usage

```python
import simple_ssh_copy

HOSTNAME = "..."
USERNAME = "..."
PASSWORD = "..."

# download file list
REMOTE_PATH = "..."
LOCAL_PATH = "..."
simple_ssh_copy.download(HOSTNAME, USERNAME, PASSWORD, [(REMOTE_PATH, LOCAL_PATH)])

# upload file list
REMOTE_PATH = "..."
LOCAL_PATH = "..."
simple_ssh_copy.upload(HOSTNAME, USERNAME, PASSWORD, [(LOCAL_PATH, REMOTE_PATH)])

# download dir
REMOTE_DIR = ".."
LOCAL_DIR = "..."
simple_ssh_copy.download_dir(HOSTNAME, USERNAME, PASSWORD, REMOTE_DIR, LOCAL_DIR)
```
