"""FixShorts: turn a tech-fix Reddit post into a YouTube Short and an upload kit.

  python run.py write  input\\my_post.txt      AI writes the script  -> output\\<date>_<topic>\\script.json
  python run.py render output\\<folder>         voice + video + upload kit (run after you review/edit)
  python run.py all    input\\my_post.txt      both steps, no review stop
  python run.py preview output\\<folder>        still frames of each card, to check the look fast
"""
import argparse
import datetime as dt
import json
import shutil
import sys
import time
from pathlib import Path

from fixshorts.config import ROOT, load_config
from fixshorts.schema import Script, problems
from fixshorts import kit

OUTPUT = ROOT / "output"
THEMES = ["cyan", "lime", "amber", "violet"]


def new_job_dir(slug):
    OUTPUT.mkdir(exist_ok=True)
    base = OUTPUT / f"{dt.date.today():%Y-%m-%d}_{slug[:48] or 'untitled'}"
    path, n = base, 2
    while path.exists():
        path = Path(f"{base}-{n}")
        n += 1
    path.mkdir(parents=True)
    return path


def pick_theme(cfg, job_dir):
    name = cfg["video"].get("theme", "auto")
    if name in THEMES:
        return name
    return THEMES[sum(map(ord, job_dir.name)) % len(THEMES)]


def cmd_write(post_path, cfg):
    from fixshorts.writer import post_to_text, write_script

    post_path = Path(post_path)
    raw = post_path.read_text(encoding="utf-8")
    print(f"Writing script for {post_path.name} with {cfg['ai']['model']} ...")
    script = write_script(post_to_text(raw, post_path.name), cfg)
    job = new_job_dir(script.slug if script.verdict == "use" else "rejected-" + script.slug)
    shutil.copy(post_path, job / ("post" + post_path.suffix))
    save_script(job, script)
    if script.verdict == "reject":
        print(f"\nRejected: {script.reject_reason}\nSaved to {job}")
        return None
    print(f"\nReview it: {job / 'script.md'}")
    print(f"Edit if needed: {job / 'script.json'}")
    report(script, cfg)
    print(f"\nThen render:  python run.py render \"{job}\"")
    return job


def save_script(job, script):
    (job / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (job / "script.md").write_text(kit.script_markdown(script), encoding="utf-8")


def report(script, cfg):
    print(f"  confidence: {script.confidence}, words: {script.word_count()}")
    for f in script.risk_flags:
        print(f"  risk: {f}")
    for n in script.review_notes:
        print(f"  note: {n}")
    for p in problems(script, cfg):
        print(f"  RULE: {p}")


def load_job_script(job):
    return Script.model_validate(json.loads((job / "script.json").read_text(encoding="utf-8")))


def narrate(script, cfg, job):
    from fixshorts.voice import Voice

    voice = Voice(cfg)
    narration = voice.narrate(script.segments)
    limit = cfg["video"]["max_seconds"]
    if narration.duration > limit:
        factor = narration.duration / limit
        if factor <= 1.15:
            speed = cfg["voice"]["speed"] * factor
            print(f"  {narration.duration:.1f}s is over {limit}s, re-voicing at speed {speed:.2f}")
            narration = voice.narrate(script.segments, speed=speed)
        else:
            print(f"  WARNING: {narration.duration:.1f}s is well over {limit}s. Shorten the script for best results.")
    (job / "_work").mkdir(exist_ok=True)
    (job / "_work" / "timing.json").write_text(json.dumps(narration.timing_json(), indent=1), encoding="utf-8")
    return narration


def cmd_render(job, cfg):
    from fixshorts.render import render_video

    job = Path(job)
    script = load_job_script(job)
    if script.verdict != "use":
        sys.exit(f"This script was rejected: {script.reject_reason}")
    for p in problems(script, cfg):
        print(f"  note: {p}")
    started = time.time()
    print("Voicing ...")
    narration = narrate(script, cfg, job)
    print(f"  {narration.duration:.1f} seconds of audio")
    theme = pick_theme(cfg, job)
    print(f"Rendering ({theme} theme) ...")
    video = render_video(script, narration, job, cfg, theme)
    (job / "upload.txt").write_text(kit.upload_text(script, narration.duration), encoding="utf-8")
    (job / "script.md").write_text(kit.script_markdown(script, duration=narration.duration), encoding="utf-8")
    print(f"\nDone in {time.time() - started:.0f}s")
    print(f"  video:  {video}")
    print(f"  upload: {job / 'upload.txt'}")


def cmd_preview(job, cfg):
    """Draw one still per card, mid-segment with a caption, without voicing or encoding."""
    from fixshorts import cards
    from fixshorts.render import caption_chunks, label_for
    from fixshorts.voice import Word

    job = Path(job)
    script = load_job_script(job)
    theme = pick_theme(cfg, job)
    t = cards.theme(theme)
    out = job / "preview"
    out.mkdir(exist_ok=True)
    n_fixes, fix_no = len(script.fixes()), 0
    bg = cards.background(theme)
    for i, seg in enumerate(script.segments):
        if seg.kind == "fix":
            fix_no += 1
        img = bg.copy()
        img.alpha_composite(cards.card_layer(seg, label_for(seg, fix_no, n_fixes), script.device, theme, n_fixes))
        cards.channel_mark(img, cfg["video"].get("channel_name", ""), t)
        cards.draw_progress(img, len(script.segments), i, 0.5, t)
        words = [Word(w, 0, 0, i, k == len(seg.narration.split()) - 1) for k, w in enumerate(seg.narration.split())]
        chunk = max(caption_chunks(words), key=lambda c: len(" ".join(x.text for x in c)))
        cap, pos = cards.caption_layer([w.text for w in chunk], min(1, len(chunk) - 1), t)
        img.alpha_composite(cap, dest=pos)
        img.convert("RGB").save(out / f"{i:02d}_{seg.kind}.png")
    print(f"Saved {len(script.segments)} frames to {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["write", "render", "all", "preview"])
    ap.add_argument("path", help="a post .txt/.json file (write, all) or an output folder (render, preview)")
    ap.add_argument("--script", help="use this script.json instead of calling the AI (with 'all')")
    args = ap.parse_args()
    cfg = load_config()

    if args.command == "write":
        cmd_write(args.path, cfg)
    elif args.command == "render":
        cmd_render(args.path, cfg)
    elif args.command == "preview":
        cmd_preview(args.path, cfg)
    elif args.command == "all":
        if args.script:
            script = Script.model_validate(json.loads(Path(args.script).read_text(encoding="utf-8")))
            job = new_job_dir(script.slug)
            shutil.copy(args.path, job / ("post" + Path(args.path).suffix))
            save_script(job, script)
        else:
            job = cmd_write(args.path, cfg)
            if job is None:
                return
        cmd_render(job, cfg)


if __name__ == "__main__":
    main()
