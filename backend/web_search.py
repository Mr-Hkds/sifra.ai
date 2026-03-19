"""
SIFRA:MIND — Web Search Module.
Gives Sifra the ability to search the web and share findings naturally.
Uses DuckDuckGo (free, no key) + Reddit (free, no key).
"""

import re
import logging
import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Search Triggers — when should Sifra search?
# ---------------------------------------------------------------------------

SEARCH_TRIGGERS = [
    "search", "look up", "find out", "google", "check online",
    "what's happening", "latest news", "trending",
    "kya chal raha", "kya ho raha", "news", "khabar",
    "suggest me", "recommend", "batao koi", "dhundh",
    "movie suggest", "song suggest", "gaana", "film",
    "who is", "what is", "kaun hai", "kya hai",
    "tell me about", "batao", "explain",
]

CURRENT_EVENT_PATTERN = re.compile(
    r"\b(latest|recent|new|current|today|aaj|abhi|trending)\b", re.IGNORECASE
)


def should_search(message: str) -> bool:
    """Detect if the user's message would benefit from a web search."""
    lower = message.lower()

    if any(trigger in lower for trigger in SEARCH_TRIGGERS):
        return True

    if CURRENT_EVENT_PATTERN.search(lower) and "?" in message:
        return True

    return False


# ---------------------------------------------------------------------------
# Search Providers
# ---------------------------------------------------------------------------

def _search_duckduckgo(query: str) -> list[dict]:
    """DuckDuckGo Instant Answer API — free, no key needed."""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=8,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []

        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "text": data["AbstractText"][:400],
                "source": data.get("AbstractSource", "DuckDuckGo"),
            })

        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "text": topic["Text"][:250],
                    "source": "DuckDuckGo",
                })

        return results
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []


def _search_reddit(query: str) -> list[dict]:
    """Reddit search for community discussions."""
    try:
        resp = requests.get(
            f"https://www.reddit.com/search.json",
            params={"q": query, "limit": 5, "sort": "relevance"},
            headers={"User-Agent": "SifraMind/3.0"},
            timeout=8,
        )
        if resp.status_code != 200:
            return []

        posts = resp.json().get("data", {}).get("children", [])
        results = []
        for post in posts[:3]:
            d = post.get("data", {})
            title = d.get("title", "")
            selftext = d.get("selftext", "")[:250]
            sub = d.get("subreddit", "")
            score = d.get("score", 0)
            if title and score > 10:
                results.append({
                    "title": title,
                    "text": selftext or title,
                    "source": f"r/{sub}",
                })
        return results
    except Exception as e:
        logger.error(f"Reddit search failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search(query: str) -> str | None:
    """
    Search the web and return formatted results for injection into Sifra's context.
    Returns a formatted string or None if nothing found.
    """
    clean_query = re.sub(r"[?!.,]", "", query).strip()

    results = _search_duckduckgo(clean_query)
    results.extend(_search_reddit(clean_query))

    if not results:
        return None

    formatted = ""
    for i, r in enumerate(results[:4], 1):
        formatted += f"{i}. [{r['source']}] {r['title']}\n   {r['text']}\n\n"

    return formatted.strip()
