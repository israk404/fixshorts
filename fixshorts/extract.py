"""Reads a Reddit post (title, body, top comments, links) in the app's own browser window.

The browser uses its own profile in data/browser-profile, so your Reddit login is remembered
there and never touches your normal browser. All browser calls must come from one thread.
"""
import re
import time
from urllib.parse import urlparse

from .config import ROOT


class NeedLogin(Exception):
    pass


class ReadError(Exception):
    pass


# Runs inside the page. Handles new Reddit, old Reddit, and falls back to the page text.
_READ_JS = r"""
() => {
  const out = {layout: "text", title: "", body: "", subreddit: "", author: "", comments: [], links: []};
  const seen = new Map();
  const isReddit = h => /(^|\.)(reddit\.com|redd\.it|redditmedia\.com|redditstatic\.com)$/.test(h);
  const addLinks = (el, where) => {
    if (!el) return;
    el.querySelectorAll("a[href]").forEach(a => {
      let u; try { u = new URL(a.href); } catch (e) { return; }
      if (!/^https?:$/.test(u.protocol) || isReddit(u.hostname)) return;
      if (!seen.has(u.href)) seen.set(u.href, {url: u.href, text: (a.innerText || "").trim().slice(0, 120), where});
    });
  };
  const post = document.querySelector("shreddit-post");
  if (post) {
    out.layout = "new";
    out.title = post.getAttribute("post-title") || (document.querySelector("h1") || {}).innerText || "";
    out.subreddit = post.getAttribute("subreddit-prefixed-name") || "";
    out.author = post.getAttribute("author") || "";
    const body = post.querySelector('[slot="text-body"]') || document.querySelector('[property="schema:articleBody"]');
    out.body = body ? body.innerText.trim() : "";
    addLinks(body, "post");
    const ch = post.getAttribute("content-href");
    if (ch) { try { const u = new URL(ch); if (!isReddit(u.hostname)) seen.set(u.href, {url: u.href, text: "link in the post", where: "post"}); } catch (e) {} }
    document.querySelectorAll("shreddit-comment").forEach(c => {
      const el = c.querySelector(':scope > [slot="comment"]') || c.querySelector('[slot="comment"]');
      if (!el) return;
      const text = el.innerText.trim();
      if (!text) return;
      const author = c.getAttribute("author") || "";
      out.comments.push({text: text.slice(0, 2000), score: parseInt(c.getAttribute("score") || "0", 10) || 0,
                         depth: parseInt(c.getAttribute("depth") || "0", 10) || 0, op: !!author && author === out.author});
      addLinks(el, "comment");
    });
  } else if (document.querySelector("#siteTable .thing.link")) {
    out.layout = "old";
    const thing = document.querySelector("#siteTable .thing.link");
    out.title = (thing.querySelector("a.title") || {}).innerText || "";
    out.subreddit = thing.getAttribute("data-subreddit-prefixed") || "";
    out.author = thing.getAttribute("data-author") || "";
    const body = thing.querySelector(".usertext-body .md");
    out.body = body ? body.innerText.trim() : "";
    addLinks(body, "post");
    document.querySelectorAll(".commentarea .comment").forEach(c => {
      const entry = c.querySelector(":scope > .entry");
      if (!entry) return;
      const md = entry.querySelector(".usertext-body .md");
      if (!md) return;
      const scoreEl = entry.querySelector(".score.unvoted");
      let depth = 0, p = c.parentElement;
      while (p) { if (p.classList && p.classList.contains("comment")) depth++; p = p.parentElement; }
      out.comments.push({text: md.innerText.trim().slice(0, 2000),
                         score: parseInt((scoreEl && scoreEl.getAttribute("title")) || "0", 10) || 0,
                         depth, op: !!entry.querySelector(".author.submitter")});
      addLinks(md, "comment");
    });
  }
  if (!out.title) {
    out.title = document.title || "";
    const main = document.querySelector("main") || document.body;
    addLinks(main, "page");
  }
  out.links = Array.from(seen.values()).slice(0, 40);
  out.page_text = (document.body ? document.body.innerText : "").slice(0, 20000);
  out.final_url = location.href;
  return out;
}
"""


def normalize_url(url):
    url = url.strip().strip("<>").split("#")[0]
    if not url:
        raise ReadError("empty link")
    if not re.match(r"^https?://", url):
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    if not (host == "redd.it" or host.endswith("reddit.com")):
        raise ReadError("that isn't a Reddit link")
    return url


