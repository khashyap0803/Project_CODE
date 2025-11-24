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
import uuid
from pathlib import Path

# Small, consistent buffers are critical for perceived latency. Lowering the
# trailing silence window keeps requests moving as soon as the user stops
# talking, so the server can start speaking almost immediately.


# Configuration
SERVER_URL = "http://localhost:8000"
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
CHANNELS = 1
FORMAT = pyaudio.paInt16

# Audio recording settings
SILENCE_THRESHOLD = 500  # Adjust based on your microphone
# Stop recording after ~0.4s of trailing silence to keep round-trip latency low
SILENCE_DURATION = 0.4
# Ensure we captured at least this much speech before auto-stopping (seconds)
MIN_UTTERANCE_DURATION = 0.4

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
        total_chunks = 0
        max_silence_chunks = max(1, int(SILENCE_DURATION * SAMPLE_RATE / CHUNK_SIZE))
        recording_started = False
        
        try:
            while self.is_running:
                data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                frames.append(data)
                total_chunks += 1
                
                # Calculate audio level
                audio_data = struct.unpack(f'{CHUNK_SIZE}h', data)
                avg_amplitude = sum(abs(x) for x in audio_data) / len(audio_data)
                
                if avg_amplitude > SILENCE_THRESHOLD:
                    recording_started = True
                    silence_chunks = 0
                elif recording_started:
                    silence_chunks += 1
                    recorded_duration = (total_chunks * CHUNK_SIZE) / SAMPLE_RATE
                    if (
                        silence_chunks >= max_silence_chunks
                        and recorded_duration >= MIN_UTTERANCE_DURATION
                    ):
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
        """Send voice request to JARVIS and stream the audio response immediately"""
        try:
            files = {'audio': ('audio.wav', audio_data, 'audio/wav')}
            print("🤔 JARVIS is thinking...")
            start_time = time.time()
            
            with requests.post(
                f"{SERVER_URL}/api/voice",
                files=files,
                stream=True,
                timeout=120
            ) as response:
                if response.status_code != 200:
                    print(f"❌ Error: {response.status_code}")
                    print(response.text)
                    return False
                
                content_type = response.headers.get('content-type', '')
                if 'audio' in content_type:
                    stream = self.p.open(
                        format=pyaudio.paInt16,
                        channels=2,
                        rate=22050,
                        output=True,
                        frames_per_buffer=1024
                    )
                    header_remaining = 44
                    first_audio_latency = None
                    try:
                        for chunk in response.iter_content(chunk_size=4096):
                            if not chunk:
                                continue
                            if header_remaining > 0:
                                if len(chunk) <= header_remaining:
                                    header_remaining -= len(chunk)
                                    continue
                                chunk = chunk[header_remaining:]
                                header_remaining = 0
                            if first_audio_latency is None:
                                first_audio_latency = time.time() - start_time
                                print(
                                    f"\r🔊 JARVIS speaking... (audio started in {first_audio_latency:.2f}s)",
                                    end='',
                                    flush=True
                                )
                            stream.write(chunk)
                    finally:
                        stream.stop_stream()
                        stream.close()
                    total_time = time.time() - start_time
                    if first_audio_latency is None:
                        print("\n⚠️  No audio data received.")
                        return False
                    print(f"\n⚡ Response finished in {total_time:.2f}s")
                    return True
                elif 'json' in content_type:
                    import json
                    import base64
                    result = response.json()
                    print(f"\n💬 You said: {result.get('transcription', '')}")
                    print(f"💭 JARVIS: {result.get('response_text', '')[:100]}...")
                    if 'audio' in result:
                        audio_bytes = base64.b64decode(result['audio'])
                        self.play_audio_stream(audio_bytes)
                        return True
                    return False
                else:
                    print(f"Unexpected content type: {content_type}")
                    return False
        except requests.exceptions.Timeout:
            print("⏱️  Request timed out. JARVIS might be processing a complex query.")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
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
                success = self.send_voice_request(audio_data)
                
                if success:
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
    
    # Initialize PyAudio for playback and keep stream open to avoid repeated ALSA/JACK setup cost
    p = pyaudio.PyAudio()
    try:
        stream_open_start = time.time()
        output_stream = p.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=22050,
            output=True,
            frames_per_buffer=256,  # Reduced from 1024 for lower latency
            start=True
        )
        stream_open_time = time.time() - stream_open_start
        print(f"🔊 Audio device initialized in {stream_open_time:.3f}s")
        
        # Pre-warm audio device with silence to ensure it's ready
        # This prevents device wakeup delays on first real audio chunk
        silence = b'\x00' * (256 * 2 * 2)  # 256 frames, 2 channels, 2 bytes per sample
        output_stream.write(silence)
        print(f"🔊 Audio device pre-warmed and ready")
    except Exception as e:
        print(f"❌ Unable to open audio output stream: {e}")
        p.terminate()
        return
    
    session_id = f"text-session-{uuid.uuid4()}"
    while True:
        try:
            # Get text input
            user_text = input("\n📝 You: ").strip()
            
            if not user_text:
                continue
            
            lowered = user_text.lower()
            if lowered in ['quit', 'exit', 'bye']:
                print("\n👋 Goodbye!")
                break
            if lowered in {'reset', '/reset', 'new chat', 'clear'}:
                session_id = f"text-session-{uuid.uuid4()}"
                print("🔄 Started a fresh chat session.")
                continue
            
            print("🎤 JARVIS speaking... ", end='', flush=True)
            request_start = time.time()
            first_chunk_received = None
            first_write_start = None
            first_write_complete = None
            
            # Keep audio device active during network/LLM processing
            # Write tiny silence to prevent suspension
            warmup_silence = b'\x00' * 128
            output_stream.write(warmup_silence)
            
            # Send text to /api/voice/text endpoint for streaming audio response
            response = requests.post(
                f"{SERVER_URL}/api/voice/text",
                json={"text": user_text, "session_id": session_id},
                stream=True,
                timeout=120  # 2 minutes for web search and long queries
            )
            
            if response.status_code == 200:
                header_remaining = 44
                for chunk in response.iter_content(chunk_size=4096):
                    if not chunk:
                        continue
                    if header_remaining > 0:
                        if len(chunk) <= header_remaining:
                            header_remaining -= len(chunk)
                            continue
                        chunk = chunk[header_remaining:]
                        header_remaining = 0
                    if first_chunk_received is None:
                        first_chunk_received = time.time() - request_start
                        print(f"[recv={first_chunk_received:.3f}s] ", end='', flush=True)
                        first_write_start = time.time()
                    output_stream.write(chunk)
                    if first_write_complete is None:
                        first_write_complete = time.time() - first_write_start
                        total_to_first_write = time.time() - request_start
                        print(f"[write={first_write_complete:.3f}s] [total={total_to_first_write:.3f}s] ", end='', flush=True)
                print("✅")
            else:
                print(f"\n❌ Error: {response.status_code}")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
    
    try:
        output_stream.stop_stream()
        output_stream.close()
    except Exception:
        pass
    p.terminate()

if __name__ == "__main__":
    main()
