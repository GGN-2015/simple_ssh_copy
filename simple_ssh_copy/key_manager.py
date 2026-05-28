import os
import paramiko
from paramiko.ed25519key import Ed25519Key
from paramiko.rsakey import RSAKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

try:
    from . import utils
except:
    import utils

RSA_PRIVATE = os.path.join(utils.KEY_FOLDER, "id_rsa")
RSA_PUBLIC = os.path.join(utils.KEY_FOLDER, "id_rsa.pub")

ED25519_PRIVATE = os.path.join(utils.KEY_FOLDER, "id_ed25519")
ED25519_PUBLIC = os.path.join(utils.KEY_FOLDER, "id_ed25519.pub")

def init_id_rsa(bits=2048):
    if not os.path.isfile(RSA_PRIVATE):
        rsa_key = paramiko.RSAKey.generate(bits=bits)

        with open(RSA_PRIVATE, "w") as f:
            rsa_key.write_private_key(f)

        with open(RSA_PUBLIC, "w") as f:
            f.write(f"{rsa_key.get_name()} {rsa_key.get_base64()}\n")

def init_id_ed25519():
    if not os.path.isfile(ED25519_PRIVATE):
        priv = ed25519.Ed25519PrivateKey.generate()

        priv_pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption()
        )

        with open(ED25519_PRIVATE, "wb") as f:
            f.write(priv_pem)

        pub = priv.public_key()
        pub_ssh = pub.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        )
        with open(ED25519_PUBLIC, "wb") as f:
            f.write(pub_ssh + b"\n")

def load_rsa_key():
    return RSAKey.from_private_key_file(RSA_PRIVATE)

def load_ed25519_key():
    return Ed25519Key.from_private_key_file(ED25519_PRIVATE)

init_id_rsa()
init_id_ed25519()
if __name__ == "__main__":
    print(load_rsa_key().fingerprint)
    print(load_ed25519_key().fingerprint)
