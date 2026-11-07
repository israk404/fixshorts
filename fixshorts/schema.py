"""The script format the AI must return, plus the rule checks."""
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

Kind = Literal["hook", "why", "fix", "avoid", "cta"]


class Segment(BaseModel):
    kind: Kind
    headline: str
    detail: str = ""
    narration: str


class Upload(BaseModel):
    titles: list[str] = Field(min_length=1)
    description: str
    tags: list[str] = []
    hashtags: list[str] = []
    pinned_comment: str = ""


class Source(BaseModel):
    subreddit: str = ""
    url: str = ""


class Script(BaseModel):
    verdict: Literal["use", "reject"]
    reject_reason: str = ""
    slug: str = "untitled"
    device: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    risk_flags: list[str] = []
    review_notes: list[str] = []
    segments: list[Segment] = []
    upload: Optional[Upload] = None
    source: Source = Source()

    def word_count(self):
        return sum(len(s.narration.split()) for s in self.segments)

    def fixes(self):
        return [s for s in self.segments if s.kind == "fix"]


_USERNAME = re.compile(r"\bu/[A-Za-z0-9_-]+")
_SYMBOLS = re.compile(r"[›/&+()<>|]")


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

    for i, s in enumerate(script.segments, 1):
        limit = 45 if s.kind == "why" else 40
        if len(s.headline) > limit + 8:  # small tolerance, the renderer shrinks text
            out.append(f"segment {i} ({s.kind}) headline is {len(s.headline)} characters; keep it under {limit}")
        if len(s.detail) > 78:
            out.append(f"segment {i} ({s.kind}) detail is {len(s.detail)} characters; keep it under 70")
        if not s.narration.strip():
            out.append(f"segment {i} ({s.kind}) has no narration")
        if _SYMBOLS.search(s.narration):
            out.append(f"segment {i} ({s.kind}) narration contains symbols; write them as spoken words")

    if script.upload is None:
        out.append("upload details are missing")
    else:
        for t in script.upload.titles:
            if len(t) > 100:
                out.append(f"title is over 100 characters: {t[:40]}...")

    text = " ".join([s.headline + " " + s.detail + " " + s.narration for s in script.segments])
    if script.upload:
        text += " " + script.upload.description + " " + script.upload.pinned_comment
    if _USERNAME.search(text):
        out.append("remove Reddit usernames (u/...) from the script and description")
    return out
