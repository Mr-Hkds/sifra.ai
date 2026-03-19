"""
SIFRA:MIND — Web Search Module v2.
AI-powered search: Sifra decides WHEN to search, extracts the right query,
and uses real DuckDuckGo HTML search for actual results.
"""

import re
import logging
import requests
from html.parser import HTMLParser

import ai_client
from config import SEARCH_INTENT_TEMPERATURE, SEARCH_QUERY_TEMPERATURE

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AI-Powered Search Intent Detection
# ---------------------------------------------------------------------------

INTENT_PROMPT = """You decide if a message needs a web search to answer properly.

NEEDS SEARCH (return YES):
- Factual questions: "iPhone 16 price kya hai", "who won IPL", "elon musk ne kya kiya"
- Current events: "aaj kya hua", "latest news", "trending kya hai"
- Knowledge questions: "quantum computing kya hota hai", "tell me about black holes"
- Recommendations needing real data: "best laptop under 50k", "top movies 2026"
- Anything where the answer requires up-to-date or specific factual information

DOES NOT NEED SEARCH (return NO):
- Personal/emotional chat: "bore ho raha hun", "mood off hai", "kya haal hai"
- Opinions/subjective: "kya lagta hai", "tujhe kya pasand hai"
- Greetings: "hi", "good morning", "kaise ho"
- Continuation of personal conversation
- Jokes, memes, casual banter
- Anything Sifra can answer from personality/opinions alone

Return ONLY "YES" or "NO". Nothing else.

Message: {message}
Recent conversation context: {context}"""


QUERY_PROMPT = """Extract a clean, effective web search query from this conversational message.

The message is in Hinglish (Hindi+English mix). Convert it to a clean English search query that would give the best results on a search engine.

Examples:
- "bhai ye iPhone 16 ka price kya hai India mein" → "iPhone 16 price India 2026"
- "yr elon musk ne kya kiya aaj" → "Elon Musk latest news today"
- "konsi nayi movie aayi hai" → "new movie releases 2026"
- "quantum computing kya hota hai" → "what is quantum computing explained"
- "best laptop under 50k batao" → "best laptops under 50000 INR 2026"
- "aaj delhi ka weather kaisa hai" → "Delhi weather today"

Return ONLY the search query. Nothing else. No quotes.

Message: {message}"""


def should_search(message: str, recent_context: str = "") -> bool:
    """AI-powered search intent detection. Much smarter than keyword matching."""
    try:
        result = ai_client.fast(
            system_prompt="You are a search intent classifier. Return ONLY 'YES' or 'NO'.",
            user_prompt=INTENT_PROMPT.format(message=message, context=recent_context or "(no context)"),
            temperature=SEARCH_INTENT_TEMPERATURE,
            max_tokens=5,
        )
        return result.strip().upper().startswith("YES")
    except Exception as e:
        logger.error(f"Search intent detection failed: {e}")
        # Fallback to basic keyword check
        return _fallback_keyword_check(message)


def _fallback_keyword_check(message: str) -> bool:
    """Fallback keyword-based check if AI intent detection fails."""
    lower = message.lower()
    triggers = [
        "search", "google", "news", "price", "cost", "weather",
        "who is", "what is", "kaun hai", "kya hai", "latest",
        "trending", "batao", "tell me about", "how to",
    ]
    return any(trigger in lower for trigger in triggers)


def extract_query(message: str) -> str:
    """AI-powered query extraction from conversational message."""
    try:
        query = ai_client.fast(
            system_prompt="Extract a clean web search query. Return ONLY the query text.",
            user_prompt=QUERY_PROMPT.format(message=message),
            temperature=SEARCH_QUERY_TEMPERATURE,
            max_tokens=30,
        )
        clean = query.strip().strip('"\'')
        return clean if clean else message
    except Exception as e:
        logger.error(f"Query extraction failed: {e}")
        # Fallback: clean up the message directly
        return re.sub(r"[?!.,]", "", message).strip()


# ---------------------------------------------------------------------------
# Search Providers
# ---------------------------------------------------------------------------

class DuckDuckGoParser(HTMLParser):
    """Parse DuckDuckGo HTML search results."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._in_result = False
        self._in_snippet = False
        self._current_title = ""
        self._current_snippet = ""
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")

        if tag == "a" and "result__a" in cls:
            self._in_result = True
            self._current_title = ""

        if tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_snippet = ""

    def handle_endtag(self, tag):
        if tag == "a" and self._in_result:
            self._in_result = False
        if tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self._current_title and self._current_snippet:
                self.results.append({
                    "title": self._current_title.strip(),
                    "text": self._current_snippet.strip(),
                    "source": "DuckDuckGo",
                })

    def handle_data(self, data):
        if self._in_result:
            self._current_title += data
        if self._in_snippet:
            self._current_snippet += data


def _search_duckduckgo(query: str) -> list[dict]:
    """Search DuckDuckGo HTML for real results."""
    try:
        # Try the HTML lite version first — more reliable for scraping
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.warning(f"DDG HTML returned {resp.status_code}")
            return _search_duckduckgo_api(query)

        parser = DuckDuckGoParser()
        parser.feed(resp.text)

        if parser.results:
            return parser.results[:5]

        # If parser didn't find structured results, fall back to the API
        return _search_duckduckgo_api(query)

    except Exception as e:
        logger.error(f"DDG HTML search failed: {e}")
        return _search_duckduckgo_api(query)


def _search_duckduckgo_api(query: str) -> list[dict]:
    """Fallback: DuckDuckGo Instant Answer API."""
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
                "text": data["AbstractText"][:500],
                "source": data.get("AbstractSource", "DuckDuckGo"),
            })

        for topic in data.get("RelatedTopics", [])[:3]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " "),
                    "text": topic["Text"][:300],
                    "source": "DuckDuckGo",
                })

        return results
    except Exception as e:
        logger.error(f"DDG API fallback failed: {e}")
        return []


def _search_reddit(query: str) -> list[dict]:
    """Reddit search for community discussions."""
    try:
        resp = requests.get(
            f"https://www.reddit.com/search.json",
            params={"q": query, "limit": 5, "sort": "relevance"},
            headers={"User-Agent": "SifraMind/3.1"},
            timeout=8,
        )
        if resp.status_code != 200:
            return []

        posts = resp.json().get("data", {}).get("children", [])
        results = []
        for post in posts[:3]:
            d = post.get("data", {})
            title = d.get("title", "")
            selftext = d.get("selftext", "")[:300]
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

def search(message: str) -> str | None:
    """
    Full search pipeline:
    1. Extract clean query from conversational message
    2. Search DuckDuckGo (HTML first, API fallback)
    3. Search Reddit for discussions
    4. Format results for injection into Sifra's prompt

    Returns a formatted string or None if nothing found.
    """
    # Step 1: Extract a proper search query
    query = extract_query(message)
    logger.info(f"Search query extracted: '{query}' from message: '{message[:50]}'")

    # Step 2: Search
    results = _search_duckduckgo(query)
    results.extend(_search_reddit(query))

    if not results:
        return None

    # Step 3: Format with clear source attribution
    formatted = ""
    for i, r in enumerate(results[:5], 1):
        formatted += f"{i}. [{r['source']}] {r['title']}\n   {r['text']}\n\n"

    return formatted.strip()
