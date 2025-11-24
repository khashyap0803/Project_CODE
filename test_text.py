#!/home/nani/Documents/Project/Project_CODE/jarvis/venv/bin/python3
"""
Quick Text Test - For testing without microphone
Uses the /api/text endpoint for text-to-text responses
"""
import requests
import sys

SERVER_URL = "http://localhost:8000"

def test_text_query(query: str):
    """Send a text query and get text response"""
    print(f"\n{'='*70}")
    print(f"Query: {query}")
    print(f"{'='*70}\n")
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/text",
            json={"text": query},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            jarvis_response = data.get('response', 'No response')
            print(f"JARVIS: {jarvis_response}\n")
            return True
        else:
            print(f"❌ Error: {response.status_code}")
            print(f"   {response.text}\n")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ./test_text.py 'your question here'")
        print()
        print("Examples:")
        print("  ./test_text.py 'What is 2 plus 2?'")
        print("  ./test_text.py 'Tell me about Python'")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    test_text_query(query)
