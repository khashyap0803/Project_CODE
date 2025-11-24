#!/usr/bin/env python3
"""
YouTube Autoplay Script
Opens YouTube search and attempts to play first non-sponsored video
"""
import sys
import webbrowser
import time

def play_youtube(query):
    """Search YouTube and open results"""
    search_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    print(f"Opening YouTube: {search_url}")
    webbrowser.open(search_url)
    print("Note: Click the first video to play it (autoplay requires browser automation)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: youtube_play.py <search query>")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    play_youtube(query)
