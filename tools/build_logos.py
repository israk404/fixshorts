"""Rebuild assets/logos from the Simple Icons package (CC0). Only needed to add brands.

    npm pack simple-icons && tar xzf simple-icons-*.tgz
    python tools/build_logos.py package

Each logo is saved as a 384px grayscale mask (white = logo); the app colors it at draw time.
Brands Simple Icons doesn't carry (Microsoft, Amazon, Adobe and others removed them) use Tabler's
outline icons from the bundled icon font instead.
"""
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logos"
SIZE = 384

SIMPLE_ICONS = """
google googlechrome gmail youtube android googledrive googlemaps googlephotos googleplay googlecalendar googlemeet
googlepay googlehome googlelens googletranslate googleassistant googleauthenticator googlemessages googletv
apple icloud ios macos appstore applemusic safari appletv applepay
playstation steam epicgames discord whatsapp telegram messenger facebook instagram tiktok x snapchat spotify netflix
zoom threads signal viber pinterest twitch roblox ubisoft battledotnet ea
samsung xiaomi oneplus huawei honor oppo vivo motorola nokia sony lg
intel amd nvidia qualcomm lenovo dell hp asus acer msi razer corsair tplink netgear
linux ubuntu firefox opera brave vivaldi bluetooth roku epson vlcmediaplayer obsstudio dropbox paypal github
cloudflare malwarebytes 7zip virtualbox python bitwarden lastpass 1password
nordvpn expressvpn protonvpn surfshark avast mcafee norton kaspersky bitdefender anydesk teamviewer notion
libreoffice thunderbird duckduckgo garmin fitbit sonos jbl bose philipshue raspberrypi androidauto smartthings ring
""".split()

# slug: (title, tabler glyph name, brand color)
TABLER = {
    "windows": ("Windows", "brand-windows", "0078D4"),
    "microsoftedge": ("Microsoft Edge", "brand-edge", "0078D7"),
    "microsoftoffice": ("Microsoft Office", "brand-office", "D83B01"),
    "microsoftteams": ("Microsoft Teams", "brand-teams", "6264A7"),
    "onedrive": ("OneDrive", "brand-onedrive", "0078D4"),
    "xbox": ("Xbox", "brand-xbox", "107C10"),
    "skype": ("Skype", "brand-skype", "00AFF0"),
    "bing": ("Bing", "brand-bing", "008373"),
    "amazon": ("Amazon", "brand-amazon", "FF9900"),
    "adobe": ("Adobe", "brand-adobe", "FF0000"),
    "nintendoswitch": ("Nintendo Switch", "device-nintendo", "E60012"),
    "chatgpt": ("ChatGPT", "brand-openai", "74AA9C"),
    "minecraft": ("Minecraft", "brand-minecraft", "62B47A"),
}


def main(package_dir):
    from PIL import Image
    from playwright.sync_api import sync_playwright

    package = Path(package_dir)
    meta = {i["slug"]: i for i in json.loads((package / "data" / "simple-icons.json").read_text(encoding="utf-8"))}
    OUT.mkdir(parents=True, exist_ok=True)
    index = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": SIZE, "height": SIZE})
        for slug in SIMPLE_ICONS:
            svg_file = package / "icons" / f"{slug}.svg"
            if slug not in meta or not svg_file.exists():
                print("missing:", slug)
                continue
            svg = svg_file.read_text(encoding="utf-8").replace("<svg ", f'<svg width="{SIZE}" height="{SIZE}" fill="#000" ', 1)
            page.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
            png = page.locator("svg").screenshot(omit_background=True)
            alpha = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")
            alpha.save(OUT / f"{slug}.png", optimize=True)
            index[slug] = {"title": meta[slug]["title"], "hex": meta[slug]["hex"], "source": "simple-icons"}
        browser.close()
    for slug, (title, glyph, hex_) in TABLER.items():
        index[slug] = {"title": title, "hex": hex_, "source": "tabler", "glyph": glyph}
    (ROOT / "assets" / "logos.json").write_text(json.dumps(dict(sorted(index.items())), indent=1), encoding="utf-8")
    print(f"{len(index)} logos")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "package")
