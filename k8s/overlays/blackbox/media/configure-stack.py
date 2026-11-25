import http.cookiejar
import json
import signal
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


NAMESPACE = "homelab.svc.cluster.local"
CREDENTIALS = Path("/credentials")
CONFIG = json.loads(Path("/desired/settings.json").read_text())
READY = Path("/tmp/media-configured")
CLIENT = 'MediaBrowser Client="homelab", Device="blackbox", DeviceId="homelab-media-stack", Version="1.0"'


def secret(name):
    return (CREDENTIALS / name).read_text().strip()


def service_host(name):
    return f"{name}.{NAMESPACE}"


class Service:
    def __init__(self, name, port, prefix="", headers=None):
        self.name = name
        self.url = f"http://{service_host(name)}:{port}"
        self.prefix = prefix
        self.headers = headers or {}
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, method, path, body=None, *, query=None, form=False, timeout=28):
        url = self.url + self.prefix + path
        if query:
            url += "?" + urlencode(query)
        headers = {"Accept": "application/json"} | self.headers
        data = None
        if body is not None:
            if form:
                headers["Content-Type"] = "application/x-www-form-urlencoded"
                data = urlencode(body).encode()
            else:
                headers["Content-Type"] = "application/json"
                data = json.dumps(body).encode()
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                content = response.read()
                if not content:
                    return None
                if "application/json" in response.headers.get("Content-Type", ""):
                    return json.loads(content)
                return content
        except HTTPError as error:
            raise RuntimeError(f"{self.name} {method} {path}: HTTP {error.code}") from None


def arr(name, port, version):
    return Service(name, port, f"/api/{version}", {"X-Api-Key": secret(f"{name}-api-key")})


def configure_login(app):
    current = app.request("GET", "/config/host")
    changes = {
        "authenticationMethod": "forms",
        "authenticationRequired": "enabled",
        "applicationUrl": f"http://{app.name}.home.stephenbolivar.com",
    }
    if not current.get("username"):
        password = secret("arr-admin-password")
        changes |= {"username": CONFIG["username"], "password": password, "passwordConfirmation": password}
    if any(current.get(key) != value for key, value in changes.items()):
        app.request("PUT", f"/config/host/{current['id']}", current | changes)


def configure_library(app, path):
    folders = app.request("GET", "/rootfolder")
    if not any(folder["path"].rstrip("/") == path for folder in folders):
        app.request("POST", "/rootfolder", {"path": path})
    options = app.request("GET", "/config/mediamanagement")
    if options.get("copyUsingHardlinks") is True:
        app.request("PUT", f"/config/mediamanagement/{options['id']}", options | {"copyUsingHardlinks": False})


def configure_provider(app, endpoint, implementation, name, values, *, timeout=28, **options):
    existing = next((item for item in app.request("GET", endpoint) if item["name"] == name), None)
    if existing and existing["implementation"] != implementation:
        raise RuntimeError(f"{app.name}: {name} already uses a different implementation")
    item = existing or next(
        row for row in app.request("GET", f"{endpoint}/schema") if row["implementation"] == implementation
    )
    updates = {key.lower(): value for key, value in values.items()}
    fields = {field["name"].lower(): field for field in item["fields"]}
    missing = updates.keys() - fields.keys()
    if missing:
        raise RuntimeError(f"{app.name}: {implementation} is missing fields {sorted(missing)}")
    changed = not existing or any(item.get(key) != value for key, value in options.items())
    for key, value in updates.items():
        if fields[key].get("value") != value:
            fields[key]["value"] = value
            changed = True
    if changed:
        item.update(options, name=name)
        if existing:
            app.request("PUT", f"{endpoint}/{existing['id']}", item, timeout=timeout)
        else:
            app.request("POST", endpoint, item, timeout=timeout)


def configure_flaresolverr(prowlarr):
    label = "flaresolverr"
    tag = next((tag for tag in prowlarr.request("GET", "/tag") if tag["label"] == label), None)
    if tag is None:
        tag = prowlarr.request("POST", "/tag", {"label": label})
    # Prowlarr runs browser checks before saving the proxy.
    configure_provider(prowlarr, "/indexerProxy", "FlareSolverr", "FlareSolverr", {
        "host": f"http://{service_host('flaresolverr')}:8191",
    }, timeout=180, tags=[tag["id"]])


def jellyfin_api_key():
    jellyfin = Service("jellyfin", 8096, headers={"Authorization": CLIENT})
    login = jellyfin.request("POST", "/Users/AuthenticateByName", {
        "Username": CONFIG["username"], "Pw": secret("jellyfin-password"),
    })
    jellyfin.headers["Authorization"] += f', Token="{login["AccessToken"]}"'
    name = "Homelab Sonarr and Radarr"
    try:
        keys = jellyfin.request("GET", "/Auth/Keys")["Items"]
        if not any(key["AppName"] == name for key in keys):
            jellyfin.request("POST", "/Auth/Keys", query={"app": name})
            keys = jellyfin.request("GET", "/Auth/Keys")["Items"]
        return next(key["AccessToken"] for key in keys if key["AppName"] == name)
    finally:
        jellyfin.request("POST", "/Sessions/Logout")


