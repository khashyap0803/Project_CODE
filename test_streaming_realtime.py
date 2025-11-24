#!/usr/bin/env python3
"""
Real-time Streaming Audio Client
Plays audio as sentences are generated - TRUE real-time experience!
"""
import requests
import pyaudio
import struct
import time
import sys

BASE_URL = "http://localhost:8000"

def play_streaming_audio(text: str):
    """
    Stream audio and play in real-time as sentences are generated
    """
    print(f"\n{'='*70}")
    print(f"Query: {text}")
    print(f"{'='*70}\n")
    
    print("🎤 Sending request to JARVIS...")
    start_time = time.time()
    
    # Start streaming request
    response = requests.post(
        f"{BASE_URL}/api/voice/stream",
        json={"text": text},
        stream=True
    )
    
    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        return
    
    print("📡 Receiving audio stream...")
    
    # Initialize PyAudio
    p = pyaudio.PyAudio()
    
    # Read WAV header from stream (44 bytes) - use larger chunks
    header_data = b""
    chunk_iter = response.iter_content(chunk_size=4096)
    first_chunk = next(chunk_iter)
    header_data = first_chunk[:44]
    remaining_data = first_chunk[44:]  # Save remaining audio data
    
    # Parse WAV header
    riff, size, wave = struct.unpack('<4sI4s', header_data[:12])
    fmt, fmt_size, audio_format, num_channels, sample_rate, byte_rate, block_align, bits_per_sample = \
        struct.unpack('<4sIHHIIHH', header_data[12:36])
    data_marker, data_size = struct.unpack('<4sI', header_data[36:44])
    
    print(f"📊 Audio Format: {num_channels} channels, {sample_rate} Hz, {bits_per_sample}-bit")
    
    # Measure latency only when we get actual audio data (not just header)
    first_audio_time = None
    if remaining_data:
        first_audio_time = time.time()
        latency = first_audio_time - start_time
        print(f"⚡ First audio received in {latency:.3f} seconds")
    else:
        print("⏳ Waiting for audio data...")
    
    # Open audio stream for playback
    stream = p.open(
        format=p.get_format_from_width(bits_per_sample // 8),
        channels=num_channels,
        rate=sample_rate,
        output=True,
        frames_per_buffer=4096
    )
    
    print("🔊 Playing audio in REAL-TIME...\n")
    
    total_bytes = 0
    chunk_count = 0
    
    # Play the remaining data from first chunk
    if remaining_data:
        stream.write(remaining_data)
        total_bytes += len(remaining_data)
        chunk_count += 1
    
    # Stream and play remaining audio as it arrives
    for chunk in chunk_iter:
        if chunk:
            # Measure first audio time if not already measured
            if first_audio_time is None:
                first_audio_time = time.time()
                latency = first_audio_time - start_time
                print(f"⚡ First audio received in {latency:.3f} seconds")
            
            stream.write(chunk)
            total_bytes += len(chunk)
            chunk_count += 1
            
            # Show progress
            if chunk_count % 10 == 0:
                elapsed = time.time() - start_time
                print(f"   📈 Streamed {total_bytes:,} bytes in {elapsed:.2f}s", end='\r')
    
    # Cleanup
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    total_time = time.time() - start_time
    audio_duration = total_bytes / (sample_rate * num_channels * (bits_per_sample // 8)) if total_bytes > 0 else 0
    
    print(f"\n\n✅ Playback complete!")
    print(f"   Total time: {total_time:.2f} seconds")
    print(f"   Audio duration: {audio_duration:.2f} seconds")
    print(f"   Total data: {total_bytes:,} bytes ({chunk_count} chunks)")
    if first_audio_time:
        print(f"   Latency to first audio: {first_audio_time - start_time:.3f}s")
    print()

if __name__ == "__main__":
    print("="*70)
    print("JARVIS Real-Time Streaming Audio Test")
    print("="*70)
    print()
    
    if len(sys.argv) > 1:
        # Use command line argument
        text = " ".join(sys.argv[1:])
        play_streaming_audio(text)
    else:
        # Interactive tests
        tests = [
            "Hello, this is a test of real-time audio streaming",
            "Tell me a short joke",
            "What is the capital of France?",
        ]
        
        for i, test_text in enumerate(tests, 1):
            print(f"\n{'='*70}")
            print(f"Test {i}/{len(tests)}")
            print(f"{'='*70}")
            play_streaming_audio(test_text)
            
            if i < len(tests):
                print("\nPress Enter for next test...")
                input()
        
        print("="*70)
        print("All tests complete!")
        print("="*70)
