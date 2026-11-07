"""Free Microsoft Edge voices (via the edge-tts library), with real word timings for captions.

Needs internet. Each segment is spoken in one request; Edge reports when every word starts
and how long it lasts, so captions line up exactly. Results are cached, so re-rendering the
same text (or the second video format) doesn't ask Edge again.
"""
import asyncio
import hashlib
import json
import re
import subprocess

import numpy as np

from .config import ROOT
from .voice import Narration, Word

SR = 24000
TICKS = 10_000_000  # Edge reports time in 100-nanosecond ticks
CACHE = ROOT / "data" / "tts-cache"

# Used when the voice list can't be downloaded
FALLBACK_VOICES = [
    ("en-US-AndrewNeural", "Andrew (US, male)"), ("en-US-BrianNeural", "Brian (US, male)"),
    ("en-US-ChristopherNeural", "Christopher (US, male)"), ("en-US-GuyNeural", "Guy (US, male)"),
    ("en-US-EricNeural", "Eric (US, male)"), ("en-US-AvaNeural", "Ava (US, female)"),
    ("en-US-EmmaNeural", "Emma (US, female)"), ("en-US-AriaNeural", "Aria (US, female)"),
    ("en-US-JennyNeural", "Jenny (US, female)"), ("en-GB-RyanNeural", "Ryan (UK, male)"),
    ("en-GB-SoniaNeural", "Sonia (UK, female)"), ("en-AU-WilliamNeural", "William (Australia, male)"),
    ("en-IN-PrabhatNeural", "Prabhat (India, male)"), ("en-IN-NeerjaNeural", "Neerja (India, female)"),
]


def _norm(word):
    return re.sub(r"[^a-z0-9]", "", word.lower())


def rate_with(base_rate, faster):
    """'+5%' sped up by a factor, e.g. faster=1.1 -> '+15%'."""
    m = re.match(r"^([+-]?\d+)%$", base_rate.strip())
    pct = int(m.group(1)) if m else 0
    pct += round((faster - 1) * 100)
    pct = max(-50, min(100, pct))
    return f"{pct:+d}%"


async def _stream(text, voice, rate):
    import edge_tts

    audio, events = bytearray(), []
    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    async for chunk in comm.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            start = chunk["offset"] / TICKS
            events.append((chunk["text"], start, start + chunk["duration"] / TICKS))
    if not audio:
        raise RuntimeError("Edge returned no audio")
    return bytes(audio), events