def configure_seerr(applications):
    seerr = Service("seerr", 5055, "/api/v1")
    public = seerr.request("GET", "/settings/public")
    login = {"username": CONFIG["username"], "password": secret("jellyfin-password")}
    if public.get("mediaServerType", 4) == 4:
        login |= {"hostname": service_host("jellyfin"), "port": 8096, "urlBase": "", "useSsl": False, "serverType": 2}
    seerr.request("POST", "/auth/jellyfin", login)

    current = seerr.request("GET", "/settings/jellyfin")
    public_url = "http://jellyfin.home.stephenbolivar.com"
    if current.get("externalHostname") != public_url:
        seerr.request("POST", "/settings/jellyfin", {"externalHostname": public_url})
    required_libraries = set(CONFIG["jellyfinLibraries"])
    libraries = current["libraries"]
    if required_libraries - {library["name"] for library in libraries}:
        libraries = seerr.request("POST", "/settings/jellyfin/library/sync")
        missing = required_libraries - {library["name"] for library in libraries}
        if missing:
            raise RuntimeError(f"seerr: Jellyfin libraries missing: {', '.join(sorted(missing))}")
    for library in libraries:
        if library["name"] in required_libraries and not library["enabled"]:
            seerr.request("PUT", f"/settings/jellyfin/library/{library['id']}", {"enabled": True})

    for name, app in applications.items():
        conf = CONFIG["applications"][name]
        profiles = {profile["name"]: profile for profile in app.request("GET", "/qualityprofile")}
        profile = next((profiles[name] for name in CONFIG["qualityProfiles"] if name in profiles), None)
        if profile is None:
            raise RuntimeError(f"{app.name}: expected quality profiles are unavailable")
        desired = {
            "name": name.capitalize(),
            "hostname": service_host(name),
            "port": conf["port"],
            "apiKey": secret(f"{name}-api-key"),
            "useSsl": False,
            "baseUrl": "",
            "activeProfileId": profile["id"],
            "activeProfileName": profile["name"],
            "activeDirectory": conf["root"],
            "tags": [],
            "is4k": False,
            "isDefault": True,
            "externalUrl": f"http://{name}.home.stephenbolivar.com",
            "syncEnabled": True,
            "preventSearch": False,
            "tagRequests": False,
            "overrideRule": [],
        }
        if name == "radarr":
            desired["minimumAvailability"] = "released"
        else:
            desired.update(
                seriesType="standard", animeSeriesType="anime",
                enableSeasonFolders=True, monitorNewItems="all",
            )
        endpoint = f"/settings/{name}"
        current = next((item for item in seerr.request("GET", endpoint) if item["name"] == desired["name"]), None)
        if current is None:
            seerr.request("POST", endpoint, desired)
        elif any(current.get(key) != value for key, value in desired.items()):
            settings_id = current.pop("id")
            seerr.request("PUT", f"{endpoint}/{settings_id}", current | desired)
    if not public.get("initialized"):
        seerr.request("POST", "/settings/initialize")


def configure_download_clients(applications):
    key = secret("qbittorrent-api-key")
    qbittorrent = Service("qbittorrent", 8089, "/api/v2", {"Authorization": f"Bearer {key}"})
    categories = qbittorrent.request("GET", "/torrents/categories")
    for name, app in applications.items():
        conf = CONFIG["applications"][name]
        category = conf["category"]
        if category not in categories:
            qbittorrent.request("POST", "/torrents/createCategory", {
                "category": category, "savePath": f"/mnt/downloads/{category}",
            }, form=True)
        configure_provider(app, "/downloadclient", "QBittorrent", "qBittorrent", {
            "host": service_host("qbittorrent"),
            "port": 8089,
            "apiKey": key,
            "username": "",
            "password": "",
            conf["categoryField"]: category,
        }, enable=True)
        print(f"{app.name}: qBittorrent client configured")


def configure():
    applications = {name: arr(name, conf["port"], "v3") for name, conf in CONFIG["applications"].items()}
    prowlarr = arr("prowlarr", 9696, "v1")
    for app in (*applications.values(), prowlarr):
        configure_login(app)

    jellyfin_key = jellyfin_api_key()
    for name, app in applications.items():
        configure_library(app, CONFIG["applications"][name]["root"])
        configure_provider(prowlarr, "/applications", name.capitalize(), name.capitalize(), {
            "prowlarrUrl": prowlarr.url,
            "baseUrl": app.url,
            "apiKey": secret(f"{name}-api-key"),
        }, syncLevel="fullSync")
        configure_provider(app, "/notification", "MediaBrowser", "Jellyfin library update", {
            "host": service_host("jellyfin"), "port": 8096, "apiKey": jellyfin_key,
            "notify": False, "updateLibrary": True,
        }, onDownload=True, onUpgrade=True)
    configure_download_clients(applications)
    configure_seerr(applications)
    configure_flaresolverr(prowlarr)
    print("Prowlarr, Sonarr, Radarr, Seerr and Jellyfin are linked.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    READY.unlink(missing_ok=True)
    while True:
        try:
            configure()
            break
        except (RuntimeError, FileNotFoundError, TimeoutError, URLError) as error:
            print(f"Waiting to finish media configuration: {error}", file=sys.stderr)
            time.sleep(12)
    READY.touch()
    print("Media stack configured.")
    while True:
        signal.pause()
