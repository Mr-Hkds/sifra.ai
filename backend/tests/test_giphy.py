import sys
import os

# Add parent directory to sys.path to import local modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import giphy_client
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

def test_giphy():
    queries = ["funny", "jethalal", "tmkoc dancing", "bollywood shock", "chai"]
    
    print("--- Giphy Search Test ---")
    for q in queries:
        print(f"Searching for: {q} (with 'hindi' enhancement)")
        url = giphy_client.search_gif(q)
        if url:
            print(f"SUCCESS: Found GIF for '{q}': {url}")
        else:
            print(f"FAILED: No GIF found for '{q}'")
    print("-------------------------")

if __name__ == "__main__":
    test_giphy()
