from __future__ import annotations

import asyncio
import json
import ssl
import time
from datetime import datetime
from urllib.parse import urlencode
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


WMO = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
    61: "Rain", 63: "Rain", 65: "Heavy rain", 71: "Snow", 73: "Snow", 75: "Heavy snow",
    80: "Showers", 81: "Showers", 82: "Heavy showers", 95: "Thunder", 96: "Thunder", 99: "Thunder",
}


def _fetch(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weather_code",
        "forecast_hours": 12,
        "timezone": "auto",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "Asteroidea/0.1"})
    with _urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    hourly = data.get("hourly", {})
    times = hourly.get("time", []) or []
    temps = hourly.get("temperature_2m", []) or []
    codes = hourly.get("weather_code", []) or []

    now = datetime.now()
    start = 0
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
            if dt >= now.replace(minute=0, second=0, microsecond=0):
                start = i
                break
        except Exception:
            continue

    hours = []
    for i in range(start, min(start + 5, len(times))):
        try:
            hh = datetime.fromisoformat(times[i]).strftime("%H:%M")
        except Exception:
            hh = str(times[i])[-5:]
        temp = temps[i] if i < len(temps) else "?"
        code = codes[i] if i < len(codes) else None
        desc = WMO.get(code, "")
        hours.append({"time": hh, "temp": f"{temp}°", "desc": desc})

    current_temp = hours[0]["temp"] if hours else ""
    summary = "Next 5 hours forecast"
    return {"hours": hours, "current_temp": current_temp, "summary": summary}


async def fetch(context):
    pm = getattr(getattr(context, "app", None), "plugin_manager", None)
    settings = pm.get_plugin_settings("weather_home") if pm else {}
    if not settings.get("enabled", True):
        return []

    try:
        lat = float(settings.get("latitude", 41.9028))
        lon = float(settings.get("longitude", 12.4964))
    except Exception:
        lat, lon = 41.9028, 12.4964
    location = str(settings.get("city_label") or "Weather")

    try:
        result = await asyncio.to_thread(_fetch, lat, lon)
    except Exception as exc:
        return [{
            "screen": "main",
            "widget_type": "WeatherCard",
            "id": "weather-next5h",
            "data": {
                "location": location,
                "current_temp": "--",
                "summary": f"Weather unavailable: {exc}",
                "hours": [],
                "source": "Open-Meteo",
            },
        }]

    # Persist per-plugin and shared memory
    mem = context.get_memory()
    mem["last_fetch_ts"] = time.time()
    mem["last_location"] = location
    mem["last_temp"] = result.get("current_temp", "")
    context.save_memory()
    context.set_shared_memory("weather_last", {"location": location, "temp": mem["last_temp"], "ts": mem["last_fetch_ts"]})

    return [{
        "screen": "main",
        "widget_type": "WeatherCard",
        "id": "weather-next5h",
        "data": {
            "location": location,
            "current_temp": result.get("current_temp", ""),
            "summary": result.get("summary", "Next 5 hours"),
            "hours": result.get("hours", []),
            "source": "Open-Meteo (next 5h)",
        },
    }]
