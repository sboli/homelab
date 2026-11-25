import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as XML


app = os.environ["ARR_APP"]
path = Path("/config/config.xml")
root = XML.parse(path).getroot() if path.exists() else XML.Element("Config")
settings = {
    "ApiKey": Path("/credentials/api-key").read_text().strip(),
    "AuthenticationMethod": "Forms",
    "AuthenticationRequired": "Enabled",
    "InstanceName": app.capitalize(),
    "LaunchBrowser": "False",
    "PostgresHost": "media-postgres.homelab.svc.cluster.local",
    "PostgresPort": "5432",
    "PostgresUser": app,
    "PostgresPassword": Path("/credentials/db-password").read_text().strip(),
    "PostgresMainDb": f"{app}_main",
    "PostgresLogDb": f"{app}_log",
}
for key, value in settings.items():
    node = root.find(key)
    if node is None:
        node = XML.SubElement(root, key)
    node.text = value

XML.indent(root, space="  ")
with NamedTemporaryFile(dir=path.parent, delete_on_close=False) as temporary:
    XML.ElementTree(root).write(temporary, encoding="utf-8", xml_declaration=True)
    temporary.flush()
    Path(temporary.name).replace(path)
