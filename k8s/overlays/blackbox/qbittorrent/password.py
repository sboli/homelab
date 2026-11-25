import base64
import getpass
import hashlib
import secrets
import sys


if __name__ == "__main__":
    while True:
        password = getpass.getpass("New qBittorrent password for boli: ")
        if password and password == getpass.getpass("Confirm new password: "):
            break
        print("Enter the same nonempty password twice.", file=sys.stderr)

    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 100000, dklen=64)
    sys.stdout.buffer.write(base64.b64encode(salt) + b":" + base64.b64encode(key))
