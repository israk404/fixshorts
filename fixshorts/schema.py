"""The script format the AI must return, plus the rule checks."""
import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .config import ROOT

Kind = Literal["hook", "why", "fix", "avoid", "cta"]
LINK_TOKEN = "{LINK}"
ICONS = json.loads((ROOT / "assets" / "icons.json").read_text(encoding="utf-8"))


class Segment(BaseModel):
    kind: Kind
    headline: str
    detail: str = ""
    narration: str


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
    thumbnail_text: str = ""
    icon: str = "tool"
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
_SYMBOLS = re.compile(r"[›/&+()<>|]")
# Anything that gives away the source or sounds machine-written
SOURCE_WORDS = re.compile(r"\b(reddit|redditors?|subreddit|r/\w+|upvot\w*|downvot\w*|the poster|original poster|"
                          r"\bOP\b|commenters?|in the comments of|this thread|a thread|people online)\b", re.I)
AI_PHRASES = re.compile(r"\b(as an ai|artificial intelligence|language model|chatgpt|delve|game[- ]changer|"
                        r"unlock the|seamless(ly)?|let's dive|dive in|in today's video|hey guys|smash that|"
                        r"without further ado|look no further|ultimate guide|hack(s)?\b)", re.I)


def problems(script: Script, cfg) -> list[str]:
    """Return rule violations. An empty list means the script is good to go."""
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

    for i, s in enumerate(script.segments, 1):
        limit = 45 if s.kind == "why" else 40
        if len(s.headline) > limit + 8:  # small tolerance, the renderer shrinks text
            out.append(f"segment {i} ({s.kind}) headline is {len(s.headline)} characters; keep it under {limit}")
        if len(s.detail) > 78:
            out.append(f"segment {i} ({s.kind}) detail is {len(s.detail)} characters; keep it under 70")
        if not s.narration.strip():
            out.append(f"segment {i} ({s.kind}) has no narration")
        if _SYMBOLS.search(s.narration.replace(LINK_TOKEN, "")):
            out.append(f"segment {i} ({s.kind}) narration contains symbols; write them as spoken words")

    if len(script.thumbnail_text) > 28:
        out.append(f"thumbnail_text is {len(script.thumbnail_text)} characters; keep it under 28")
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
    return out


def tidy(script: Script) -> Script:
    """Small automatic fixes that don't need the AI: unknown icon, stray hashtags."""
    if script.icon not in ICONS:
        script.icon = "tool"
    if script.upload:
        tags = [h if h.startswith("#") else "#" + h for h in script.upload.hashtags]
        script.upload.hashtags = [h for h in tags if h.lower() != "#shorts"][:4]
    script.thumbnail_text = script.thumbnail_text.strip()
    return script
