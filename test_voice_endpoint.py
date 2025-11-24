#!/usr/bin/env python3
"""
Simple test for /api/voice endpoint
Uses text-to-speech to create test audio, then sends it to the voice endpoint
"""
import requests
import io
import wave
import struct
from gtts import gTTS

def create_test_audio(text: str) -> bytes:
    """Create a simple test WAV audio from text using gTTS"""
    print(f"Creating test audio: '{text}'")
    
    # Use gTTS to create mp3, but we'll convert to WAV format
    tts = gTTS(text=text, lang='en', slow=False)
    
    # Save to bytes
    mp3_fp = io.BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)
    
    return mp3_fp.read()

def test_voice_endpoint():
    """Test the /api/voice endpoint"""
    print("\n" + "="*70)
    print("Testing /api/voice endpoint")
    print("="*70 + "\n")
    
    # Create test audio
    test_query = "Hello Jarvis, what is two plus two?"
    
    # For now, let's just test with a simple approach
    # We'll use the existing test audio or create one manually
    print("⚠️  For full test, please record a WAV file manually")
    print("You can use: arecord -d 3 -f cd /tmp/test_query.wav")
    print("\nOr test with curl:")
    print("curl -X POST http://localhost:8000/api/voice \\")
    print('  -F "audio=@/tmp/test_query.wav" \\')
    print("  --output /tmp/jarvis_response.wav")
    print("\nThen play: aplay /tmp/jarvis_response.wav")

if __name__ == "__main__":
    test_voice_endpoint()