class RedditReader:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.pw = None
        self.ctx = None
        self.headless = None

    # ---------- browser ----------

    def _launch(self, headless):
        from playwright.sync_api import sync_playwright

        self.close()
        if self.pw is None:
            self.pw = sync_playwright().start()
        b = self.cfg["browser"]
        profile = ROOT / b["profile"]
        profile.mkdir(parents=True, exist_ok=True)
        tried = []
        for channel in dict.fromkeys([b.get("channel", "msedge"), "msedge", "chrome", None]):
            try:
                self.ctx = self.pw.chromium.launch_persistent_context(
                    str(profile), channel=channel, headless=headless,
                    viewport={"width": 1280, "height": 900},
                    args=["--disable-blink-features=AutomationControlled"],
                )
                self.headless = headless
                return
            except Exception as e:  # browser not installed, profile in use, ...
                tried.append(f"{channel or 'chromium'}: {str(e).splitlines()[0][:120]}")
        raise ReadError("Couldn't open Edge or Chrome. " + " | ".join(tried))

    def ensure(self):
        want_headless = not self.cfg["browser"].get("show", True)
        if self.ctx is None or self.headless != want_headless:
            self._launch(want_headless)

    def close(self):
        if self.ctx is not None:
            try:
                self.ctx.close()
            except Exception:
                pass
            self.ctx = None

    def shutdown(self):
        self.close()
        if self.pw is not None:
            try:
                self.pw.stop()
            except Exception:
                pass
            self.pw = None

    def logged_in(self):
        if self.ctx is None:
            return None
        try:
            return any(c["name"] == "reddit_session" for c in self.ctx.cookies("https://www.reddit.com"))
        except Exception:
            return None

    def check_login(self):
        """Open the profile briefly (no window) to see whether the Reddit login cookie is there."""
        self._launch(headless=True)
        try:
            return bool(self.logged_in())
        finally:
            self.close()

    def login(self, wait_seconds=600, on_status=None):
        """Open a visible window on Reddit's login page and wait until you're logged in."""
        self._launch(headless=False)
        page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        page.goto("https://www.reddit.com/login", wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + wait_seconds
        ok = False
        while time.time() < deadline:
            if self.logged_in():
                ok = True
                break
            if not self.ctx.pages:  # you closed the window
                break
            time.sleep(2)
        if ok and on_status:
            on_status("logged_in")
        time.sleep(2 if ok else 0)
        self.close()
        return ok

    # ---------- reading ----------

    def read(self, url):
        url = normalize_url(url)
        self.ensure()
        page = self.ctx.new_page()
        try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                reason = str(e).splitlines()[0].replace("Page.goto: ", "")
                raise ReadError(f"Couldn't load the page ({reason[:120]}). Check your internet and the link.")
            try:
                page.wait_for_selector("shreddit-post, #siteTable .thing.link", timeout=15000)
            except Exception:
                pass
            if re.search(r"/(account/)?login", page.url):
                raise NeedLogin("Reddit wants you to log in")
            for _ in range(4):  # load a few more comments
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(900)
            data = page.evaluate(_READ_JS)
        finally:
            try:
                page.close()
            except Exception:
                pass

        text = data.get("page_text", "")
        if data["layout"] == "text":
            if re.search(r"log in to (continue|view|see)|sign up to (continue|view)", text, re.I) or len(text) < 300:
                raise NeedLogin("Reddit didn't show the post (log in first)")
        if not data.get("body") and not data.get("comments") and len(text) < 300:
            raise ReadError("the page had no post text or comments")

        comments = sorted(data["comments"], key=lambda c: (c["op"], c["score"]), reverse=True)
        top = sorted(comments, key=lambda c: c["score"], reverse=True)[:22]
        op_replies = [c for c in comments if c["op"] and c not in top][:5]
        data["comments"] = top + op_replies
        data["url"] = url
        if data["layout"] != "text":
            data.pop("page_text", None)
        return data


def post_to_text(post):
    """Format an extracted post for the AI, with numbered links."""
    lines = []
    if post.get("subreddit"):
        lines.append(f"Community: {post['subreddit']}")
    lines.append(f"Title: {post.get('title', '').strip()}")
    lines.append("")
    if post.get("body"):
        lines += [post["body"].strip(), ""]
    if post.get("comments"):
        lines.append("Top replies (most upvoted first, [OP] = the person who asked):")
        for c in post["comments"]:
            tag = "[OP] " if c.get("op") else ""
            text = re.sub(r"\n{2,}", "\n", c["text"].strip())
            lines.append(f"- [{c.get('score', 0)} upvotes] {tag}{text}")
        lines.append("")
    if post.get("page_text"):
        lines += ["Page text (the page layout wasn't recognized, so this is everything visible):",
                  post["page_text"], ""]
    if post.get("links"):
        lines.append("Links found in the post and replies:")
        for i, link in enumerate(post["links"], 1):
            label = f' "{link["text"]}"' if link.get("text") and link["text"] != link["url"] else ""
            lines.append(f"[{i}] {link['url']}{label} (in a {link.get('where', 'reply')})")
    return "\n".join(lines).strip()
