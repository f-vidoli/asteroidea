from __future__ import annotations

import asyncio
import ssl
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen


def _urlopen(req, timeout=10):
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            ctx = ssl.create_default_context()
        except Exception:
            ctx = None
    try:
        if ctx is not None:
            return urlopen(req, timeout=timeout, context=ctx)
        return urlopen(req, timeout=timeout)
    except Exception as e:
        msg = str(e).lower()
        if 'cert' in msg or 'ssl' in msg:
            try:
                return urlopen(req, timeout=timeout, context=ssl._create_unverified_context())
            except Exception:
                pass
        raise


def _clean(text: str | None) -> str:
    if not text:
        return ""
    out = []
    inside = False
    for ch in text:
        if ch == "<":
            inside = True
            continue
        if ch == ">":
            inside = False
            continue
        if not inside:
            out.append(ch)
    return " ".join("".join(out).split())


def _parse_date(text: str | None) -> str:
    if not text:
        return ""
    try:
        dt = parsedate_to_datetime(text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return text[:25]


def _fetch_feed(url: str, max_items: int) -> list[dict]:
    req = Request(url, headers={"User-Agent": "Asteroidea/0.1 (+rss plugin)"})
    with _urlopen(req, timeout=10) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items: list[dict] = []

    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item")[:max_items]:
            title = _clean(item.findtext("title"))
            link = _clean(item.findtext("link"))
            desc = _clean(item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded"))
            pub = _parse_date(item.findtext("pubDate"))
            items.append({"title": title or "Untitled", "summary": desc[:220], "link": link, "date": pub})
        return items

    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns)[:max_items]:
        title = _clean(entry.findtext("a:title", default="", namespaces=ns))
        summary = _clean(entry.findtext("a:summary", default="", namespaces=ns) or entry.findtext("a:content", default="", namespaces=ns))
        link_el = entry.find("a:link[@rel='alternate']", ns) or entry.find("a:link", ns)
        link = (link_el.get("href") if link_el is not None else "") or ""
        updated = _parse_date(entry.findtext("a:updated", default="", namespaces=ns) or entry.findtext("a:published", default="", namespaces=ns))
        items.append({"title": title or "Untitled", "summary": summary[:220], "link": link, "date": updated})
    return items


async def fetch(context):
    pm = getattr(getattr(context, "app", None), "plugin_manager", None)
    settings = pm.get_plugin_settings("rss_feed") if pm else {}
    if not settings.get("enabled", True):
        return []

    url = str(settings.get("feed_url") or "").strip()
    if not url:
        return [{
            "screen": "feed",
            "widget_type": "RssCard",
            "id": "rss-error",
            "data": {
                "title": "RSS feed not configured",
                "summary": "Set a Feed URL in Settings (RSS plugin).",
                "source": "rss_feed",
                "link": "",
            },
        }]
    try:
        max_items = max(1, int(settings.get("max_items", 5)))
    except Exception:
        max_items = 5

    try:
        items = await asyncio.to_thread(_fetch_feed, url, max_items)
    except Exception as exc:
        return [{
            "screen": "feed",
            "widget_type": "RssCard",
            "id": "rss-error",
            "data": {
                "title": "RSS error",
                "summary": str(exc),
                "source": url,
                "link": "",
            },
        }]

    # Persist per-plugin memory (last fetch info) and shared memory (cross-plugin summary)
    mem = context.get_memory()
    mem["last_fetch_ts"] = time.time()
    mem["last_url"] = url
    mem["last_count"] = len(items)
    context.save_memory()
    context.set_shared_memory("rss_last_fetch", {"url": url, "count": len(items), "ts": mem["last_fetch_ts"]})

    if not items:
        return [{
            "screen": "feed",
            "widget_type": "RssCard",
            "id": "rss-empty",
            "data": {
                "title": "No RSS items found",
                "summary": "The feed returned no entries.",
                "source": url,
                "link": "",
            },
        }]

    payloads = []
    for idx, item in enumerate(items):
        src = item.get("date") or url
        link = item.get("link", "") or ""
        title = item.get("title", "Untitled") or "Untitled"
        payloads.append({
            "screen": "feed",
            "widget_type": "RssCard",
            "id": f"rss-{idx}-{link or title}",
            "data": {
                "title": str(title),
                "summary": str(item.get("summary", "") or ""),
                "source": str(src),
                "link": str(link),
            },
        })
    return payloads
