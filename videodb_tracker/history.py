#!/usr/bin/env python3
"""
List all past recorded Focus Tracker sessions from VideoDB.

Usage:
  python videodb_tracker/history.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the parent directory to match capture.py
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT.parent / ".env")

try:
    import videodb
except ImportError:
    print("Error: 'videodb' package is not installed.")
    print("Please activate your virtual environment and install dependencies:")
    print("  source ../.venv/bin/activate")
    print("  pip install -r requirements.txt")
    sys.exit(1)

def main():
    if not os.environ.get("VIDEO_DB_API_KEY"):
        print("Error: VIDEO_DB_API_KEY not found. Ensure it is set in your .env file.")
        sys.exit(1)

    print("Fetching recorded sessions from VideoDB...")
    try:
        conn = videodb.connect()
        # Screen recordings are saved in the default collection
        videos = conn.get_collection("default").get_videos()
        
        if not videos:
            print("No recorded sessions found.")
            return
            
        print("\n--- Your Recorded Sessions ---")
        for v in videos:
            # We fetch stream_url if available, falling back to player_url
            url = getattr(v, "stream_url", getattr(v, "player_url", "No URL available"))
            print(f"{v.name}: {url}")
            
    except Exception as e:
        print(f"Failed to fetch sessions: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
