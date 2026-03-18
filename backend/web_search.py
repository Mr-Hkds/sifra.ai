"""
Web Search Module — Gives Sifra the ability to search the web.
Uses DuckDuckGo Instant Answer API (free, no key needed).
Falls back to generating from knowledge if search fails.
"""

import re
import logging
import requests

logger = logging.getLogger(__name__)


def _search_duckduckgo(query: str) -> list[dict]:
    """Search DuckDuckGo and return relevant results."""
    try:
        # DDG Instant Answer API
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=8,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []

        # Abstract (main answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "text": data["AbstractText"][:300],
                "source": data.get("AbstractSource", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "text": topic["Text"][:200],
                    "source": "DuckDuckGo",
                })

        return results
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []


def _search_reddit_for_topic(query: str) -> list[dict]:
    """Search Reddit for discussions about a topic."""
    try:
        headers = {"User-Agent": "SifraMind/1.0"}
        resp = requests.get(
            f"https://www.reddit.com/search.json?q={query}&limit=5&sort=relevance",
            headers=headers, timeout=8,
        )
        if resp.status_code != 200:
            return []

        posts = resp.json().get("data", {}).get("children", [])
        results = []
        for post in posts[:3]:
            d = post.get("data", {})
            title = d.get("title", "")
            selftext = d.get("selftext", "")[:200]
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


def should_search(message: str) -> bool:
    """Detect if the user's message needs a web search."""
    lower = message.lower()

    # Explicit search triggers
    search_triggers = [
        "search", "look up", "find out", "google", "check online",
        "what's happening", "latest news", "trending",
        "kya chal raha", "kya ho raha", "news", "khabar",
        "suggest me", "recommend", "batao koi", "dhundh",
        "movie suggest", "song suggest", "gaana", "film",
        "who is", "what is", "kaun hai", "kya hai",
    ]

    if any(trigger in lower for trigger in search_triggers):
        return True

    # Questions about current events / real-world stuff
    if re.search(r"\b(latest|recent|new|current|today|aaj|abhi)\b", lower) and "?" in message:
        return True

    return False


def search_web(query: str) -> str | None:
    """
    Search the web for a query and return formatted results.
    Returns a formatted string for injection into Sifra's context,
    or None if nothing useful found.
    """
    # Clean query for search
    clean_query = re.sub(r"[?!.,]", "", query).strip()

    # Try DuckDuckGo first
    results = _search_duckduckgo(clean_query)

    # Also try Reddit for community discussions
    reddit_results = _search_reddit_for_topic(clean_query)
    results.extend(reddit_results)

    if not results:
        return None

    # Format results for context injection
    formatted = "WEB SEARCH RESULTS (use these to inform your response, share naturally like you found it yourself):\n"
    for i, r in enumerate(results[:4], 1):
        formatted += f"\n{i}. [{r['source']}] {r['title']}\n   {r['text']}\n"

    formatted += "\nIMPORTANT: Share this info naturally as if YOU found it while scrolling. Don't say 'according to search results'. Say things like 'maine padha ki...', 'dekh sun ye interesting hai', 'arre haan ye toh...'"

    return formatted
