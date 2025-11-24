#!/usr/bin/env fish
# Quick test of text-to-voice endpoint
# Type text, get streaming audio output

echo "🎯 Testing Text-to-Voice Endpoint"
echo ""
echo "Query: 'What is two plus two?'"
echo "Expected: Streaming audio response (not text!)"
echo ""

# Send text query and pipe audio directly to speaker
curl -X POST http://localhost:8000/api/voice/text \
  -H "Content-Type: application/json" \
  -d '{"text": "What is two plus two?"}' \
  --no-buffer \
  -N \
  2>/dev/null | aplay -q 2>/dev/null

echo ""
echo "✅ Audio should have played in real-time!"
echo ""
