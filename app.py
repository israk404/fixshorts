"""FixShorts app: double-click start.bat (or run `python app.py`) and it opens in your browser."""
import json
import os
import threading
import urllib.request
import webbrowser
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from fixshorts import kit
from fixshorts.config import ROOT, editable_view, load_config, save_settings, set_env_value
from fixshorts.jobs import BUSY, LABELS, Pipeline, Store, attention_points, open_folder
from fixshorts.links import check_opens, classify
from fixshorts.schema import ICONS, PROBLEM_ICONS, Script, problems, tidy

WEB = ROOT / "web"
app = FastAPI(title="FixShorts")
store = Store()
pipeline = Pipeline(store)
_voice_cache = {}
_balance_cache = {"t": 0, "value": None}

STAGES = ["Read", "Write", "Review", "Videos", "Done"]
STAGE_OF = {"queued": 0, "reading": 0, "duplicate": 0, "writing": 1, "review": 2, "skipped": 2,
            "approved": 3, "rendering": 3, "done": 4, "failed": None}
FILES = ("short.mp4", "video.mp4", "thumbnail.jpg", "cover.jpg", "upload.txt")


def _job_or_404(job_id):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "That job doesn't exist anymore.")
    return job


def _summary(job):
    stage = STAGE_OF.get(job.status)
    if stage is None:  # failed: show where it stopped
        has_script = (store.path(job) / "script.json").exists()
        has_post = (store.path(job) / "post.json").exists()
        stage = 3 if has_script else (1 if has_post else 0)
    return {
        "id": job.id, "url": job.url, "status": job.status, "label": LABELS.get(job.status, job.status),
        "message": job.message, "progress": job.progress, "title": job.title, "created": job.created,
        "error": job.error, "cost_usd": job.cost_usd, "attention": job.attention, "stage": stage,
        "failed": job.status == "failed", "sample": job.url == "sample",
    }


def _files(job):
    p = store.path(job)
    return {name: int((p / name).stat().st_mtime) for name in FILES if (p / name).exists()}


# ---------- pages and assets ----------

@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/assets/{name}")
def asset(name: str):
    allowed = {"tabler-icons.ttf": ROOT / "assets" / "fonts" / "tabler-icons.ttf",
               "icons.json": ROOT / "assets" / "icons.json",
               "logos.json": ROOT / "assets" / "logos.json"}
    if name not in allowed:
        raise HTTPException(404)
    return FileResponse(allowed[name])


