"""Jobs: one per pasted link. Two background workers move them along.

  queued -> reading -> writing -> review   (prep worker: browser + AI, runs for every link first)
  review --you approve--> approved -> rendering -> done   (render worker: voice + both videos)
  any step can end in failed; retry puts it back in the queue.
"""
import datetime as dt
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from .config import ROOT, load_config
from .schema import Link, Script, problems, tidy

OUTPUT = ROOT / "output"
THEMES = ["cyan", "lime", "amber", "violet"]
BUSY = ("reading", "writing", "rendering")

LABELS = {
    "queued": "Waiting to read",
    "reading": "Reading the Reddit page",
    "writing": "Writing the script",
    "review": "Ready for your review",
    "skipped": "AI skipped this post",
    "approved": "Approved, waiting to make videos",
    "rendering": "Making the videos",
    "done": "Videos ready",
    "failed": "Something went wrong",
}

FIELDS = ("id", "url", "created", "status", "message", "progress", "folder", "title", "error",
          "cost_usd", "cost_note", "durations", "voice", "theme", "attention")


class Job:
    def __init__(self, **kw):
        self.id = kw.get("id") or uuid.uuid4().hex[:10]
        self.url = kw.get("url", "")
        self.created = kw.get("created") or dt.datetime.now().isoformat(timespec="milliseconds")
        self.status = kw.get("status", "queued")
        self.message = kw.get("message", "")
        self.progress = kw.get("progress", 0.0)
        self.folder = kw.get("folder", "")
        self.title = kw.get("title", "")
        self.error = kw.get("error", "")
        self.cost_usd = kw.get("cost_usd", 0.0)
        self.cost_note = kw.get("cost_note", "")
        self.durations = kw.get("durations", {})
        self.voice = kw.get("voice", "")
        self.theme = kw.get("theme", "")
        self.attention = kw.get("attention", [])

    def to_dict(self):
        return {k: getattr(self, k) for k in FIELDS}


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs = {}
        OUTPUT.mkdir(exist_ok=True)
        for folder in sorted(OUTPUT.iterdir()):
            f = folder / "job.json"
            if not f.exists():
                continue
            try:
                job = Job(**json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
            job.folder = folder.name
            # the app was closed mid-step: put the job back where it can continue
            if job.status in ("reading", "writing"):
                job.status, job.message = "queued", ""
            elif job.status == "rendering":
                job.status, job.message, job.progress = "approved", "", 0.0
            self.jobs[job.id] = job

    def path(self, job):
        return OUTPUT / job.folder

    def save(self, job):
        p = self.path(job)
        p.mkdir(parents=True, exist_ok=True)
        tmp = p / "job.json.tmp"
        tmp.write_text(json.dumps(job.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, p / "job.json")

    def add(self, url):
        with self.lock:
            job = Job(url=url.strip())
            job.folder = f"{dt.date.today():%Y-%m-%d}_job-{job.id[:6]}"
            self.jobs[job.id] = job
            self.save(job)
            return job

    def update(self, job, save=True, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(job, k, v)
            if save:
                self.save(job)

    def rename(self, job, slug):
        """Give the folder a readable name once the topic is known."""
        with self.lock:
            safe = "".join(c if c.isalnum() or c == "-" else "-" for c in slug.lower())[:48].strip("-") or "video"
            new = f"{job.created[:10]}_{safe}_{job.id[:4]}"
            if new != job.folder and not (OUTPUT / new).exists():
                os.replace(self.path(job), OUTPUT / new)
                job.folder = new
                self.save(job)

    def get(self, job_id):
        return self.jobs.get(job_id)

    def all(self):
        with self.lock:
            return sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)

    def next_with(self, status):
        with self.lock:
            waiting = [j for j in self.jobs.values() if j.status == status]
            return min(waiting, key=lambda j: j.created) if waiting else None

    def delete(self, job):
        with self.lock:
            if job.status in BUSY:
                raise ValueError("this job is being worked on right now; wait for it to finish")
            shutil.rmtree(self.path(job), ignore_errors=True)
            self.jobs.pop(job.id, None)

    # ---------- files inside a job folder ----------

    def script(self, job):
        p = self.path(job) / "script.json"
        return Script.model_validate(json.loads(p.read_text(encoding="utf-8"))) if p.exists() else None

    def save_script(self, job, script):
        p = self.path(job) / "script.json"
        p.write_text(script.model_dump_json(indent=2), encoding="utf-8")

    def post(self, job):
        p = self.path(job) / "post.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def attention_points(script, cfg):
    """Short reasons a script deserves a careful look, shown as badges in the app."""
    out = []
    if script.confidence != "high":
        out.append(f"{script.confidence} confidence")
    if script.risk_flags:
        out.append("has risks")
    if any(l.use and l.trust != "trusted" for l in script.links):
        out.append("unverified link")
    if any(l.use and l.status == "broken" for l in script.links):
        out.append("broken link")
    if problems(script, cfg):
        out.append("rule check")
    return out


class Pipeline:
    def __init__(self, store: Store):
        self.store = store
        self.prep_wake = threading.Event()
        self.render_wake = threading.Event()
        self.browser_tasks = queue.Queue()
        self.reddit_state = "unknown"  # unknown, checking, logged_in, logged_out, waiting_login
        self.log_lines = []
        threading.Thread(target=self._prep_loop, daemon=True, name="prep").start()
        threading.Thread(target=self._render_loop, daemon=True, name="render").start()
        self.browser_tasks.put("check")
        self.prep_wake.set()
        self.render_wake.set()

    def log(self, msg):
        line = f"{dt.datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        self.log_lines = (self.log_lines + [line])[-200:]

    # ---------- commands from the app ----------

    def add_links(self, text):
        added, skipped = [], []
        for raw in text.replace(",", "\n").split():
            url = raw.strip()
            if not url:
                continue
            if "reddit.com" not in url and "redd.it" not in url:
                skipped.append(url)
                continue
            added.append(self.store.add(url))
        self.prep_wake.set()
        return added, skipped

    def add_sample(self):
        job = self.store.add("sample")
        self.prep_wake.set()
        return job

    def retry(self, job, reread=False):
        if reread:
            (self.store.path(job) / "post.json").unlink(missing_ok=True)
        self.store.update(job, status="queued", error="", message="", progress=0.0)
        self.prep_wake.set()

    def approve(self, job):
        script = self.store.script(job)
        if script is None or script.verdict != "use":
            raise ValueError("there's no usable script to make videos from")
        self.store.update(job, status="approved", error="", message="", progress=0.0)
        self.render_wake.set()

    def request_login(self):
        self.browser_tasks.put("login")
        self.reddit_state = "waiting_login"
        self.prep_wake.set()

    # ---------- prep worker: browser + AI ----------

    def _prep_loop(self):
        from .extract import RedditReader

        reader, idle_since = None, None
        while True:
            try:
                task = self.browser_tasks.get_nowait()
            except queue.Empty:
                task = None
            cfg = load_config()
            if task:
                reader = reader or RedditReader(cfg, self.log)
                reader.cfg = cfg
                try:
                    if task == "check":
                        self.reddit_state = "checking"
                        self.reddit_state = "logged_in" if reader.check_login() else "logged_out"
                    elif task == "login":
                        self.reddit_state = "waiting_login"
                        ok = reader.login(on_status=lambda s: setattr(self, "reddit_state", s))
                        self.reddit_state = "logged_in" if ok else "logged_out"
                        if ok:  # jobs that only failed because of the login can go again
                            for j in self.store.all():
                                if j.status == "failed" and "log in" in j.error.lower():
                                    self.retry(j)
                except Exception as e:
                    self.reddit_state = "logged_out" if task == "login" else "unknown"
                    self.log(f"Browser: {e}")
                continue

            job = self.store.next_with("queued")
            if job:
                idle_since = None
                if job.url != "sample" and reader is None:
                    reader = RedditReader(cfg, self.log)
                if reader:
                    reader.cfg = cfg
                self._prepare(job, reader, cfg)
                continue

            if reader and reader.ctx is not None:
                idle_since = idle_since or time.time()
                if time.time() - idle_since > 20:
                    reader.close()
                    idle_since = None
            self.prep_wake.wait(timeout=2)
            self.prep_wake.clear()

    def _prepare(self, job, reader, cfg):
        from .extract import NeedLogin, post_to_text
        from .links import check_opens
        from .writer import write_script

        store = self.store
        folder = store.path(job)
        try:
            if job.url == "sample":
                post = {"title": "Laptop Wi-Fi disconnects every 10-15 minutes", "sample": True,
                        "links": [{"url": "https://www.intel.com/content/www/us/en/support/detect.html"}]}
                (folder / "post.json").write_text(json.dumps(post, indent=2), encoding="utf-8")
                store.update(job, status="writing", message="Loading the sample script")
                script = tidy(Script.model_validate(json.loads((ROOT / "input" / "sample_script.json").read_text(encoding="utf-8"))))
                from .writer import finalize_links
                finalize_links(script, {l["url"] for l in post["links"]})
                cost, note = 0.0, "sample, no AI used"
            else:
                post = store.post(job)
                if post is None:
                    store.update(job, status="reading", message="Opening the page in the app's browser", error="")
                    post = reader.read(job.url)
                    (folder / "post.json").write_text(json.dumps(post, indent=2), encoding="utf-8")
                    self.reddit_state = "logged_in" if reader.logged_in() else self.reddit_state
                store.update(job, status="writing", message="Writing the script", title=post.get("title", "")[:120])
                script, meter = write_script(post_to_text(post), cfg,
                                             thread_urls={l["url"] for l in post.get("links", [])},
                                             log=lambda m: store.update(job, message=m))
                cost, note = meter.usd, meter.summary()
                (folder / "script.ai.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

            if script.verdict == "use":
                store.update(job, message="Checking the links")
                for link in script.links:
                    if link.trust != "blocked":
                        link.status = check_opens(link.url)
                        if link.status == "broken" and link.use:
                            link.use = False
                            script.review_notes.append(f"Turned off a link that doesn't open: {link.url}")
            store.save_script(job, script)
            store.rename(job, script.slug if script.verdict == "use" else "skipped-" + script.slug)
            title = (script.upload.titles[0] if script.upload and script.upload.titles else post.get("title", ""))
            status = "review" if script.verdict == "use" else "skipped"
            store.update(job, status=status, title=title[:140], cost_usd=round(job.cost_usd + cost, 5),
                         cost_note=note, attention=attention_points(script, cfg) if status == "review" else [],
                         message=script.reject_reason if status == "skipped" else "", progress=0.0, error="")
            self.log(f"Prepared: {title}")
        except NeedLogin as e:
            self.reddit_state = "logged_out"
            store.update(job, status="failed", message="", error=f"{e}. Open Settings, log in to Reddit, then press Try again.")
        except Exception as e:
            self.log(traceback.format_exc())
            store.update(job, status="failed", message="", error=str(e)[:400])

    # ---------- render worker: voice + videos ----------

    def _render_loop(self):
        while True:
            job = self.store.next_with("approved")
            if job:
                self._render(job)
                continue
            self.render_wake.wait(timeout=3)
            self.render_wake.clear()

    def _render(self, job):
        from . import cards, kit, thumbs
        from .render import pick_encoder, render_video
        from .voice import narrate_with_fallback

        store = self.store
        cfg = load_config()
        folder = store.path(job)
        try:
            script = store.script(job)
            theme = cfg["video"].get("theme", "auto")
            if theme not in THEMES:
                theme = job.theme if job.theme in THEMES else THEMES[sum(map(ord, job.id)) % len(THEMES)]
            store.update(job, status="rendering", progress=0.02, message="Recording the voice", theme=theme, error="")
            enc_name, _ = pick_encoder(cfg)

            long_segs = kit.format_segments(script, "long")
            short_segs = kit.format_segments(script, "short")
            log = lambda m: store.update(job, message=m)
            nar_long, voice_name = narrate_with_fallback(cfg, long_segs, log=log)
            store.update(job, progress=0.08)
            nar_short, _ = narrate_with_fallback(cfg, short_segs, log=log)
            limit = cfg["video"]["max_seconds"]
            if nar_short.duration > limit and nar_short.duration / limit <= 1.15:
                store.update(job, message="Speeding the Short up a little to fit under a minute")
                nar_short, _ = narrate_with_fallback(cfg, short_segs, faster=nar_short.duration / limit, log=log)
            store.update(job, progress=0.15)

            def step(start, span, label):
                return lambda f: store.update(job, save=False, progress=round(start + span * f, 3),
                                              message=f"{label} ({enc_name})")

            render_video(short_segs, script.device, script.icon, nar_short, folder, cfg, theme, cards.SHORT,
                         "short.mp4", progress=step(0.15, 0.4, "Making the Short"), cover_name="cover.jpg")
            render_video(long_segs, script.device, script.icon, nar_long, folder, cfg, theme, cards.LONG,
                         "video.mp4", progress=step(0.55, 0.4, "Making the full video"))
            store.update(job, progress=0.97, message="Making the thumbnail")
            thumbs.make_thumbnail(script, theme, cfg["thumbnail"].get("style", "bold"), folder / "thumbnail.jpg")
            durations = {"short": round(nar_short.duration, 1), "long": round(nar_long.duration, 1)}
            (folder / "upload.txt").write_text(kit.upload_text(script, durations), encoding="utf-8")
            store.update(job, status="done", progress=1.0, message="", durations=durations, voice=voice_name)
            self.log(f"Done: {job.title}")
        except Exception as e:
            self.log(traceback.format_exc())
            store.update(job, status="failed", message="", error=str(e)[:400], progress=0.0)


def open_folder(path: Path):
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606 - opens Explorer on your own output folder
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass
