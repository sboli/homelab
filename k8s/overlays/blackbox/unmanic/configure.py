import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from unmanic.config import Config
from unmanic.libs.library import Library
from unmanic.libs.plugins import PluginsHandler
from unmanic.libs.unmodels import Libraries, WorkerGroups
from unmanic.service import init_db


plugin = {
    "id": "homelab_x265",
    "name": "Homelab x265",
    "description": "Encode eligible H.264 videos and replace them atomically after verification.",
    "author": "Homelab",
    "version": "1.0.0",
    "tags": "video,hevc",
    "icon": "",
    "compatibility": [2],
    "priorities": {
        "on_library_management_file_test": 0,
        "on_worker_process": 0,
        "on_postprocessor_file_movement": 0,
    },
}

enable_scans = os.environ["UNMANIC_ENABLE_SCANS"] == "true"
settings = Config()
settings.set_bulk_config_items({
    "library_path": "/media/movies",
    "enable_library_scanner": enable_scans,
    "run_full_scan_on_start": enable_scans,
    "schedule_full_scan_minutes": 1440,
    "follow_symlinks": False,
    "concurrent_file_testers": 1,
    "clear_pending_tasks_on_restart": True,
    "auto_manage_completed_tasks": True,
}, save_settings=True)
database = init_db(settings.get_config_path())

try:
    with TemporaryDirectory() as staging:
        archive = Path(staging) / "plugin.zip"
        with ZipFile(archive, "w") as files:
            files.writestr("info.json", json.dumps(plugin))
            files.write("/desired/plugin.py", "plugin.py")
        if not PluginsHandler().install_plugin_from_path_on_disk(archive):
            raise RuntimeError("Unmanic plugin installation failed")

    for library_id, name, path in ((1, "Movies", "/media/movies"), (2, "TV Shows", "/media/tv_shows")):
        record, _ = Libraries.get_or_create(id=library_id, defaults={"name": name, "path": path})
        record.name = name
        record.path = path
        record.enable_scanner = enable_scans
        record.enable_inotify = False
        record.save()
        Library(library_id).set_enabled_plugins([{"plugin_id": plugin["id"]}])

    workers, _ = WorkerGroups.get_or_create(id=1, defaults={"name": "x265", "number_of_workers": 0})
    workers.number_of_workers = 1
    workers.save()
finally:
    database.obj.stop()
    database.close()
