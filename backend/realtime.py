"""
SIFRA:MIND — Real-Time Awareness Module.

Gives Sifra always-on access to:
  - Exact current time + date + day in IST
  - Live Delhi weather (Open-Meteo, no API key needed)
  - Top Indian news headlines (NewsAPI, uses existing key)
  - DuckDuckGo quick-answer for anything factual

All results are cached in-process for 5 minutes so they never
slow down a response. Each external call has a hard 3s timeout.
Graceful degradation: if any source is down, it returns None — never breaks.
"""

import logging
import time as _time
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IST offset
# ---------------------------------------------------------------------------
_IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Simple 5-minute in-process cache
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, object]] = {}  # key → (timestamp, value)
_CACHE_TTL = 300  # seconds


def _cached(key: str, fetcher, *args, **kwargs):
    now = _time.monotonic()
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts < _CACHE_TTL:
            return val
    try:
        val = fetcher(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[realtime] {key} fetch failed: {e}")
        val = None
    _CACHE[key] = (now, val)
    return val


# ---------------------------------------------------------------------------
# Time / Date
# ---------------------------------------------------------------------------

def get_time_info() -> dict:
    """Always accurate — no network call needed."""
    now = datetime.now(_IST)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    hour = now.hour
    minute = now.minute
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12

    if 5 <= hour < 12:
        period = "morning"
    elif 12 <= hour < 17:
        period = "afternoon"
    elif 17 <= hour < 21:
        period = "evening"
    elif 21 <= hour < 24:
        period = "late evening"
    else:
        period = "late night"

    return {
        "time_str": f"{hour12}:{minute:02d} {ampm} IST",
        "date_str": f"{days[now.weekday()]}, {now.day} {months[now.month - 1]} {now.year}",
        "day": days[now.weekday()],
        "hour": hour,
        "period": period,
    }


# ---------------------------------------------------------------------------
# Live Weather — Delhi (Open-Meteo, completely free, no API key)
# ---------------------------------------------------------------------------

_DELHI_LAT = 28.6139
_DELHI_LON = 77.2090
_WMO_CODES = {
    0: "clear sky ☀️", 1: "mainly clear 🌤️", 2: "partly cloudy ⛅", 3: "overcast ☁️",
    45: "foggy 🌫️", 48: "icy fog 🌫️",
    51: "light drizzle 🌦️", 53: "drizzle 🌦️", 55: "heavy drizzle 🌧️",
    61: "light rain 🌧️", 63: "rain 🌧️", 65: "heavy rain 🌧️",
    71: "light snow 🌨️", 73: "snow 🌨️", 75: "heavy snow ❄️",
    80: "rain showers 🌦️", 81: "heavy showers 🌧️", 82: "violent showers ⛈️",
    95: "thunderstorm ⛈️", 96: "thunderstorm with hail ⛈️", 99: "severe thunderstorm ⛈️",
}


def _fetch_weather() -> Optional[str]:
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": _DELHI_LAT,
            "longitude": _DELHI_LON,
            "current": "temperature_2m,apparent_temperature,weathercode,relative_humidity_2m",
            "timezone": "Asia/Kolkata",
        },
        timeout=3,
    )
    if resp.status_code != 200:
        return None
    curr = resp.json().get("current", {})
    temp = curr.get("temperature_2m")
    feels = curr.get("apparent_temperature")
    code = curr.get("weathercode", 0)
    humidity = curr.get("relative_humidity_2m")
    desc = _WMO_CODES.get(code, "clear")
    if temp is None:
        return None
    return (
        f"{desc}, {temp:.0f}°C (feels like {feels:.0f}°C), "
        f"humidity {humidity}% — Delhi"
    )


def get_weather() -> Optional[str]:
    return _cached("weather", _fetch_weather)


# ---------------------------------------------------------------------------
# Live Indian News — top 2 headlines (NewsAPI)
# ---------------------------------------------------------------------------

def _fetch_news_headlines(api_key: str) -> Optional[str]:
    resp = requests.get(
        "https://newsapi.org/v2/top-headlines",
        params={"country": "in", "pageSize": 5, "apiKey": api_key},
        timeout=3,
    )
    if resp.status_code != 200:
        return None
    articles = resp.json().get("articles", [])
    headlines = []
    for a in articles[:2]:
        title = (a.get("title") or "").split(" - ")[0].strip()
        if title:
            headlines.append(title)
    return " | ".join(headlines) if headlines else None


def get_news(api_key: Optional[str] = None) -> Optional[str]:
    if not api_key:
        return None
    return _cached("news", _fetch_news_headlines, api_key)


# ---------------------------------------------------------------------------
# DuckDuckGo Instant Answer — quick factual lookups
# ---------------------------------------------------------------------------

def _fetch_ddg_instant(query: str) -> Optional[str]:
    resp = requests.get(
        "https://api.duckduckgo.com/",
        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        timeout=3,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    abstract = data.get("AbstractText", "")
    answer = data.get("Answer", "")
    return (answer or abstract or None)


def quick_answer(query: str) -> Optional[str]:
    """Non-cached — for one-off factual lookups during a conversation."""
    try:
        return _fetch_ddg_instant(query)
    except Exception as e:
        logger.warning(f"[realtime] quick_answer failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Master Context Builder — called once per response in brain.py
# ---------------------------------------------------------------------------

def get_realtime_context(news_api_key: Optional[str] = None) -> dict:
    """
    Returns a dict with all live context.
    Never raises — always returns at minimum time/date.

    Keys:
        time_str, date_str, day, hour, period  — always present
        weather                                  — str or None
        news_headlines                           — str or None
    """
    time_info = get_time_info()
    weather = get_weather()
    news = get_news(news_api_key)

    return {
        **time_info,
        "weather": weather,
        "news_headlines": news,
    }
