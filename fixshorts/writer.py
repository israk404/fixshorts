"""Turns a pasted Reddit post into a script, using any OpenAI-compatible AI API (DeepSeek by default)."""
import datetime as dt
import json
import os
import re

from .config import ROOT
from .schema import Script, problems

PROMPTS = ROOT / "prompts"


def post_to_text(raw: str, filename: str = "") -> str:
    """Accept either pasted text or a JSON capture (title/body/comments) and return plain text."""
    if filename.lower().endswith(".json"):
        data = json.loads(raw)
        lines = []
        if data.get("subreddit"):
            lines.append(f"Subreddit: {data['subreddit']}")
        if data.get("url"):
            lines.append(f"URL: {data['url']}")
        lines.append(f"Title: {data.get('title', '')}")
        lines.append("")
        lines.append(data.get("body", ""))
        lines.append("")
        lines.append("Top comments:")
        for c in data.get("comments", []):
            score = c.get("score", "?")
            lines.append(f"[{score} upvotes] {c.get('text', '').strip()}")
        return "\n".join(lines)
    return raw


def build_messages(post_text, cfg):
    style = (PROMPTS / "style_guide.md").read_text(encoding="utf-8")
    task = (PROMPTS / "script_prompt.md").read_text(encoding="utf-8")
    task = task.replace("{{MIN_WORDS}}", str(cfg["script"]["min_words"]))
    task = task.replace("{{MAX_WORDS}}", str(cfg["script"]["max_words"]))
    return [
        {"role": "system", "content": style + "\n\n" + task},
        {"role": "user", "content": "Here is the post and its top comments:\n\n<post>\n" + post_text.strip()
                                    + "\n</post>\n\nReply with the json object only."},
    ]


def extract_json(text: str):
    """Pull the JSON object out of a reply, even if it is wrapped in ``` fences or chatter."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def make_client(cfg):
    from openai import OpenAI  # imported here so rendering works without it

    ai = cfg["ai"]
    key = os.environ.get(ai["api_key_env"], "").strip()
    if not key:
        raise SystemExit(
            f"No API key found. Put this line in a file called .env next to run.py:\n"
            f"  {ai['api_key_env']}=your-key-here"
        )
    return OpenAI(api_key=key, base_url=ai["base_url"], timeout=300)


# ---------- cost tracking ----------

def is_peak(cfg, now=None):
    """DeepSeek-style peak window: weekdays, within the configured UTC hours."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.weekday() > 4:
        return False
    return any(a <= now.hour < b for a, b in cfg["ai"].get("peak_hours_utc", []))


def peak_note(cfg):
    """One line for the console when the current time is in the expensive window, else ''."""
    hours = cfg["ai"].get("peak_hours_utc", [])
    if not hours or not is_peak(cfg):
        return ""
    now = dt.datetime.now(dt.timezone.utc)
    end = next(b for a, b in hours if a <= now.hour < b)
    cheap_at = now.replace(hour=end, minute=0, second=0, microsecond=0).astimezone()
    mult = cfg["ai"].get("peak_multiplier", 2)
    return f"  note: peak pricing now ({mult:g}x). Cheaper again at {cheap_at:%H:%M} your time."


class CostMeter:
    def __init__(self, cfg):
        self.prices = cfg["ai"].get("prices", {})
        self.mult = cfg["ai"].get("peak_multiplier", 1) if is_peak(cfg) else 1
        self.usd, self.known = 0.0, True
        self.tokens = {"in": 0, "cached": 0, "out": 0, "thinking": 0}

    def add(self, model, usage):
        if usage is None:
            return
        u = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
        prompt = u.get("prompt_tokens") or 0
        hit = u.get("prompt_cache_hit_tokens") or 0
        miss = u.get("prompt_cache_miss_tokens")
        if miss is None:
            miss = prompt - hit
        out = u.get("completion_tokens") or 0
        thinking = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        self.tokens["in"] += prompt
        self.tokens["cached"] += hit
        self.tokens["out"] += out
        self.tokens["thinking"] += thinking
        p = self.prices.get(model)
        if not p:
            self.known = False
            return
        self.usd += self.mult * (hit * p["cache_hit"] + miss * p["cache_miss"] + out * p["output"]) / 1e6

    def summary(self):
        t = self.tokens
        line = f"{t['in']:,} tokens in ({t['cached']:,} cached), {t['out']:,} out"
        if t["thinking"]:
            line += f" (of which {t['thinking']:,} thinking)"
        if self.known and self.prices:
            line += f", about ${self.usd:.4f}" + (" at peak rates" if self.mult > 1 else "")
        return line


# ---------- the writer ----------

def _request(client, cfg, model, messages, json_mode):
    ai = cfg["ai"]
    kwargs = dict(model=model, messages=messages, max_tokens=ai.get("max_tokens", 12000))
    if "temperature" in ai:
        kwargs["temperature"] = ai["temperature"]
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if ai.get("reasoning_effort"):
        kwargs["extra_body"] = {"reasoning_effort": ai["reasoning_effort"]}
    return client.chat.completions.create(**kwargs)


def write_script(post_text: str, cfg, client=None, log=print) -> Script:
    ai = cfg["ai"]
    client = client or make_client(cfg)
    messages = build_messages(post_text, cfg)
    json_mode = ai.get("json_mode", True)
    meter = CostMeter(cfg)
    note = peak_note(cfg)
    if note:
        log(note)
    best, best_issues = None, None
    has_draft = False  # the cheaper repair model only edits an existing draft, never writes the first one

    for attempt in range(1, ai.get("max_attempts", 3) + 1):
        model = ai["repair_model"] if has_draft and ai.get("repair_model") else ai["model"]
        try:
            resp = _request(client, cfg, model, messages, json_mode)
        except Exception as e:  # some providers reject response_format; retry without it once
            if json_mode and "response_format" in str(e):
                json_mode = False
                resp = _request(client, cfg, model, messages, json_mode)
            else:
                raise
        meter.add(model, getattr(resp, "usage", None))
        choice = resp.choices[0]
        text = choice.message.content or ""

        if not text.strip():
            # DeepSeek's JSON mode can return blank content; just ask again
            reason = "cut off (raise max_tokens in config.toml)" if choice.finish_reason == "length" else "blank"
            log(f"  attempt {attempt} ({model}): reply was {reason}, asking again")
            continue

        try:
            script = Script.model_validate(extract_json(text))
            issues = problems(script, cfg)
        except Exception as e:
            script, issues = None, [f"the reply was not valid JSON in the required shape ({e})"]

        if script and not issues:
            log(f"  script ready (attempt {attempt}, {model}, {script.word_count()} words)")
            log(f"  {meter.summary()}")
            return script
        if script and (best is None or len(issues) < len(best_issues)):
            best, best_issues = script, issues
        log(f"  attempt {attempt} ({model}): {len(issues)} problem(s), asking the AI to fix them")
        has_draft = True
        messages = messages + [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "Fix these problems and return the complete corrected json object only:\n- "
                                        + "\n- ".join(issues)},
        ]

    log(f"  {meter.summary()}")
    if best is None:
        raise RuntimeError("The AI never returned a usable script. Try again, or try another model in config.toml.")
    best.review_notes = best.review_notes + [f"RULE CHECK: {p}" for p in best_issues]
    log(f"  script saved with {len(best_issues)} unresolved problem(s); see review notes")
    return best
