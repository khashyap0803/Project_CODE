#!/home/nani/Documents/Project/Project_CODE/jarvis/venv/bin/python3
"""
JARVIS - Interactive Voice Assistant Client
The main way to interact with JARVIS through voice

Usage: ./jarvis.py
   or: python jarvis.py
"""
import pyaudio
import wave
import io
import struct
import requests
import time
import sys
import signal
from pathlib import Path

# Configuration
SERVER_URL = "http://localhost:8000"
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
CHANNELS = 1
FORMAT = pyaudio.paInt16

# Audio recording settings
SILENCE_THRESHOLD = 500  # Adjust based on your microphone
SILENCE_DURATION = 2.0  # Seconds of silence to stop recording

class JARVISClient:
    """Interactive voice client for JARVIS"""
    
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.is_running = True
        self.session_id = None
        
        # Setup signal handler for clean exit
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, sig, frame):
        """Handle Ctrl+C gracefully"""
        print("\n\n👋 Goodbye!")
        self.is_running = False
        sys.exit(0)
    
    def record_audio(self):
        """Record audio until silence detected"""
        print("🎤 Listening... (speak now)")
        
        stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )
        
        frames = []
        silence_chunks = 0
        max_silence_chunks = int(SILENCE_DURATION * SAMPLE_RATE / CHUNK_SIZE)
        recording_started = False
        
        try:
            while self.is_running:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                frames.append(data)
                
                # Calculate audio level
                audio_data = struct.unpack(f'{CHUNK_SIZE}h', data)
                avg_amplitude = sum(abs(x) for x in audio_data) / len(audio_data)
                
                if avg_amplitude > SILENCE_THRESHOLD:
                    recording_started = True
                    silence_chunks = 0
                elif recording_started:
                    silence_chunks += 1
                    
                    if silence_chunks >= max_silence_chunks:
                        print("✓ Recording complete")
                        break
                        
        except Exception as e:
            print(f"Recording error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
        
        if not frames:
            return None
            
        # Convert to WAV format
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(frames))
        
        return wav_buffer.getvalue()
    
    def play_audio_stream(self, audio_data):
        """Play audio stream in real-time"""
        # Parse WAV header
        wav_buffer = io.BytesIO(audio_data)
        with wave.open(wav_buffer, 'rb') as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            
            stream = self.p.open(
                format=self.p.get_format_from_width(sample_width),
                channels=channels,
                rate=framerate,
                output=True
            )
            
            # Play audio
            data = wf.readframes(CHUNK_SIZE)
            while data and self.is_running:
                stream.write(data)
                data = wf.readframes(CHUNK_SIZE)
            
            stream.stop_stream()
            stream.close()
    
    def send_voice_request(self, audio_data):
        """Send voice request to JARVIS and get audio response"""
        try:
            # Send audio file
            files = {'audio': ('audio.wav', audio_data, 'audio/wav')}
            
            print("🤔 JARVIS is thinking...")
            start_time = time.time()
            
            response = requests.post(
                f"{SERVER_URL}/api/voice",
                files=files,
                timeout=60
            )
            
            if response.status_code != 200:
                print(f"❌ Error: {response.status_code}")
                print(response.text)
                return None
            
            elapsed = time.time() - start_time
            print(f"⚡ Response in {elapsed:.2f}s")
            
            # Get audio response
            content_type = response.headers.get('content-type', '')
            
            if 'audio' in content_type:
                return response.content
            elif 'json' in content_type:
                # Handle JSON response with base64 audio
                import json
                import base64
                result = response.json()
                print(f"\n💬 You said: {result.get('transcription', '')}")
                print(f"💭 JARVIS: {result.get('response_text', '')[:100]}...")
                
                if 'audio' in result:
                    return base64.b64decode(result['audio'])
                return None
            else:
                print(f"Unexpected content type: {content_type}")
                return None
                
        except requests.exceptions.Timeout:
            print("⏱️  Request timed out. JARVIS might be processing a complex query.")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
    
    def run_interactive(self):
        """Run interactive voice conversation loop"""
        print("=" * 70)
        print("🎯 JARVIS Interactive Voice Assistant")
        print("=" * 70)
        print()
        print("💡 How to use:")
        print("   1. Wait for the listening prompt")
        print("   2. Speak your question")
        print("   3. Stop speaking and wait for JARVIS to respond")
        print("   4. Press Ctrl+C to exit")
        print()
        print("=" * 70)
        print()
        
        # Check server health
        try:
            response = requests.get(f"{SERVER_URL}/health", timeout=5)
            if response.status_code != 200:
                print("⚠️  Warning: Server health check failed")
        except:
            print("❌ Error: Cannot connect to JARVIS server")
            print(f"   Make sure the server is running at {SERVER_URL}")
            return
        
        print("✅ Connected to JARVIS server\n")
        
        while self.is_running:
            try:
                # Record user voice
                audio_data = self.record_audio()
                
                if not audio_data:
                    print("No audio recorded. Try again.\n")
                    continue
                
                # Send to JARVIS
                response_audio = self.send_voice_request(audio_data)
                
                if response_audio:
                    print("🔊 JARVIS is speaking...")
                    self.play_audio_stream(response_audio)
                    print("✓ Done\n")
                else:
                    print("No audio response received.\n")
                
                # Small pause before next interaction
                time.sleep(0.5)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error in conversation loop: {e}\n")
                time.sleep(1)
        
        self.cleanup()
    
    def cleanup(self):
        """Clean up audio resources"""
        try:
            self.p.terminate()
        except:
            pass

