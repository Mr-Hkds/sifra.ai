import requests
import random
import logging
from config import GIPHY_API_KEY

logger = logging.getLogger(__name__)

def search_gif(query: str) -> str | None:
    """
    Search Giphy for a GIF based on the query.
    Appends 'hindi' to the query for cultural relevance.
    Returns the URL of the GIF or None if not found.
    """
    if not GIPHY_API_KEY:
        logger.warning("GIPHY_API_KEY not set")
        return None

    # Enhance query for Hindi relevance
    meme_keywords = ["hindi meme", "bollywood meme", "indian reaction", "jethalal"]
    # Pick 2 random meme-related keywords to add variety
    extra = " ".join(random.sample(meme_keywords, 2))
    enhanced_query = f"{query} {extra}"
    
    # If the AI explicitly asked for jethalal or tmkoc, focus on that
    if any(k in query.lower() for k in ["jethalal", "tmkoc", "babita"]):
        enhanced_query = f"{query} funny hindi"
    
    try:
        url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": GIPHY_API_KEY,
            "q": enhanced_query,
            "limit": 10,
            "rating": "g",
            "lang": "en"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Giphy search failed: {resp.status_code} - {resp.text}")
            return None
            
        data = resp.json().get("data", [])
        if not data:
            # Fallback to original query without 'hindi' if no results
            params["q"] = query
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json().get("data", [])
            
        if data:
            # Pick a random one from the top results
            chosen = random.choice(data)
            return chosen.get("images", {}).get("original", {}).get("url")
            
        return None
    except Exception as e:
        logger.error(f"search_gif error: {e}")
        return None
