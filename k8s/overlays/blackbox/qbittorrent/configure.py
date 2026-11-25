from configparser import ConfigParser
from pathlib import Path
from tempfile import NamedTemporaryFile


def read_settings(path):
    settings = ConfigParser(interpolation=None, delimiters=("=",))
    settings.optionxform = str
    settings.read(path, encoding="utf-8")
    return settings


config_dir = Path("/config/qBittorrent")
config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
config_path = config_dir / "qBittorrent.conf"
current = read_settings(config_path)
desired = read_settings("/desired/settings.ini")
password_hash = Path("/credentials/password-hash").read_text().strip()
if not password_hash:
    raise RuntimeError("qBittorrent password hash is empty")
desired["Preferences"][r"WebUI\Password_PBKDF2"] = f"@ByteArray({password_hash})"

for section in desired.sections():
    if not current.has_section(section):
        current.add_section(section)
    current[section].update(desired[section])

with NamedTemporaryFile(mode="w", encoding="utf-8", dir=config_dir, delete_on_close=False) as temporary:
    current.write(temporary, space_around_delimiters=False)
    temporary.flush()
    Path(temporary.name).replace(config_path)