@app.get("/api/logo/{slug}")
def logo_png(slug: str):
    """A brand logo in its own color, sized for the review screen."""
    import io
    from fixshorts.cards import LOGOS, brand_color, logo_image

    if slug not in LOGOS:
        raise HTTPException(404)
    img = logo_image(slug, 96, brand_color(slug, (255, 255, 255)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@app.get("/files/{job_id}/{name}")
def job_file(job_id: str, name: str):
    job = _job_or_404(job_id)
    path = store.path(job) / name
    if name not in FILES or not path.exists():
        raise HTTPException(404, "That file isn't ready yet.")
    return FileResponse(path, headers={"Cache-Control": "no-store"})


# ---------- jobs ----------

@app.get("/api/state")
def state():
    from fixshorts.writer import peak_status

    jobs = [_summary(j) for j in store.all()]
    return {"jobs": jobs, "reddit": pipeline.reddit_state, "peak_until": peak_status(load_config()),
            "ready": sum(1 for j in jobs if j["status"] == "review")}


@app.post("/api/links")
def add_links(body: dict = Body(...)):
    added, skipped, repeats = pipeline.add_links(body.get("text", ""), bool(body.get("allow_repeats")))
    return {"added": [j.id for j in added], "skipped": skipped, "repeats": repeats}


@app.post("/api/sample")
def add_sample():
    return {"id": pipeline.add_sample().id}


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    job = _job_or_404(job_id)
    cfg = load_config()
    script = store.script(job)
    post = store.post(job) or {}
    out = {**_summary(job), "files": _files(job), "durations": job.durations, "voice": job.voice,
           "cost_note": job.cost_note, "folder": job.folder,
           "post": {"title": post.get("title", ""), "subreddit": post.get("subreddit", ""),
                    "comments": len(post.get("comments", [])), "links": len(post.get("links", [])),
                    "layout": post.get("layout", ""), "sample": bool(post.get("sample"))}}
    if script:
        out["script"] = json.loads(script.model_dump_json())
        out["problems"] = problems(script, cfg)
        out["words"] = script.word_count()
        out["upload"] = kit.upload_fields(script) if script.upload else None
    return out


@app.put("/api/jobs/{job_id}/script")
def save_script(job_id: str, body: dict = Body(...)):
    job = _job_or_404(job_id)
    if job.status in BUSY:
        raise HTTPException(409, "Wait until this step finishes before editing.")
    cfg = load_config()
    old = store.script(job)
    try:
        script = tidy(Script.model_validate(body))
    except Exception as e:
        raise HTTPException(400, f"Couldn't save: {e}")
    old_links = {l.url: l for l in (old.links if old else [])}
    for link in script.links:
        link.url = link.url.strip()
        prev = old_links.get(link.url)
        if prev:
            link.source, link.trust, link.trust_reason, link.status = prev.source, prev.trust, prev.trust_reason, prev.status
        else:  # a link you added
            link.source = "you"
            link.trust, link.trust_reason = classify(link.url)
            link.status = check_opens(link.url, timeout=6) if link.trust != "blocked" else "unchecked"
        if link.trust == "blocked":
            link.use = False
    script.links = [l for l in script.links if l.url]
    store.save_script(job, script)
    title = kit.title(script)
    store.update(job, title=title[:140], attention=attention_points(script, cfg))
    return {"problems": problems(script, cfg), "words": script.word_count(),
            "upload": kit.upload_fields(script) if script.upload else None,
            "links": json.loads(script.model_dump_json())["links"], "attention": job.attention}


@app.post("/api/jobs/{job_id}/approve")
def approve(job_id: str):
    job = _job_or_404(job_id)
    if job.status not in ("review", "done", "failed"):
        raise HTTPException(409, "This job isn't waiting for approval.")
    try:
        pipeline.approve(job)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/approve-all")
def approve_all():
    n = 0
    for job in store.all():
        if job.status == "review":
            try:
                pipeline.approve(job)
                n += 1
            except ValueError:
                pass
    return {"approved": n}


@app.post("/api/jobs/{job_id}/retry")
def retry(job_id: str, body: dict = Body(default={})):
    job = _job_or_404(job_id)
    if job.status in BUSY:
        raise HTTPException(409, "This job is already being worked on.")
    script = store.script(job)
    if job.status == "duplicate":
        pipeline.retry(job, allow_repeat=True)  # you chose to make it anyway
    elif job.status == "failed" and script is not None and not body.get("rewrite"):
        pipeline.approve(job)  # it failed while making videos: just try the videos again
    else:
        pipeline.retry(job, reread=bool(body.get("reread")))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/edit")
def back_to_review(job_id: str):
    job = _job_or_404(job_id)
    if job.status in BUSY:
        raise HTTPException(409, "Wait until this step finishes.")
    store.update(job, status="review", message="")
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def delete(job_id: str):
    job = _job_or_404(job_id)
    try:
        store.delete(job)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/open")
def open_job_folder(job_id: str):
    open_folder(store.path(_job_or_404(job_id)))
    return {"ok": True}


# ---------- settings, voice, Reddit, balance ----------

@app.get("/api/settings")
def get_settings():
    from fixshorts.voice import kokoro_available
    from fixshorts.writer import api_key

    cfg = load_config()
    key = api_key(cfg)
    return {
        "values": editable_view(cfg),
        "key_set": bool(key), "key_hint": f"…{key[-4:]}" if len(key) > 8 else "",
        "kokoro_available": kokoro_available(cfg),
        "models": [{"id": m, "price": p} for m, p in cfg["ai"].get("prices", {}).items()],
        "icons": PROBLEM_ICONS,
    }


@app.post("/api/settings")
def post_settings(body: dict = Body(...)):
    save_settings(body.get("changes", {}))
    if "browser.show" in body.get("changes", {}) or "browser.channel" in body.get("changes", {}):
        pipeline.browser_tasks.put("check")
        pipeline.prep_wake.set()
    return {"values": editable_view(load_config())}


@app.post("/api/key")
def post_key(body: dict = Body(...)):
    key = (body.get("key") or "").strip()
    if len(key) < 10:
        raise HTTPException(400, "That doesn't look like an API key.")
    set_env_value(load_config()["ai"]["api_key_env"], key)
    _balance_cache["t"] = 0
    return {"ok": True}


@app.get("/api/voices")
def voices():
    if "edge" not in _voice_cache:
        from fixshorts.tts_edge import list_voices
        _voice_cache["edge"] = list_voices()
    return {"edge": [{"id": v, "label": label} for v, label in _voice_cache["edge"]],
            "kokoro": ["am_michael", "am_adam", "am_eric", "am_liam", "am_onyx", "af_heart", "af_bella",
                       "af_nicole", "af_sarah", "bm_george", "bm_lewis", "bf_emma", "bf_isabella"]}


@app.post("/api/voice-preview")
def voice_preview(body: dict = Body(...)):
    cfg = load_config()
    text = "Your laptop's Wi-Fi keeps dropping? Here's how to fix it in under a minute."
    try:
        if body.get("engine", "edge") == "kokoro":
            import io
            import soundfile as sf
            from fixshorts.voice import KokoroVoice
            cfg["voice"]["voice"] = body.get("voice") or cfg["voice"]["voice"]
            cfg["voice"]["speed"] = float(body.get("speed") or cfg["voice"]["speed"])
            audio, sr = KokoroVoice(cfg)._speak(text, cfg["voice"]["speed"])
            buf = io.BytesIO()
            sf.write(buf, audio, sr, format="WAV")
            return Response(buf.getvalue(), media_type="audio/wav")
        from fixshorts.tts_edge import preview
        data = preview(text, body.get("voice") or cfg["voice"]["edge_voice"],
                       body.get("rate") or cfg["voice"]["edge_rate"], cfg["video"]["ffmpeg"])
        return Response(data, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(502, f"Couldn't play the voice: {str(e)[:200]}")


@app.get("/api/thumb-preview/{style}")
def thumb_preview(style: str, theme: str = "cyan"):
    from fixshorts.thumbs import STYLES, make_thumbnail
    if style not in STYLES:
        raise HTTPException(404)
    out = ROOT / "data" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"thumb-{style}-{theme}.jpg"
    if not path.exists():
        sample = Script.model_validate(json.loads((ROOT / "input" / "sample_script.json").read_text(encoding="utf-8")))
        make_thumbnail(sample, theme, style, path)
    return FileResponse(path)


@app.post("/api/reddit/login")
def reddit_login():
    pipeline.request_login()
    return {"state": pipeline.reddit_state}


@app.post("/api/reddit/check")
def reddit_check():
    pipeline.browser_tasks.put("check")
    pipeline.prep_wake.set()
    return {"state": pipeline.reddit_state}


@app.get("/api/balance")
def balance():
    import time
    from fixshorts.writer import api_key

    if time.time() - _balance_cache["t"] < 60:
        return _balance_cache["value"] or {"available": None}
    cfg = load_config()
    key = api_key(cfg)
    value = {"available": None}
    if key and "deepseek" in cfg["ai"]["base_url"]:
        try:
            req = urllib.request.Request(cfg["ai"]["base_url"].rstrip("/") + "/user/balance",
                                         headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
            infos = data.get("balance_infos") or []
            usd = next((i for i in infos if i.get("currency") == "USD"), infos[0] if infos else None)
            if usd:
                value = {"available": bool(data.get("is_available")), "amount": usd.get("total_balance"),
                         "currency": usd.get("currency")}
        except Exception as e:
            value = {"available": None, "error": str(e)[:120]}
    _balance_cache.update(t=time.time(), value=value)
    return value


@app.exception_handler(HTTPException)
def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn

    cfg = load_config()
    port = int(cfg.get("app", {}).get("port", 8765))
    url = f"http://127.0.0.1:{port}"
    print(f"FixShorts is running at {url}  (keep this window open; close it to stop)")
    if cfg.get("app", {}).get("open_browser", True) and not os.environ.get("FIXSHORTS_NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
