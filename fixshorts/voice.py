"""Voice-over with Kokoro (runs on CPU), plus a timing for every word so captions stay in sync.

Kokoro's standard model doesn't report word timings, so each sentence is spoken separately
(giving exact sentence boundaries) and its length is split across its words by how many
sounds (phonemes) each word has.
"""
import re
from dataclasses import dataclass, asdict

import numpy as np

from .config import ROOT

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_EDGE_PUNCT = re.compile(r"^[\"'“”‘’(\[]+|[\"'“”‘’)\],.;:!?]+$")
_PHONE_MARKS = re.compile(r"[ˈˌː.,;:!?\"'“”()\-]")
CLAUSE_PAUSE = 0.1  # Kokoro adds about this much at commas


@dataclass
class Word:
    text: str       # as shown in captions
    start: float    # seconds
    end: float
    segment: int    # which script segment it belongs to
    sentence_end: bool = False


@dataclass
class Narration:
    audio: np.ndarray
    sample_rate: int
    words: list
    segment_spans: list  # (speech_start, speech_end) per segment, in seconds

    @property
    def duration(self):
        return len(self.audio) / self.sample_rate

    def timing_json(self):
        return {
            "duration": round(self.duration, 3),
            "segments": [[round(a, 3), round(b, 3)] for a, b in self.segment_spans],
            "words": [{**asdict(w), "start": round(w.start, 3), "end": round(w.end, 3)} for w in self.words],
        }


def _silences(audio, sr, min_len=0.06):
    """Quiet stretches inside a sentence's audio, as (start, end) seconds."""
    win = max(1, int(0.01 * sr))
    env = np.sqrt(np.convolve(audio.astype(np.float64) ** 2, np.ones(win) / win, "same"))
    quiet = env < max(0.012, 0.04 * float(env.max() or 1))
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) / sr >= min_len and start > 0 and i < len(audio):
                out.append((start / sr, i / sr))
            start = None
    return out


def _spread(weights, start, end):
    total = sum(weights) or 1
    out, cur = [], start
    for w in weights:
        step = (end - start) * w / total
        out.append((cur, cur + step))
        cur += step
    return out


def _time_words(shown, weights, audio, sr):
    """Start/end of each word in one sentence. Commas snap to the real pauses Kokoro left."""
    dur = len(audio) / sr
    commas = [k for k, w in enumerate(shown[:-1]) if re.search(r"[,;:]$", w)]

    # First guess: spread the time by weight, with a short pause after each comma
    talk = max(dur - CLAUSE_PAUSE * len(commas), dur * 0.6)
    guess, cur = [], 0.0
    for k, w in enumerate(weights):
        step = talk * w / sum(weights)
        guess.append((cur, cur + step))
        cur += step + (CLAUSE_PAUSE if k in commas else 0)

    # Snap each comma to the nearest real silence, then spread words inside each clause
    gaps, used, cuts = _silences(audio, sr), set(), []
    for k in commas:
        expected = guess[k][1] + CLAUSE_PAUSE / 2
        best = None
        for gi, (a, b) in enumerate(gaps):
            if gi not in used and abs((a + b) / 2 - expected) < 0.6:
                if best is None or abs((a + b) / 2 - expected) < abs(sum(gaps[best]) / 2 - expected):
                    best = gi
        if best is not None and (not cuts or gaps[best][0] > cuts[-1][1]):
            used.add(best)
            cuts.append((k, gaps[best][0], gaps[best][1]))

    times, first, clause_start = [], 0, 0.0
    for k, gap_start, gap_end in cuts + [(len(shown) - 1, dur, dur)]:
        times += _spread(weights[first:k + 1], clause_start, gap_start)
        first, clause_start = k + 1, gap_end
    return times


