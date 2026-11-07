"""The script format the AI must return, plus the rule checks."""
import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .config import ROOT

Kind = Literal["hook", "why", "fix", "avoid", "cta"]
LINK_TOKEN = "{LINK}"
ICONS = json.loads((ROOT / "assets" / "icons.json").read_text(encoding="utf-8"))
LOGOS = json.loads((ROOT / "assets" / "logos.json").read_text(encoding="utf-8"))
# problem icons the AI may pick (brand glyphs are only used as logo fallbacks)
PROBLEM_ICONS = sorted(n for n in ICONS if not n.startswith("brand-") and n != "device-nintendo")


class Segment(BaseModel):
    kind: Kind
    headline: str
    detail: str = ""
    narration: str
    logo: str = ""                # optional brand logo for this step (a fix that uses a brand's tool)


class Link(BaseModel):
    url: str
    label: str = ""
    use: bool = True
    reason: str = ""
    source: str = "thread"        # thread (found in the post/replies) or ai (suggested by the AI)
    trust: str = "check"          # trusted, check or blocked (set by the app)
    trust_reason: str = ""
    status: str = "unchecked"     # ok, broken, unknown or unchecked (set by the app)


class Upload(BaseModel):
    titles: list[str] = Field(min_length=1)
    description: str
    tags: list[str] = []
    hashtags: list[str] = []
    pinned_comment: str = ""


class Script(BaseModel):
    verdict: Literal["use", "reject"]
    reject_reason: str = ""
    slug: str = "untitled"
    device: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    risk_flags: list[str] = []
    review_notes: list[str] = []
    error_text: str = ""          # exact error code or message, copied character for character ("" if none)
    search_phrase: str = ""       # the problem in the words people search, e.g. "Wi-Fi keeps disconnecting"
    thumbnail_text: str = ""
    icon: str = "tool"
    logo: str = ""                # brand the problem is about, from assets/logos.json, or ""
    segments: list[Segment] = []
    links: list[Link] = []
    upload: Optional[Upload] = None
    title_choice: int = 0         # which title you picked in the app

    def word_count(self):
        text = " ".join(s.narration for s in self.segments)
        return len(text.replace(LINK_TOKEN, "The link is in the description.").split())

    def fixes(self):
        return [s for s in self.segments if s.kind == "fix"]

    def used_links(self):
        return [l for l in self.links if l.use and l.trust != "blocked"]


_USERNAME = re.compile(r"\bu/[A-Za-z0-9_-]+")
_SYMBOLS = re.compile(r"[›/&+()<>|_]")
# Anything that gives away the source or sounds machine-written
SOURCE_WORDS = re.compile(r"\b(reddit|redditors?|subreddit|r/\w+|upvot\w*|downvot\w*|the poster|original poster|"
                          r"\bOP\b|commenters?|in the comments of|this thread|a thread|people online)\b", re.I)
AI_PHRASES = re.compile(r"\b(as an ai|artificial intelligence|language model|chatgpt|delve|game[- ]changer|"
                        r"unlock the|seamless(ly)?|let's dive|dive in|in today's video|hey guys|smash that|"
                        r"without further ado|look no further|ultimate guide|hack(s)?\b)", re.I)


def _norm(text):
    """For comparing against the source: lower case, straight quotes, single spaces."""
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(text.lower().split())


_CODE_PATTERNS = [
    re.compile(r"\b0x[0-9A-Fa-f]{4,8}\b"),                       # 0x80070005
    re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+){2,}\b"),           # DRIVER_IRQL_NOT_LESS_OR_EQUAL
    re.compile(r"\b(?:ERR|NET|DNS|SSL)_[A-Z_]{4,}\b"),              # ERR_CONNECTION_TIMED_OUT
    re.compile(r"\b(?:error|code)\s*[:#]?\s*\d{2,6}\b", re.I),        # error 651, Code 43
]


def error_candidates(text, limit=5):
    """Things in the post that look like error codes, so the AI can be pointed at the real one."""
    found = []
    for pat in _CODE_PATTERNS:
        for m in pat.finditer(text):
            value = m.group(1) if m.groups() else m.group(0)
            if value not in found:
                found.append(value)
    return found[:limit]


def problem_word_rules(script: Script, source_text=None) -> list[str]:
    """The exact error (or the search words) must survive into titles, thumbnail, first card and description."""
    out = []
    err = script.error_text.strip().strip('"').strip("'")
    phrase = script.search_phrase.strip()
    hook = next((s for s in script.segments if s.kind == "hook"), None)
    titles = script.upload.titles if script.upload else []
    first_line = (script.upload.description.strip().splitlines() or [""])[0] if script.upload else ""
    if err:
        if source_text is not None and _norm(err) not in _norm(source_text):
            found = error_candidates(source_text)
            hint = f" The post contains: {', '.join(found)}." if found else ""
            return [f'error_text "{err}" is not in the post; copy the error exactly as the post writes it, '
                    f"character for character, and use that same text in the headline, titles, thumbnail and "
                    f"description.{hint}"]
        if hook and err not in hook.headline and err not in hook.detail:
            out.append(f'the hook headline (or its detail) must contain the exact error "{err}"')
        missing = [t for t in titles if err not in t]
        if missing:
            out.append(f'every title must contain the exact error "{err}" unchanged (missing in {len(missing)})')
        if err.lower() not in script.thumbnail_text.lower():
            out.append(f'thumbnail_text must contain the exact error "{err}"')
        if err not in first_line:
            out.append(f'the first line of the description must contain the exact error "{err}"')
    elif phrase:
        low = phrase.lower()
        if hook and low not in (hook.headline + " " + hook.detail).lower():
            out.append(f'the hook headline must contain the problem words "{phrase}"')
        if titles and sum(low in t.lower() for t in titles) < 2:
            out.append(f'at least 2 titles must contain the problem words "{phrase}"')
        if len(phrase) <= 28 and low not in script.thumbnail_text.lower():
            out.append(f'thumbnail_text must contain the problem words "{phrase}"')
    else:
        out.append("fill error_text (exact error) or search_phrase (the problem in search words)")
    return out


