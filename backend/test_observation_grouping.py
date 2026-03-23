
import sys
import os

# Mock the environment so we can test the grouping logic
class MockAIClient:
    def extract_json(self, system_prompt, user_prompt, temperature=0.1, max_tokens=1000):
        print(f"\n--- AI ANALYST RECEIVED ---\n{user_prompt}\n--- END ---")
        return {"patterns": [{"category": "tone", "pattern": "Test pattern", "examples": "test", "strength": "strong"}]}

# Inject mocks
sys.modules['ai_client'] = MockAIClient()
sys.modules['config'] = type('MockConfig', (), {
    'OBSERVATION_BATCH_SIZE': 10,
    'OBSERVATION_MAX_LEARNINGS': 80,
    'OBSERVATION_ANALYSIS_TEMPERATURE': 0.4,
    'GROQ_FAST_MODEL': 'mock-model'
})
sys.modules['supabase_client'] = type('MockSupabase', (), {
    'get_unanalyzed_observations': lambda bot_name, limit: [
        {"user_message": "hi", "bot_response": "hello", "id": 1},
        {"user_message": "hi", "bot_response": "how are you?", "id": 2},
        {"user_message": "good", "bot_response": "nice", "id": 3}
    ],
    'mark_observations_analyzed': lambda ids: print(f"Marked as analyzed: {ids}"),
    'insert_learning_pattern': lambda b, p, e, w: print(f"Inserted pattern: {p}")
})

# Now import the logic
from observation_engine import run_batch_analysis

def test_grouping():
    print("Testing observation grouping...")
    result = run_batch_analysis("rumik")
    print(f"\nResult: {result}")

if __name__ == "__main__":
    test_grouping()