def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("JARVIS Interactive Voice Assistant")
            print()
            print("Usage: python jarvis.py [--text]")
            print()
            print("Options:")
            print("  --text    Text-only mode (no microphone needed)")
            print()
            print("Speak naturally to JARVIS and get voice responses.")
            print("Press Ctrl+C to exit.")
            return
        elif sys.argv[1] == "--text":
            # Text-only mode for testing without microphone
            run_text_mode()
            return
    
    client = JARVISClient()
    client.run_interactive()

def run_text_mode():
    """Text input mode with voice output (streaming audio)"""
    print("\n" + "="*70)
    print("🎯 JARVIS Text-to-Voice Mode")
    print("="*70)
    print()
    print("💡 Type your questions, JARVIS responds with VOICE (streaming audio)")
    print("   Type 'quit' or 'exit' to stop.")
    print()
    print("="*70 + "\n")
    
    # Initialize PyAudio for playback
    p = pyaudio.PyAudio()
    
    while True:
        try:
            # Get text input
            user_text = input("\n📝 You: ").strip()
            
            if not user_text:
                continue
            
            if user_text.lower() in ['quit', 'exit', 'bye']:
                print("\n👋 Goodbye!")
                break
            
            print("🎤 JARVIS speaking... ", end='', flush=True)
            
            # Send text to /api/voice/text endpoint for streaming audio response
            response = requests.post(
                f"{SERVER_URL}/api/voice/text",
                json={"text": user_text},
                stream=True,
                timeout=120  # 2 minutes for web search and long queries
            )
            
            if response.status_code == 200:
                # Stream audio playback in real-time
                stream = p.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=22050,
                    output=True,
                    frames_per_buffer=1024
                )
                
                # Skip WAV header (44 bytes)
                header_skipped = False
                bytes_read = 0
                
                for chunk in response.iter_content(chunk_size=4096):
                    if chunk:
                        if not header_skipped and bytes_read < 44:
                            # Skip WAV header
                            bytes_read += len(chunk)
                            if bytes_read >= 44:
                                # Start playing after header
                                chunk = chunk[44 - (bytes_read - len(chunk)):]
                                header_skipped = True
                                stream.write(chunk)
                        else:
                            stream.write(chunk)
                
                stream.stop_stream()
                stream.close()
                print("✅")
            else:
                print(f"\n❌ Error: {response.status_code}")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    p.terminate()

if __name__ == "__main__":
    main()