def problems(script: Script, cfg, source_text=None) -> list[str]:
    """Return rule violations. An empty list means the script is good to go.

    `source_text` (the post as given to the AI) lets the check confirm the exact error is really in it."""
    if script.verdict == "reject":
        return [] if script.reject_reason.strip() else ["verdict is reject but reject_reason is empty"]

    out = []
    kinds = [s.kind for s in script.segments]
    if not kinds or kinds[0] != "hook" or kinds.count("hook") != 1:
        out.append("the first segment must be the only 'hook'")
    if not kinds or kinds[-1] != "cta" or kinds.count("cta") != 1:
        out.append("the last segment must be the only 'cta'")
    if not 1 <= kinds.count("fix") <= 3:
        out.append(f"there must be 1 to 3 'fix' segments, found {kinds.count('fix')}")
    if kinds.count("why") > 1 or kinds.count("avoid") > 1:
        out.append("use at most one 'why' and at most one 'avoid' segment")
    order = {"hook": 0, "why": 1, "fix": 2, "avoid": 3, "cta": 4}
    if [order[k] for k in kinds] != sorted(order[k] for k in kinds):
        out.append("segments must be in the order hook, why, fix, avoid, cta")

    lo, hi = cfg["script"]["min_words"], cfg["script"]["max_words"]
    n = script.word_count()
    if not lo <= n <= hi:
        out.append(f"total narration is {n} words; it must be {lo} to {hi} words")

    uses_token = any(LINK_TOKEN in s.narration for s in script.segments)
    if uses_token and not script.used_links():
        out.append(f"narration uses {LINK_TOKEN} but no link has use=true")

    err = script.error_text.strip()
    for i, s in enumerate(script.segments, 1):
        limit = 45 if s.kind == "why" else 40
        if err and err in s.headline:
            limit += len(err)  # an exact error can make the headline long; the renderer shrinks it
        if len(s.headline) > limit + 8:  # small tolerance, the renderer shrinks text
            out.append(f"segment {i} ({s.kind}) headline is {len(s.headline)} characters; keep it under {limit}")
        if len(s.detail) > 78:
            out.append(f"segment {i} ({s.kind}) detail is {len(s.detail)} characters; keep it under 70")
        if not s.narration.strip():
            out.append(f"segment {i} ({s.kind}) has no narration")
        if _SYMBOLS.search(s.narration.replace(LINK_TOKEN, "")):
            out.append(f"segment {i} ({s.kind}) narration contains symbols; write them as spoken words")

    thumb_limit = 28 + (len(err) if err and err.lower() in script.thumbnail_text.lower() else 0)
    if len(script.thumbnail_text) > min(thumb_limit, 56):
        out.append(f"thumbnail_text is {len(script.thumbnail_text)} characters; keep it under {min(thumb_limit, 56)}")
    if not script.thumbnail_text.strip():
        out.append("thumbnail_text is empty")

    if script.upload is None:
        out.append("upload details are missing")
    else:
        for t in script.upload.titles:
            if len(t) > 100:
                out.append(f"title is over 100 characters: {t[:40]}...")

    spoken = " ".join(s.narration for s in script.segments)
    shown = " ".join(s.headline + " " + s.detail for s in script.segments) + " " + script.thumbnail_text
    meta = ""
    if script.upload:
        meta = " ".join(script.upload.titles) + " " + script.upload.description + " " + script.upload.pinned_comment
    everything = f"{spoken} {shown} {meta}"
    if _USERNAME.search(everything):
        out.append("remove usernames (u/...)")
    m = SOURCE_WORDS.search(everything)
    if m:
        out.append(f"remove any mention of where the fix came from (found \"{m.group(0)}\"); give the fixes as direct advice")
    m = AI_PHRASES.search(everything)
    if m:
        out.append(f"rewrite in plain words, avoid \"{m.group(0)}\"")
    out += problem_word_rules(script, source_text)
    return out


def tidy(script: Script) -> Script:
    """Small automatic fixes that don't need the AI: unknown icon, stray hashtags."""
    if script.icon not in ICONS:
        script.icon = "tool"
    script.logo = script.logo.strip().lower() if script.logo else ""
    if script.logo not in LOGOS:
        script.logo = ""
    for seg in script.segments:
        seg.logo = (seg.logo or "").strip().lower()
        if seg.logo not in LOGOS or seg.kind != "fix":
            seg.logo = ""
    if script.upload:
        tags = [h if h.startswith("#") else "#" + h for h in script.upload.hashtags]
        script.upload.hashtags = [h for h in tags if h.lower() != "#shorts"][:4]
    script.thumbnail_text = script.thumbnail_text.strip()
    script.error_text = script.error_text.strip().strip('"').strip("'").strip()
    script.search_phrase = script.search_phrase.strip()
    if script.upload:
        # the exact error and search words lead the tags, since that's what people type
        lead = [t for t in (script.error_text, script.search_phrase) if t]
        rest = [t for t in script.upload.tags if t.lower() not in {x.lower() for x in lead}]
        script.upload.tags = lead + rest
    return script
