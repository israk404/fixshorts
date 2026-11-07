"""A permanent record of every Reddit post the app has used, so the same post is never made twice.

Posts are matched by Reddit's post ID, so www., old., mobile, redd.it, share links (once opened)
and links to a single comment all count as the same post. Deleting a job keeps its record.
"""
import datetime as dt
import json
import os
import re
import threading
from urllib.parse import urlparse

from .config import ROOT

FILE = ROOT / "data" / "history.json"
_POST_ID = re.compile(r"/comments/([a-z0-9]{4,12})(?:/|$)", re.I)


def post_key(url):
    """Reddit's post ID for a link, or None (for share links, until the page is opened)."""
    if not url:
        return None
    try:
        p = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if host == "redd.it":
        first = p.path.strip("/").split("/")[0]
        return first.lower() if re.fullmatch(r"[a-z0-9]{4,12}", first, re.I) else None
    if host != "reddit.com" and not host.endswith(".reddit.com"):
        return None
    m = _POST_ID.search(p.path)
    return m.group(1).lower() if m else None


class History:
    def __init__(self):
        self.lock = threading.RLock()
        self.data = {}
        if FILE.exists():
            try:
                self.data = json.loads(FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.data = {}

    def _save(self):
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, FILE)

    def get(self, key):
        return self.data.get(key) if key else None

    def remember(self, key, url, job_id, title="", when=None):
        if not key:
            return
        with self.lock:
            entry = self.data.setdefault(key, {
                "url": url, "added": when or dt.datetime.now().isoformat(timespec="seconds"),
                "title": "", "jobs": [],
            })
            if job_id and job_id not in entry["jobs"]:
                entry["jobs"].append(job_id)
            if title:
                entry["title"] = title[:140]
            self._save()

    def describe(self, key):
        """'Nov 8, 2026: Laptop Wi-Fi keeps dropping' for messages."""
        e = self.get(key)
        if not e:
            return ""
        try:
            day = dt.datetime.fromisoformat(e["added"]).strftime("%b %-d, %Y") if os.name != "nt" else \
                dt.datetime.fromisoformat(e["added"]).strftime("%b %#d, %Y")
        except ValueError:
            day = e["added"][:10]
        return f"{day}: {e['title']}" if e.get("title") else day
