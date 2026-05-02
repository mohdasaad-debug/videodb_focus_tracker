# Focus Tracker

A screen-aware focus tracking application that logs and summarizes the time you spend in different applications. It offers two distinct tracking modes: a lightweight local tracker using macOS APIs, and an AI-powered cloud tracker using VideoDB.

## Structure

```text
focus-tracker/
├── local_tracker/       # Fast, lightweight tracker using macOS AppKit
├── videodb_tracker/     # AI-powered visual tracking using VideoDB Screen Capture
├── data/                # Local data storage for events and PIDs
├── examples/            # Example scripts (e.g., upload and search)
└── requirements.txt     # Python dependencies
```

---

## Setup & Prerequisites

1. **Activate the Virtual Environment**
   Make sure you are running from the parent directory's virtual environment:
   ```bash
   cd focus-tracker
   source ../.venv/bin/activate
   ```

2. **Install Requirements**
   If you haven't already, install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **VideoDB API Key** *(Required for VideoDB Tracker only)*
   Ensure you have a `.env` file in the parent directory (`videodb/.env`) containing your `VIDEO_DB_API_KEY`.

---

## Mode 1: VideoDB Tracker (AI Visual Indexing)

This mode securely captures your screen and uses VideoDB's real-time AI to identify the active foreground application. When finished, you receive a focus breakdown and a compiled playback link.

### Step-by-Step Instructions

1. **Start the WebSocket Listener**
   *Open a separate terminal window*, activate your environment, and start the listener. This process catches events coming back from VideoDB.
   ```bash
   cd /path/to/videodb
   source .venv/bin/activate
   python scripts/ws_listener.py --clear /tmp
   ```
   *Leave this running in the background.*

2. **Start the Capture Session**
   In your main terminal, start the screen capture script:
   ```bash
   cd /path/to/videodb/focus-tracker
   source ../.venv/bin/activate
   python videodb_tracker/capture.py --events-dir /tmp
   ```
   *(Note: The very first time you run this, macOS will prompt you for Screen Recording permissions. You may also see a microphone prompt, which is required by the capture API even if you don't record audio).*

3. **Stop Capturing**
   When you are done tracking, press `Ctrl + C` in the capture terminal. Wait a few seconds for the session to finish exporting.
   
   > **Note on Video URLs:** To ensure your session successfully exports and generates a playback link, avoid pressing `Ctrl + C` too quickly after starting. If the process is terminated too abruptly, the session may get stuck in an "active" state and fail to export. Alternatively, use the `--duration <seconds>` flag (e.g., `--duration 60`) to automatically shut down the capture gracefully.

4. **Generate the Summary**
   Run the summary script to see your focus breakdown and get the video playback link:
   ```bash
   python videodb_tracker/summary.py --events-dir /tmp
   ```

5. **View Past Recordings**
   You can view a list of all your past VideoDB recorded sessions and their playback URLs by running the history script:
   ```bash
   python videodb_tracker/history.py
   ```
   Alternatively, you can manage your videos directly on the [VideoDB Timeline Dashboard](https://console.videodb.io/timeline).

---

## Mode 2: Local Tracker (macOS AppKit)

This mode runs entirely on your local machine using the `NSWorkspace` API to detect when you switch between macOS applications. It does not record video or use AI.

### Step-by-Step Instructions

1. **Start Tracking**
   Run the tracker in the background. It will automatically save events to the `data/` folder.
   ```bash
   cd /path/to/videodb/focus-tracker
   source ../.venv/bin/activate
   python local_tracker/tracker.py &
   ```

2. **Generate the Summary**
   You can run the summary script at any time to see your progress:
   ```bash
   python local_tracker/summary.py
   ```

3. **Stop Tracking**
   To stop the local tracker, you can kill the background process using the automatically generated PID file:
   ```bash
   kill $(cat data/tracker.pid)
   ```

---

## Additional Options

- **Audio Capture (VideoDB Mode):** To include microphone and system audio in your VideoDB capture, run:
  ```bash
  python videodb_tracker/capture.py --with-audio --events-dir /tmp
  ```
- **Resetting Data:** To clear previous tracking data when starting a new session:
  - Local mode: `python local_tracker/tracker.py --clear`
  - VideoDB mode: Restart the `ws_listener.py` with the `--clear` flag.
