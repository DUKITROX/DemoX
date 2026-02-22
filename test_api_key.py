"""Quick test: is the ANTHROPIC_API_KEY valid and does it have credits?"""
import os, json, time
from dotenv import load_dotenv
load_dotenv()

LOG_PATH = "/Users/danielbordeianu/git/demogorgux/.cursor/debug.log"

def dlog(message, data=None):
    try:
        entry = {"timestamp": int(time.time()*1000), "location": "test_api_key.py", "message": message, "data": data or {}}
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

api_key = os.getenv("ANTHROPIC_API_KEY", "")
masked = f"{api_key[:10]}...{api_key[-4:]}" if len(api_key) > 14 else "(short/missing)"
dlog("API key check", {"masked_key": masked, "key_length": len(api_key)})
print(f"API key: {masked} (length: {len(api_key)})")

try:
    import anthropic
    client = anthropic.Anthropic()
    dlog("Sending test request to Anthropic API...")
    print("Sending minimal test request to Anthropic API...")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[{"role": "user", "content": "Say hi"}],
    )
    result = response.content[0].text
    dlog("API call SUCCEEDED", {"response": result, "model": response.model})
    print(f"SUCCESS: API responded with: {result}")
except Exception as e:
    dlog("API call FAILED", {"error_type": type(e).__name__, "error_msg": str(e)[:500], "status_code": getattr(e, 'status_code', None)})
    print(f"FAILED: {type(e).__name__}: {e}")
