"""Settings: config.toml holds the defaults, settings.json holds what you changed in the app."""
import copy
import json
import os
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "settings.json"
ENV_FILE = ROOT / ".env"

# Settings the app's Settings screen may change: "section.key" -> allowed type
EDITABLE = {
    "ai.model": str, "ai.reasoning_effort": str,
    "script.min_words": int, "script.max_words": int,
    "browser.channel": str, "browser.show": bool,
    "voice.engine": str, "voice.edge_voice": str, "voice.edge_rate": str,
    "voice.voice": str, "voice.speed": float,
    "video.theme": str, "video.channel_name": str,
    "thumbnail.style": str,
}


def load_config(path=None):
    path = Path(path) if path else ROOT / "config.toml"
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    for dotted, value in load_settings().items():
        section, key = dotted.split(".", 1)
        cfg.setdefault(section, {})[key] = value
    _load_dotenv(ENV_FILE)
    cfg["video"]["ffmpeg"] = find_ffmpeg(cfg["video"].get("ffmpeg", "ffmpeg"))
    return cfg


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in data.items() if k in EDITABLE}


def save_settings(changes: dict):
    """Validate and merge changed settings into settings.json. Returns the saved dict."""
    current = load_settings()
    for dotted, value in changes.items():
        kind = EDITABLE.get(dotted)
        if kind is None:
            continue
        current[dotted] = kind(value) if kind is not bool else bool(value)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def editable_view(cfg):
    """The current value of every editable setting, for the Settings screen."""
    return {d: cfg.get(d.split(".")[0], {}).get(d.split(".", 1)[1]) for d in EDITABLE}


def _load_dotenv(path):
    """Read KEY=value lines from .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def set_env_value(key, value):
    """Write KEY=value into .env (replacing an existing line) and the running environment."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    out, done = [], False
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"# {key}="):
            if not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ[key] = value


def find_ffmpeg(configured):
    """Use the configured ffmpeg, else PATH, else the folder winget installs to."""
    if configured and configured != "ffmpeg" and Path(configured).exists():
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        link = Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if link.exists():
            return str(link)
        packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if packages.exists():
            for exe in packages.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
                return str(exe)
    return configured or "ffmpeg"


def deep_copy(cfg):
    return copy.deepcopy(cfg)
