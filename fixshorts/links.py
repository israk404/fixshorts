"""Decide which links are safe to put in a description, and check that they open."""
import ipaddress
import urllib.error
import urllib.request
from urllib.parse import urlparse

# Official makers and long-standing, reputable software sites
TRUSTED = {
    "microsoft.com", "windows.com", "live.com", "office.com", "xbox.com", "bing.com",
    "apple.com", "icloud.com", "google.com", "android.com", "chrome.com", "youtube.com", "gstatic.com",
    "samsung.com", "intel.com", "amd.com", "nvidia.com", "realtek.com", "qualcomm.com", "mediatek.com",
    "lenovo.com", "dell.com", "hp.com", "asus.com", "acer.com", "msi.com", "gigabyte.com", "asrock.com",
    "logitech.com", "logi.com", "razer.com", "corsair.com", "steelseries.com", "hyperx.com",
    "tp-link.com", "netgear.com", "linksys.com", "ubiquiti.com", "ui.com", "eero.com",
    "xiaomi.com", "mi.com", "oneplus.com", "motorola.com", "huawei.com", "honor.com", "oppo.com", "vivo.com",
    "sony.com", "lg.com", "canon.com", "epson.com", "brother.com", "hp.com",
    "crucial.com", "westerndigital.com", "seagate.com", "kingston.com", "sandisk.com", "synology.com",
    "github.com", "githubusercontent.com", "mozilla.org", "firefox.com", "videolan.org", "7-zip.org",
    "malwarebytes.com", "ninite.com", "wikipedia.org", "cpuid.com", "rufus.ie", "ventoy.net",
    "obsproject.com", "libreoffice.org", "notepad-plus-plus.org", "python.org", "memtest.org",
    "crystalmark.info", "hwinfo.com", "nirsoft.net", "adobe.com", "zoom.us", "spotify.com",
    "steampowered.com", "discord.com", "whatsapp.com", "telegram.org", "opera.com", "brave.com",
    "vivaldi.com", "dropbox.com", "ubuntu.com", "debian.org", "archlinux.org", "raspberrypi.com",
    "bleepingcomputer.com", "speedtest.net", "fast.com", "cloudflare.com", "1.1.1.1", "quad9.net",
}
SHORTENERS = {"bit.ly", "tinyurl.com", "goo.gl", "t.co", "cutt.ly", "is.gd", "ow.ly", "shorturl.at",
              "rb.gy", "tiny.cc", "buff.ly", "rebrand.ly", "adf.ly", "shorte.st", "linktr.ee"}
FILE_TYPES = (".exe", ".msi", ".zip", ".rar", ".7z", ".apk", ".dmg", ".iso", ".bat", ".cmd", ".scr", ".jar")
BAD_WORDS = ("crack", "keygen", "warez", "torrent", "pirat", "serial-key", "activator", "kms")


def _domain_matches(host, domains):
    return any(host == d or host.endswith("." + d) for d in domains)


def classify(url):
    """Return (trust, reason): trust is 'trusted', 'check' or 'blocked'."""
    try:
        p = urlparse(url)
    except ValueError:
        return "blocked", "not a valid link"
    host = (p.hostname or "").lower()
    if p.scheme not in ("http", "https") or not host:
        return "blocked", "not a web link"
    try:
        ipaddress.ip_address(host)
        if host not in ("1.1.1.1",):
            return "blocked", "raw IP address"
    except ValueError:
        pass
    if _domain_matches(host, SHORTENERS):
        return "blocked", "link shortener hides where it goes"
    lowered = url.lower()
    if any(w in lowered for w in BAD_WORDS):
        return "blocked", "looks like piracy or cracked software"
    trusted = _domain_matches(host, TRUSTED)
    if p.path.lower().endswith(FILE_TYPES) and not trusted:
        return "blocked", "direct file download from an unknown site"
    if trusted:
        return "trusted", "official or well-known site"
    if p.scheme == "http":
        return "check", "unknown site without https"
    return "check", "unknown site: open it and check before using"


def check_opens(url, timeout=8):
    """'ok' if the page answers, 'broken' if it's gone, 'unknown' if the site blocks checks."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status < 400:
                    return "ok"
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "broken"
            if e.code in (405, 501) and method == "HEAD":
                continue
            return "unknown"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = str(getattr(e, "reason", e)).lower()
            if "name or service" in reason or "getaddrinfo" in reason or "nodename" in reason:
                return "broken"
            return "unknown"
    return "unknown"
