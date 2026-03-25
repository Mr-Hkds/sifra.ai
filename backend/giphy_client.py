import requests
import random
import logging
from config import GIPHY_API_KEY

logger = logging.getLogger(__name__)

# Context-aware query enhancers — only add when relevant
BOLLYWOOD_KEYWORDS = {"jethalal", "tmkoc", "babita", "amitabh", "srk", "bollywood", "akshay"}
EMOTION_ENHANCERS = {
    "happy": "celebration",
    "sad": "crying emotional",
    "angry": "angry frustrated",
    "excited": "excited hype",
    "love": "romantic love",
    "funny": "funny comedy",
    "surprised": "shocked surprise",
    "bored": "bored sleepy",
}


def search_gif(query: str) -> str | None:
    """
    Search Giphy for a relevant GIF.
    
    v2: Smart enhancement — only adds context when the query is vague.
    No more random meme keyword pollution.
    """
    if not GIPHY_API_KEY:
        logger.warning("GIPHY_API_KEY not set")
        return None

    query_lower = query.lower().strip()

    # If the AI explicitly asked for a Bollywood/TMKOC character, keep it focused
    if any(k in query_lower for k in BOLLYWOOD_KEYWORDS):
        search_query = f"{query} funny hindi"
    # If the query is very short (1-2 words), add "indian" for cultural relevance
    elif len(query_lower.split()) <= 2:
        # Check if it matches an emotion we can enhance
        for emotion, enhancer in EMOTION_ENHANCERS.items():
            if emotion in query_lower:
                search_query = f"{query} {enhancer} indian"
                break
        else:
            search_query = f"{query} indian"
    else:
        # Longer queries are already specific enough — don't pollute
        search_query = query

    try:
        url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": GIPHY_API_KEY,
            "q": search_query,
            "limit": 15,
            "rating": "pg-13",
            "lang": "en"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Giphy search failed: {resp.status_code}")
            return None
            
        data = resp.json().get("data", [])
        
        # Fallback: try original query without enhancement
        if not data:
            params["q"] = query
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json().get("data", [])
            
        if data:
            # Pick from top 5 for more relevant results (not totally random)
            top = data[:min(5, len(data))]
            chosen = random.choice(top)
            gif_url = chosen.get("images", {}).get("original", {}).get("url")
            logger.info(f"GIF found for '{search_query}': {gif_url and gif_url[:60]}")
            return gif_url
            
        logger.warning(f"No GIF found for: {search_query}")
        return None
    except Exception as e:
        logger.error(f"search_gif error: {e}")
        return None