class KokoroVoice:
    name = "Kokoro (offline)"

    def __init__(self, cfg):
        from kokoro_onnx import Kokoro

        v = cfg["voice"]
        self.cfg = v
        self.pron = cfg.get("pronounce", {})
        self.kokoro = Kokoro(str(ROOT / v["model"]), str(ROOT / v["voices"]))

    def _spoken_form(self, word):
        core = _EDGE_PUNCT.sub("", word)
        if core in self.pron:
            return word.replace(core, self.pron[core])
        return word

    def _word_weights(self, spoken_words):
        """Relative speaking time per word, from its phoneme count (falls back to letter count)."""
        try:
            phon = self.kokoro.tokenizer.phonemize(" ".join(spoken_words), self.cfg["lang"]).split()
        except Exception:
            phon = []
        # A spoken form can be several words ("S S D"), so compare against the expanded list
        expanded = [len(w.split()) for w in spoken_words]
        if len(phon) == sum(expanded):
            weights, i = [], 0
            for n in expanded:
                weights.append(sum(max(1, len(_PHONE_MARKS.sub("", p))) for p in phon[i:i + n]))
                i += n
            return weights
        return [max(2, len(re.sub(r"[^A-Za-z0-9]", "", w))) for w in spoken_words]

    def _speak(self, text, speed):
        samples, sr = self.kokoro.create(
            text, voice=self.cfg["voice"], speed=speed, lang=self.cfg["lang"], trim=True,
        )
        return np.asarray(samples, dtype=np.float32), sr

    def narrate(self, segments, faster=1.0, log=print) -> Narration:
        speed = self.cfg["speed"] * faster
        sr = 24000
        chunks, words, spans = [], [], []
        t = 0.0

        def silence(sec):
            nonlocal t
            chunks.append(np.zeros(int(round(sec * sr)), dtype=np.float32))
            t += len(chunks[-1]) / sr

        silence(self.cfg["lead_in"])
        for si, seg in enumerate(segments):
            sentences = [s for s in _SENTENCE_SPLIT.split(seg.narration.strip()) if s.strip()]
            seg_start = t
            for j, sentence in enumerate(sentences):
                shown = sentence.split()
                spoken = [self._spoken_form(w) for w in shown]
                audio, sr = self._speak(" ".join(spoken), speed)
                dur = len(audio) / sr

                weights = self._word_weights(spoken)
                for k, (start, end) in enumerate(_time_words(shown, weights, audio, sr)):
                    words.append(Word(shown[k], t + start, t + end, si, sentence_end=(k == len(shown) - 1)))

                chunks.append(audio)
                t += dur
                if j < len(sentences) - 1:
                    silence(self.cfg["sentence_pause"])
            spans.append((seg_start, t))
            if si < len(segments) - 1:
                silence(self.cfg["segment_pause"])
        silence(self.cfg["tail"])

        audio = np.concatenate(chunks)
        peak = float(np.max(np.abs(audio))) or 1.0
        audio = audio * (0.89 / peak)  # about -1 dB peak; loudness is evened out at the final mix
        return Narration(audio, sr, words, spans)


def kokoro_available(cfg):
    v = cfg["voice"]
    return (ROOT / v["model"]).exists() and (ROOT / v["voices"]).exists()


def make_voice(cfg):
    """The voice engine chosen in Settings (Edge by default)."""
    if cfg["voice"].get("engine", "edge") == "kokoro":
        if not kokoro_available(cfg):
            raise RuntimeError("The offline voice isn't installed. Run setup_models.py, or pick Edge in Settings.")
        return KokoroVoice(cfg)
    from .tts_edge import EdgeVoice
    return EdgeVoice(cfg)


def narrate_with_fallback(cfg, segments, faster=1.0, log=print):
    """Edge first; if it fails (no internet, service change) use the offline voice when it's installed."""
    voice = make_voice(cfg)
    try:
        return voice.narrate(segments, faster=faster, log=log), voice.name
    except Exception as e:
        if voice.name.startswith("Kokoro") or not kokoro_available(cfg):
            raise RuntimeError(f"{voice.name} failed: {e}") from e
        log(f"Edge voice failed ({str(e)[:120]}), using the offline voice instead")
        backup = KokoroVoice(cfg)
        return backup.narrate(segments, faster=faster, log=log), backup.name
