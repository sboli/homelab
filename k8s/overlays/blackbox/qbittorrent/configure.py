import gzip
import re
import zlib
from configparser import ConfigParser
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.request import urlopen


def read_settings(path):
    settings = ConfigParser(interpolation=None, delimiters=("=",))
    settings.optionxform = str
    settings.read(path, encoding="utf-8")
    return settings


def refresh_blocklist(path):
    url = Path("/desired/blocklist-url").read_text().strip()
    max_size = 64 * 1024 * 1024
    rule = rb"(?:\d{1,3}\.){3}\d{1,3}\s*-\s*(?:\d{1,3}\.){3}\d{1,3}\s*,\s*\d+\s*,"
    try:
        with urlopen(url, timeout=20) as response, gzip.GzipFile(fileobj=response) as archive:
            data = archive.read(max_size + 1)
        if len(data) > max_size or not re.match(rule, data):
            raise ValueError("unexpected eMule DAT blocklist format or size")
    except (OSError, EOFError, HTTPException, ValueError, zlib.error):
        if not path.is_file() or not path.stat().st_size:
            raise
        print("Blocklist download failed. Using the previous copy on the NAS.")
        return

    with NamedTemporaryFile(dir=path.parent, delete_on_close=False) as temporary:
        temporary.write(data)
        temporary.flush()
        Path(temporary.name).replace(path)
    print(f"Installed qBittorrent blocklist ({len(data)} bytes).")


config_dir = Path("/config/qBittorrent")
config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
refresh_blocklist(config_dir / "ipfilter.dat")
config_path = config_dir / "qBittorrent.conf"
current = read_settings(config_path)
desired = read_settings("/desired/settings.ini")
password_hash = Path("/credentials/password-hash").read_text().strip()
if not password_hash:
    raise RuntimeError("qBittorrent password hash is empty")
desired["WebUI"]["Password_PBKDF2"] = f"@ByteArray({password_hash})"

for section in desired.sections():
    if not current.has_section(section):
        current.add_section(section)
    current[section].update(desired[section])

with NamedTemporaryFile(mode="w", encoding="utf-8", dir=config_dir, delete_on_close=False) as temporary:
    current.write(temporary, space_around_delimiters=False)
    temporary.flush()
    Path(temporary.name).replace(config_path)
