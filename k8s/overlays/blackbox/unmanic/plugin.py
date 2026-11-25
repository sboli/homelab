import hashlib
import json
import logging
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile


LOG = logging.getLogger("Unmanic.homelab_x265")
MIN_AGE = 86400
MAX_INPUT_SIZE = 24 * 1024 ** 3
MIN_SAVINGS_PERCENT = 15
STATE = Path("/config/.unmanic/userdata/homelab_x265")


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-show_chapters", "-of", "json", str(path)],
        check=True, capture_output=True, timeout=30,
    )
    return json.loads(result.stdout)


def fingerprint(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Source must be a regular file with one link")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def reject_marker(path, source_state):
    identity = repr((str(path), source_state, "crf21-medium"))
    return STATE / hashlib.sha256(identity.encode()).hexdigest()


def eligible(path, source_state):
    if path.suffix.lower() not in {".mkv", ".mp4"}:
        return False
    _, _, size, modified, _ = source_state
    if size > MAX_INPUT_SIZE or time.time() - modified / 10 ** 9 < MIN_AGE:
        return False
    if reject_marker(path, source_state).exists():
        return False
    media = probe(path)
    videos = [stream for stream in media["streams"] if stream["codec_type"] == "video"]
    if len(videos) != 1:
        return False
    video = videos[0]
    if (video.get("codec_name"), video.get("pix_fmt"), video.get("field_order")) != ("h264", "yuv420p", "progressive"):
        return False
    if video.get("color_transfer") not in (None, "unknown", "bt709", "smpte170m", "bt470bg", "gamma22", "gamma28"):
        return False
    if any("2020" in video.get(key, "") for key in ("color_primaries", "color_space")):
        return False
    if any(key in item.get("side_data_type", "").lower() for item in video.get("side_data_list", [])
           for key in ("dv", "dolby", "hdr", "mastering", "light level", "display matrix")):
        return False
    width, height = video["width"], video["height"]
    if not (640 <= width <= 1920 and height <= 1080):
        return False
    duration = float(media["format"].get("duration", 0))
    bit_rate = 8 * size / duration if duration > 0 else 0
    return bit_rate >= max(1_600_000, 3_000_000 * width * height / (1920 * 1080))


def ffmpeg_args(source, output):
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-xerror", "-n", "-i", str(source),
        "-map", "0", "-map_metadata", "0", "-map_chapters", "0", "-c", "copy",
        "-c:v:0", "libx265", "-preset", "medium", "-crf", "21",
        "-x265-params", "pools=2:frame-threads=2", "-pix_fmt", "yuv420p", "-fps_mode:v:0", "passthrough",
    ]
    if source.suffix.lower() == ".mp4":
        args.extend(["-tag:v:0", "hvc1", "-movflags", "+faststart"])
    return [*args, str(output)]


def valid_output(original, output):
    before, after = probe(original), probe(output)
    if len(before["streams"]) != len(after["streams"]) or len(before["chapters"]) != len(after["chapters"]):
        return False
    if abs(float(before["format"]["duration"]) - float(after["format"]["duration"])) > 0.5:
        return False
    for old, new in zip(before["streams"], after["streams"]):
        if old["codec_type"] != new["codec_type"]:
            return False
        if old.get("tags", {}).get("language", "und") != new.get("tags", {}).get("language", "und"):
            return False
        if old["codec_type"] == "video":
            if new["codec_name"] != "hevc" or any(old[k] != new[k] for k in ("width", "height", "pix_fmt")):
                return False
        elif old.get("codec_name") != new.get("codec_name"):
            return False
    return True


def on_library_management_file_test(data):
    path = Path(data["path"])
    try:
        data["add_file_to_pending_tasks"] = eligible(path, fingerprint(path))
    except (OSError, ValueError, subprocess.SubprocessError):
        data["add_file_to_pending_tasks"] = False


def on_worker_process(data, task_data_store=None):
    source = Path(data["file_in"])
    source_state = fingerprint(source)
    if not eligible(source, source_state):
        raise ValueError("Source no longer matches the x265 profile")
    task_data_store.set_task_state("source_state", source_state)
    data["exec_command"] = ffmpeg_args(source, Path(data["file_out"]))


def on_postprocessor_file_movement(data, task_data_store=None):
    # Always suppress Unmanic's default unlink-then-rename workflow.
    data["run_default_file_copy"] = False
    data["remove_source_file"] = False
    source = Path(data["source_data"]["abspath"])
    output = Path(data["file_in"])
    source_state = task_data_store.get_task_state("source_state")
    if not source_state or fingerprint(source) != source_state:
        LOG.warning("Kept source because it changed: %s", source)
        return

    if output.stat().st_size * 100 > source_state[2] * (100 - MIN_SAVINGS_PERCENT):
        STATE.mkdir(parents=True, exist_ok=True)
        reject_marker(source, source_state).touch()
        LOG.info("Kept source because savings were below %d%%: %s", MIN_SAVINGS_PERCENT, source)
        return
    if not valid_output(source, output):
        LOG.warning("Kept source because output streams or duration did not match: %s", source)
        return

    temporary = None
    try:
        with NamedTemporaryFile(prefix=".unmanic-", suffix=".part", dir=source.parent, delete=False) as staged:
            temporary = Path(staged.name)
            with output.open("rb") as encoded:
                shutil.copyfileobj(encoded, staged)
            staged.flush()
            shutil.copystat(source, temporary)
            os.fsync(staged.fileno())
        if temporary.stat().st_size != output.stat().st_size or fingerprint(source) != source_state:
            raise OSError("Source changed or staged output size differed")
        os.replace(temporary, source)
        LOG.info("Replaced verified source with x265 output: %s", source)
    except OSError:
        LOG.exception("Could not replace source: %s", source)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
