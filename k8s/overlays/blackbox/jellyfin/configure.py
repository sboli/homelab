import json
import os
import signal
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8096"
CLIENT = 'MediaBrowser Client="homelab", Device="blackbox", DeviceId="homelab-jellyfin", Version="1.0"'
LIBRARIES = "/Library/VirtualFolders"
READY_FILE = Path("/tmp/jellyfin-configured")


def api(method, path, body=None, *, token=None, query=None):
    if query is not None:
        path += "?" + urlencode(query, doseq=True)
    headers = {"Authorization": CLIENT, "Accept": "application/json"}
    if token is not None:
        headers["Authorization"] += f', Token="{token}"'
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = Request(BASE_URL + path, data=data, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        content = response.read()
        return json.loads(content) if content else None


def wait_for_server():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            return api("GET", "/System/Info/Public")
        except (URLError, TimeoutError):
            time.sleep(3)
    raise RuntimeError("Jellyfin did not start within five minutes")


def authenticate(username, password, wizard_complete):
    if not wizard_complete:
        api("GET", "/Startup/User")
        try:
            api("POST", "/Startup/User", {"Name": username, "Password": password})
        except HTTPError as error:
            # A previous attempt can set the password before completing the wizard.
            if error.code != 403:
                raise

    session = api("POST", "/Users/AuthenticateByName", {"Username": username, "Pw": password})
    if not session["User"]["Policy"]["IsAdministrator"]:
        raise RuntimeError("The configured Jellyfin user must be an administrator")
    token = session["AccessToken"]
    if not wizard_complete:
        api("POST", "/Startup/Complete", token=token)
    return token


def configure_library(library, folder, options, token):
    name = library["name"]
    paths = set(library["paths"])
    if folder is None:
        api("POST", LIBRARIES, {"LibraryOptions": options}, token=token, query={
            "name": name,
            "collectionType": library["type"],
            "paths": library["paths"],
        })
        print(f"Created library {name}")
        return True

    if folder["CollectionType"].lower() != library["type"]:
        raise RuntimeError(f"Existing library {name} has a different collection type")

    existing_options = folder.get("LibraryOptions")
    if existing_options is not None and any(
        existing_options.get(key) != value for key, value in options.items()
    ):
        api("POST", f"{LIBRARIES}/LibraryOptions", {
            "Id": folder["ItemId"],
            "LibraryOptions": existing_options | options,
        }, token=token)

    existing_paths = set(folder["Locations"])
    for path in sorted(paths - existing_paths):
        api("POST", f"{LIBRARIES}/Paths", {"Name": name, "PathInfo": {"Path": path}}, token=token)
    for path in sorted(existing_paths - paths):
        api("DELETE", f"{LIBRARIES}/Paths", token=token, query={"name": name, "path": path})
    # Jellyfin omits library options until the new folder has been indexed.
    return paths != existing_paths or existing_options is None


def configure():
    settings = json.loads(Path("/desired/settings.json").read_text())
    server = wait_for_server()
    token = authenticate(
        settings["adminUsername"], os.environ["JELLYFIN_ADMIN_PASSWORD"], server["StartupWizardCompleted"]
    )
    try:
        current = api("GET", "/System/Configuration", token=token)
        if any(current.get(key) != value for key, value in settings["server"].items()):
            api("POST", "/System/Configuration", current | settings["server"], token=token)

        encoding_path = "/System/Configuration/encoding"
        current_encoding = api("GET", encoding_path, token=token)
        if any(current_encoding.get(key) != value for key, value in settings["transcoding"].items()):
            api("POST", encoding_path, current_encoding | settings["transcoding"], token=token)

        folders = {folder["Name"]: folder for folder in api("GET", LIBRARIES, token=token)}
        changed = [
            configure_library(library, folders.get(library["name"]), settings["libraryOptions"], token)
            for library in settings["libraries"]
        ]
        if any(changed):
            tasks = api("GET", "/ScheduledTasks", token=token)
            scan = next(task for task in tasks if task["Key"] == "RefreshLibrary")
            if scan["State"] == "Idle":
                api("POST", f"/ScheduledTasks/Running/{scan['Id']}", token=token)
    finally:
        api("POST", "/Sessions/Logout", token=token)


if __name__ == "__main__":
    READY_FILE.unlink(missing_ok=True)
    configure()
    READY_FILE.touch()
    print("Jellyfin configuration applied")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        signal.pause()