def synthesize(text, voice, rate, ffmpeg="ffmpeg", retries=3):
    """(samples float32 at 24 kHz, [(word, start, end), ...]); cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()
    mp3, meta = CACHE / f"{key}.mp3", CACHE / f"{key}.json"
    if not (mp3.exists() and meta.exists()):
        last = None
        for attempt in range(retries):
            try:
                data, events = asyncio.run(_stream(text, voice, rate))
                mp3.write_bytes(data)
                meta.write_text(json.dumps(events), encoding="utf-8")
                break
            except Exception as e:
                last = e
                import time
                time.sleep(1.5 * (attempt + 1))
        else:
            raise RuntimeError(f"Edge voice didn't answer ({last})")
    events = [tuple(e) for e in json.loads(meta.read_text(encoding="utf-8"))]
    pcm = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(mp3),
                          "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    if pcm.returncode != 0:
        raise RuntimeError(f"couldn't decode Edge audio: {pcm.stderr.decode(errors='replace')[-300:]}")
    return np.frombuffer(pcm.stdout, dtype=np.float32).copy(), events


def align(shown, events, total):
    """Match our words (as shown in captions) to Edge's word events. Returns [(start, end), ...].

    Edge may split a word ("Wi-Fi" -> "Wi", "Fi") or skip punctuation-only words, so this walks
    both lists and joins events until they spell our word. Falls back to an even spread.
    """
    ours = [_norm(w) for w in shown]
    ev = [(_norm(t), a, b) for t, a, b in events if _norm(t)]
    times, j, matched = [], 0, 0
    for word in ours:
        if not word:  # a symbol-only word: give it zero length at the current point
            times.append(None)
            continue
        if j >= len(ev):
            times.append(None)
            continue
        acc, start, end, k = ev[j][0], ev[j][1], ev[j][2], j
        while acc != word and k + 1 < len(ev) and word.startswith(acc) and len(acc) < len(word):
            k += 1
            acc += ev[k][0]
            end = ev[k][2]
        if acc == word or word.startswith(acc) or acc.startswith(word):
            times.append((start, end))
            matched += 1
            j = k + 1
        else:
            # look a little ahead in case Edge skipped or added something
            found = next((m for m in range(j + 1, min(j + 4, len(ev))) if ev[m][0] == word), None)
            if found is not None:
                times.append((ev[found][1], ev[found][2]))
                matched += 1
                j = found + 1
            else:
                times.append(None)

    if not ours or matched < 0.7 * sum(1 for w in ours if w):
        # even spread by letter count over the spoken part
        a = events[0][1] if events else 0.0
        b = events[-1][2] if events else total
        weights = [max(1, len(w)) for w in ours]
        out, cur = [], a
        for wt in weights:
            step = (b - a) * wt / sum(weights)
            out.append((cur, cur + step))
            cur += step
        return out

    # fill gaps from neighbours
    filled, last_end = [], (events[0][1] if events else 0.0)
    for k, t in enumerate(times):
        if t is None:
            nxt = next((x[0] for x in times[k + 1:] if x is not None), last_end)
            filled.append((last_end, max(last_end, nxt)))
        else:
            filled.append(t)
            last_end = t[1]
    return filled


class EdgeVoice:
    name = "Edge"

    def __init__(self, cfg):
        self.cfg = cfg["voice"]
        self.ffmpeg = cfg["video"]["ffmpeg"]
        self.voice = self.cfg.get("edge_voice", "en-US-AndrewNeural")
        self.name = f"Edge ({self.voice})"

    def narrate(self, segments, faster=1.0, log=print) -> Narration:
        rate = rate_with(self.cfg.get("edge_rate", "+0%"), faster)
        chunks, words, spans = [], [], []
        t = 0.0

        def add(samples):
            nonlocal t
            chunks.append(samples)
            t += len(samples) / SR

        add(np.zeros(int(self.cfg["lead_in"] * SR), dtype=np.float32))
        for si, seg in enumerate(segments):
            text = seg.narration.strip()
            audio, events = synthesize(text, self.voice, rate, self.ffmpeg)
            total = len(audio) / SR
            # trim Edge's own leading and trailing silence so our pauses stay consistent
            head = max(0.0, (events[0][1] - 0.04) if events else 0.0)
            tail = min(total, (events[-1][2] + 0.18) if events else total)
            audio = audio[int(head * SR):int(tail * SR)]
            shown = text.split()
            seg_start = t
            for k, (a, b) in enumerate(align(shown, events, total)):
                ends_sentence = bool(re.search(r"[.!?]$", shown[k])) or k == len(shown) - 1
                words.append(Word(shown[k], seg_start + max(0.0, a - head), seg_start + max(0.0, b - head),
                                  si, sentence_end=ends_sentence))
            add(audio)
            spans.append((seg_start, t))
            if si < len(segments) - 1:
                add(np.zeros(int(self.cfg["segment_pause"] * SR), dtype=np.float32))
        add(np.zeros(int(self.cfg["tail"] * SR), dtype=np.float32))

        audio = np.concatenate(chunks)
        peak = float(np.max(np.abs(audio))) or 1.0
        return Narration(audio * (0.89 / peak), SR, words, spans)


def list_voices():
    """English Edge voices as [(id, label)], from Microsoft's list or the built-in fallback."""
    try:
        import edge_tts

        voices = asyncio.run(edge_tts.list_voices())
        out = []
        for v in voices:
            if not v["ShortName"].startswith("en-"):
                continue
            region = v["Locale"].split("-")[-1]
            gender = v.get("Gender", "").lower()
            name = v["ShortName"].split("-")[-1].replace("Neural", "").replace("Multilingual", " multilingual")
            out.append((v["ShortName"], f"{name} ({region}, {gender})"))
        return sorted(out, key=lambda x: (not x[0].startswith("en-US"), x[1])) or FALLBACK_VOICES
    except Exception:
        return FALLBACK_VOICES


def preview(text, voice, rate, ffmpeg="ffmpeg"):
    """MP3 bytes of a short sample, for the Settings screen."""
    synthesize(text, voice, rate, ffmpeg)
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()
    return (CACHE / f"{key}.mp3").read_bytes()
