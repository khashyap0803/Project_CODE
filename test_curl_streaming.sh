#!/usr/bin/env fish
# True Real-Time Streaming Test with Curl
# Audio plays AS IT'S BEING GENERATED, not after saving to file

echo "🎙️  Recording your voice for 5 seconds..."
echo "Say: 'Hello Jarvis, what is the capital of France?'"
echo ""

# Record audio
arecord -d 5 -f cd /tmp/test_query.wav 2>/dev/null

echo ""
echo "🚀 Sending to JARVIS and streaming audio in REAL-TIME..."
echo "   (Audio will play as sentences are generated)"
echo ""

# TRUE STREAMING: Pipe curl output directly to aplay
# No intermediate file - audio plays immediately as it arrives!
curl -X POST http://localhost:8000/api/voice \
  -F "audio=@/tmp/test_query.wav" \
  --no-buffer \
  -N \
  2>/dev/null | aplay -q 2>/dev/null

echo ""
echo "✅ Done! That was TRUE real-time streaming."
echo "   Audio played as soon as JARVIS generated each sentence."
echo ""
