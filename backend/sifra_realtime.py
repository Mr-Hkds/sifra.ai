"""
SIFRA:MIND — Real-Time Awareness Module v2.

Gives Sifra always-on human-like awareness:
  - Exact IST time + date + day + period
  - Live Delhi weather (temp, feels-like, humidity, condition, wind)
  - Delhi Air Quality Index (PM2.5, PM10)
  - UV Index for Delhi
  - Sunrise & Sunset times
  - Indian holidays & festivals for today
  - Top Indian news headlines (NewsAPI)
  - DuckDuckGo quick-answer for factual lookups

All external calls: 3s hard timeout, per-source TTL caching.
Graceful degradation: any source can fail without breaking anything.
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
# Per-source TTL cache — weather is slow-changing (15m), news is fast (5m)
# ---------------------------------------------------------------------------
_CACHE: dict[str, tuple[float, object]] = {}
_TTL_MAP = {
    "weather": 900,     # 15 minutes — weather changes slowly
    "aqi": 1800,        # 30 minutes — AQI is even slower
    "news": 300,        # 5 minutes — news moves fast
    "holidays": 86400,  # 24 hours — doesn't change within a day
}
_DEFAULT_TTL = 300


def _cached(key: str, fetcher, *args, **kwargs):
    """Fetch with per-source TTL cache. Returns None on error, never raises."""
    now = _time.monotonic()
    ttl = _TTL_MAP.get(key, _DEFAULT_TTL)
    if key in _CACHE:
        ts, val = _CACHE[key]
        if now - ts < ttl:
            return val
    try:
        val = fetcher(*args, **kwargs)
    except Exception as e:
        logger.warning(f"[realtime] {key} fetch failed: {e}")
        # Return stale value if available, otherwise None
        if key in _CACHE:
            _, stale = _CACHE[key]
            return stale
        val = None
    _CACHE[key] = (now, val)
    return val


# ---------------------------------------------------------------------------
# Time / Date — always accurate, zero network cost
# ---------------------------------------------------------------------------

def get_time_info() -> dict:
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
# Indian Holidays & Festivals — hardcoded for awareness (2025-2026)
# ---------------------------------------------------------------------------

_INDIAN_FESTIVALS: dict[str, str] = {
    # 2025
    "01-14": "Makar Sankranti / Pongal 🪁",
    "01-26": "Republic Day 🇮🇳",
    "02-26": "Maha Shivaratri 🔱",
    "03-14": "Holi 🎨",
    "03-30": "Eid ul-Fitr (Ramadan ends) 🌙",
    "03-31": "Eid ul-Fitr 🌙",
    "04-06": "Ram Navami 🏹",
    "04-10": "Mahavir Jayanti 🙏",
    "04-14": "Ambedkar Jayanti / Baisakhi 🌾",
    "04-18": "Good Friday ✝️",
    "05-12": "Buddha Purnima 🪷",
    "06-07": "Eid ul-Adha (Bakrid) 🐑",
    "07-06": "Muharram",
    "08-09": "Raksha Bandhan 🧵",
    "08-15": "Independence Day 🇮🇳",
    "08-16": "Janmashtami 🦚",
    "08-27": "Ganesh Chaturthi 🐘",
    "09-05": "Milad-un-Nabi (Prophet's Birthday) 🌙",
    "10-01": "Navratri begins 🔥",
    "10-02": "Gandhi Jayanti 🕊️",
    "10-10": "Dussehra (Vijayadashami) 🏹",
    "10-20": "Karwa Chauth 🌕",
    "10-29": "Dhanteras ✨",
    "10-31": "Diwali 🪔",
    "11-01": "Govardhan Puja 🐄",
    "11-02": "Bhai Dooj 👫",
    "11-05": "Chhath Puja 🌅",
    "11-15": "Guru Nanak Jayanti 🙏",
    "12-25": "Christmas 🎄",
    # 2026
    "01-14": "Makar Sankranti / Pongal 🪁",
    "01-26": "Republic Day 🇮🇳",
    "03-04": "Holi 🎨",
    "03-20": "Eid ul-Fitr 🌙",
    "04-14": "Ambedkar Jayanti / Baisakhi 🌾",
    "05-01": "Buddha Purnima 🪷",
    "05-27": "Eid ul-Adha 🐑",
    "08-15": "Independence Day 🇮🇳",
    "08-28": "Raksha Bandhan 🧵",
    "09-05": "Janmashtami 🦚",
    "10-02": "Gandhi Jayanti 🕊️",
    "10-17": "Diwali 🪔",
    "11-15": "Guru Nanak Jayanti 🙏",
    "12-25": "Christmas 🎄",
}

_WEEKEND_VIBES = {
    5: "It's Saturday — weekend mode 🎉",
    6: "It's Sunday — lazy day energy 😴",
}


def get_todays_occasion() -> Optional[str]:
    """Check if today is a holiday/festival or weekend."""
    now = datetime.now(_IST)
    key = now.strftime("%m-%d")
    festival = _INDIAN_FESTIVALS.get(key)
    weekend = _WEEKEND_VIBES.get(now.weekday())

    parts = []
    if festival:
        parts.append(f"🎉 Today is {festival}")
    if weekend and not festival:
        parts.append(weekend)
    return " | ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Live Weather — Delhi (Open-Meteo, free, no API key)
# Now includes: wind speed, UV index, sunrise/sunset
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
_UV_LEVEL = [
    (3, "low"), (6, "moderate"), (8, "high"), (11, "very high"), (999, "extreme ⚠️"),
]


def _fetch_weather_full() -> Optional[dict]:
    """Fetch comprehensive weather data in a single API call."""
    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": _DELHI_LAT,
            "longitude": _DELHI_LON,
            "current": (
                "temperature_2m,apparent_temperature,weathercode,"
                "relative_humidity_2m,wind_speed_10m,uv_index"
            ),
            "daily": "sunrise,sunset",
            "timezone": "Asia/Kolkata",
            "forecast_days": 1,
        },
        timeout=3,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    curr = data.get("current", {})
    daily = data.get("daily", {})

    temp = curr.get("temperature_2m")
    if temp is None:
        return None

    feels = curr.get("apparent_temperature", temp)
    code = curr.get("weathercode", 0)
    humidity = curr.get("relative_humidity_2m", 0)
    wind = curr.get("wind_speed_10m", 0)
    uv_raw = curr.get("uv_index", 0)

    # Derive UV level
    uv_label = "low"
    for threshold, label in _UV_LEVEL:
        if uv_raw < threshold:
            uv_label = label
            break

    desc = _WMO_CODES.get(code, "clear")

    # Sunrise/sunset
    sunrise_raw = (daily.get("sunrise") or [None])[0]
    sunset_raw = (daily.get("sunset") or [None])[0]
    sunrise = sunrise_raw.split("T")[1] if sunrise_raw else None
    sunset = sunset_raw.split("T")[1] if sunset_raw else None

    weather_str = (
        f"{desc}, {temp:.0f}°C (feels like {feels:.0f}°C), "
        f"humidity {humidity}%, wind {wind:.0f} km/h — Delhi"
    )

    return {
        "weather_str": weather_str,
        "uv_str": f"UV index: {uv_raw:.0f} ({uv_label})" if uv_raw else None,
        "sunrise": sunrise,
        "sunset": sunset,
        "temp": temp,
    }


def get_weather() -> Optional[dict]:
    return _cached("weather", _fetch_weather_full)


# ---------------------------------------------------------------------------
# Delhi Air Quality (Open-Meteo Air Quality API — free, no key)
# ---------------------------------------------------------------------------

def _fetch_aqi() -> Optional[str]:
    resp = requests.get(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        params={
            "latitude": _DELHI_LAT,
            "longitude": _DELHI_LON,
            "current": "pm2_5,pm10,us_aqi",
            "timezone": "Asia/Kolkata",
        },
        timeout=3,
    )
    if resp.status_code != 200:
        return None

    curr = resp.json().get("current", {})
    aqi = curr.get("us_aqi")
    pm25 = curr.get("pm2_5")
    pm10 = curr.get("pm10")
    if aqi is None:
        return None

    # AQI category
    if aqi <= 50:
        level = "Good 🟢"
    elif aqi <= 100:
        level = "Moderate 🟡"
    elif aqi <= 150:
        level = "Unhealthy for sensitive groups 🟠"
    elif aqi <= 200:
        level = "Unhealthy 🔴"
    elif aqi <= 300:
        level = "Very unhealthy 🟣"
    else:
        level = "Hazardous ☠️"

    parts = [f"AQI: {aqi} ({level})"]
    if pm25 is not None:
        parts.append(f"PM2.5: {pm25:.0f}")
    if pm10 is not None:
        parts.append(f"PM10: {pm10:.0f}")
    return " | ".join(parts) + " — Delhi"


def get_aqi() -> Optional[str]:
    return _cached("aqi", _fetch_aqi)


# ---------------------------------------------------------------------------
# Live Indian News — top headlines (NewsAPI)
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
    for a in articles[:3]:
        title = (a.get("title") or "").split(" - ")[0].strip()
        if title and title != "[Removed]":
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
    """Non-cached — one-off factual lookups during a conversation."""
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
        weather                                  — dict or None
        aqi                                      — str or None
        news_headlines                           — str or None
        occasion                                 — str or None
    """
    time_info = get_time_info()
    weather = get_weather()
    aqi = get_aqi()
    news = get_news(news_api_key)
    occasion = get_todays_occasion()

    return {
        **time_info,
        "weather": weather,
        "aqi": aqi,
        "news_headlines": news,
        "occasion": occasion,
    }
