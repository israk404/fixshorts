"""Builds the video: one encoded file per segment, joined, then the voice-over is added."""
import os
import subprocess
from pathlib import Path

from PIL import Image

from . import cards

_ENCODER_CACHE = {}


# ---------- encoder ----------

def pick_encoder(cfg):
    """Intel Quick Sync if it works on this PC, otherwise x264 on the CPU."""
    v = cfg["video"]
    choice = v.get("encoder", "auto")
    if choice in _ENCODER_CACHE:
        return _ENCODER_CACHE[choice]
    x264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-g", "60"]
    qsv = ["-vf", "format=nv12", "-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "22",
           "-g", "60"]
    result = ("x264", x264)
    if choice in ("auto", "qsv"):
        test = [v["ffmpeg"], "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                "-i", f"color=c=black:s={v['width']}x{v['height']}:r={v['fps']}:d=0.3",
                *qsv, "-f", "null", "-"]
        ok = subprocess.run(test, capture_output=True).returncode == 0
        if ok:
            result = ("Intel Quick Sync", qsv)
        elif choice == "qsv":
            print("  Quick Sync isn't available on this PC, using x264 instead")
    _ENCODER_CACHE[choice] = result
    return result


# ---------- timeline ----------

def caption_chunks(words, max_words=3, max_chars=16):
    """Group words into short caption chunks, never across a sentence or segment."""
    chunks, cur = [], []
    for w in words:
        if cur and (w.segment != cur[-1].segment or len(cur) >= max_words
                    or len(" ".join(x.text for x in cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w.sentence_end or w.text.endswith((",", ";", ":")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def scene_bounds(narration, fps):
    """Frame index where each segment's card starts (cut halfway through the pause)."""
    spans = narration.segment_spans
    times = [0.0] + [(spans[i - 1][1] + spans[i][0]) / 2 for i in range(1, len(spans))] + [narration.duration]
    return [round(t * fps) for t in times]


def label_for(seg, fix_no, n_fixes):
    return {
        "hook": "THE PROBLEM",
        "why": "WHY IT HAPPENS",
        "fix": f"FIX {fix_no} OF {n_fixes}",
        "avoid": "AVOID THIS",
        "cta": "YOUR TURN",
    }[seg.kind]


# ---------- rendering ----------

def render_video(script, narration, job_dir: Path, cfg, theme_name, log=print):
    v = cfg["video"]
    fps, ff = v["fps"], v["ffmpeg"]
    work = job_dir / "_work"
    work.mkdir(exist_ok=True)
    enc_name, enc_args = pick_encoder(cfg)
    log(f"  encoder: {enc_name}")

    t = cards.theme(theme_name)
    segs = script.segments
    n_fixes = len(script.fixes())
    bounds = scene_bounds(narration, fps)
    chunks = caption_chunks(narration.words)
    words_by_seg = [[w for w in narration.words if w.segment == i] for i in range(len(segs))]

    # Card layer per segment
    bases, fix_no = [], 0
    bg = cards.background(theme_name)
    for i, seg in enumerate(segs):
        if seg.kind == "fix":
            fix_no += 1
        layer = cards.card_layer(seg, label_for(seg, fix_no, n_fixes), script.device, theme_name, n_fixes)
        base = bg.copy()
        base.alpha_composite(layer)
        cards.channel_mark(base, v.get("channel_name", ""), t)
        bases.append(base)

    cover = bases[0].copy()
    cards.draw_progress(cover, len(segs), 0, 0, t)
    cover.convert("RGB").save(job_dir / "cover.png")

    scene_files = []
    for i in range(len(segs)):
        f0, f1 = bounds[i], bounds[i + 1]
        seg_chunks = [c for c in chunks if c[0].segment == i]
        seg_words = words_by_seg[i]
        name = f"scene_{i:02d}.mp4"
        tmp = work / f"scene_{i:02d}.tmp.mp4"
        cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{v['width']}x{v['height']}", "-r", str(fps),
               "-i", "-", *enc_args, "-an", str(tmp)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        cache = {}
        try:
            for f in range(f0, f1):
                now = f / fps
                spoken = sum(1 for w in seg_words if w.start <= now)
                chunk_i, hi = _active(seg_chunks, now)
                key = (chunk_i, hi, spoken)
                frame = cache.get(key)
                if frame is None:
                    img = bases[i].copy()
                    cards.draw_progress(img, len(segs), i, spoken / max(1, len(seg_words)), t)
                    if chunk_i is not None:
                        cap, pos = cards.caption_layer([w.text for w in seg_chunks[chunk_i]], hi, t)
                        img.alpha_composite(cap, dest=pos)
                    frame = img.convert("RGB").tobytes()
                    cache[key] = frame
                proc.stdin.write(frame)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed on scene {i}: {err.strip()[-800:]}")
        os.replace(tmp, work / name)  # only a finished file gets its real name
        scene_files.append(name)
        log(f"  rendered scene {i + 1}/{len(segs)} ({(f1 - f0) / fps:.1f}s, {len(cache)} unique frames)")

    (work / "scenes.txt").write_text("".join(f"file '{n}'\n" for n in scene_files), encoding="utf-8")
    import soundfile as sf
    sf.write(work / "voice.wav", narration.audio, narration.sample_rate, subtype="PCM_16")

    out_tmp = job_dir / "video.tmp.mp4"
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", "scenes.txt", "-i", "voice.wav",
           "-map", "0:v", "-map", "1:a", "-c:v", "copy",
           "-af", _loudnorm_filter(ff, work / "voice.wav"), "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
           "-movflags", "+faststart", "-shortest", str(out_tmp.resolve())]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed joining scenes: {r.stderr.strip()[-800:]}")
    final = job_dir / "video.mp4"
    os.replace(out_tmp, final)

    if not v.get("keep_work_files", False):
        for p in work.iterdir():
            if p.suffix in (".mp4", ".txt"):
                p.unlink()
    return final


# Light cleanup before loudness: cut rumble, even out the voice, cap peaks so the final gain stays clean
VOICE_CHAIN = ("highpass=f=70,acompressor=threshold=0.1:ratio=4:attack=3:release=100:makeup=2,"
               "alimiter=limit=0.4:attack=2:release=50:level=false")


def _loudnorm_filter(ff, wav, target="I=-14:TP=-1.5:LRA=11"):
    """Two-pass loudness: measure the voice first, then normalize it exactly to YouTube's -14 LUFS."""
    import json
    import re

    r = subprocess.run([ff, "-hide_banner", "-i", str(wav), "-af", f"{VOICE_CHAIN},loudnorm={target}:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr)
    if not m:
        return f"{VOICE_CHAIN},loudnorm={target}"
    s = json.loads(m.group(0))
    return (f"{VOICE_CHAIN},loudnorm={target}:measured_I={s['input_i']}:measured_TP={s['input_tp']}"
            f":measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}"
            f":offset={s['target_offset']}:linear=true")


def _active(seg_chunks, now):
    """Which caption chunk is on screen at `now`, and which of its words is being spoken."""
    current = None
    for ci, c in enumerate(seg_chunks):
        if c[0].start <= now:
            current = ci
        else:
            break
    if current is None:
        return None, -1
    c = seg_chunks[current]
    hi = -1
    for wi, w in enumerate(c):
        if w.start <= now:
            hi = wi
    return current, hi
