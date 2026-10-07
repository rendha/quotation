"""
quotations/pwa.py
=================

The parts of the PWA that need no Django, so they can be tested on their own:
    manifest(...) ........... what the browser reads to install the app (name, colours, icons, start page)
    precache(...) ........... the few files the service worker keeps for the offline page
    service_worker_source(...) .. the service worker (pwa_files/sw.template.js) with its three placeholders filled in
"""
import json

APP_NAME = "Dehlsen Energy Quotations"
SHORT_NAME = "Dehlsen"
DESCRIPTION = "Solar quotation generator"
THEME_COLOR = "#3B73B9"            # the blue of the header; the browser colours its toolbar with it
BACKGROUND_COLOR = "#f4f7fb"       # the page colour shown while the app opens

# Change this when the offline page, the icons or the service worker change: phones then replace their old copy.
CACHE_VERSION = "1"

ICON_DIR = "quotations/icons/"
ICONS = (                          # file, size, purpose
    ("icon-192.png", "192x192", "any"),
    ("icon-512.png", "512x512", "any"),
    ("icon-maskable-512.png", "512x512", "maskable"),
)


def manifest(static, url):
    """static(path) -> the address of a static file;  url(name) -> the address of a named page."""
    return {
        "id": "/",
        "name": APP_NAME,
        "short_name": SHORT_NAME,
        "description": DESCRIPTION,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": THEME_COLOR,
        "background_color": BACKGROUND_COLOR,
        "lang": "en-IN",
        "dir": "ltr",
        "icons": [{"src": static(ICON_DIR + name), "sizes": size, "type": "image/png", "purpose": purpose} for name, size, purpose in ICONS],
        "shortcuts": [{
            "name": "New quotation",
            "short_name": "New",
            "url": url("create_quotation"),
            "icons": [{"src": static(ICON_DIR + "icon-192.png"), "sizes": "192x192", "type": "image/png"}],
        }],
    }


def precache(static, url):
    """Kept for offline use: only the offline page and the icons.  Pages with quotations are never stored on the phone."""
    return [url("offline"), static(ICON_DIR + "icon-192.png"), static(ICON_DIR + "icon-512.png")]


def service_worker_source(template_text, static, url):
    source = (template_text
              .replace("__VERSION__", CACHE_VERSION)
              .replace("__OFFLINE_URL__", url("offline"))
              .replace("__PRECACHE_JSON__", json.dumps(precache(static, url))))
    assert "__" not in source.replace("__proto__", ""), "a placeholder of the service worker was not replaced"
    return source
