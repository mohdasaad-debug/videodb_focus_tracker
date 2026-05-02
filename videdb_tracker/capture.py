#!/usr/bin/env python3
"""
Screen recording → VideoDB Capture (macOS).

Default: **display only** (no microphone / system audio). Optional `--with-audio` adds mic + system audio.

Prerequisites:
  1. WebSocket listener (writes videodb_ws_id):
       python scripts/ws_listener.py --clear --cwd=<PROJECT_ROOT> &
  2. pip install 'videodb[capture]' python-dotenv

Flow:
  - Loads VIDEO_DB_API_KEY from project root .env
  - Reads WebSocket ID from <events-dir>/videodb_ws_id
  - Asks for screen + a one-time mic *permission handshake* (recorder requires it before
    startRecording, even for display-only; no mic channel is recorded unless --with-audio)
  - Records display with store=True; optional live visual indexing on the screen RTStream
  - Ctrl+C or --duration to stop → wait for capture_session.exported in events JSONL

Examples:
  cd /path/to/videodb && source .venv/bin/activate
  python scripts/ws_listener.py --clear --cwd=/path/to/videodb &
  python videodb_tracker/capture.py --events-dir /tmp
  python videodb_tracker/capture.py --duration 60 --events-dir /tmp
  python videodb_tracker/capture.py --with-audio --events-dir /tmp   # + mic + system audio
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT.parent / ".env")

# Match scripts/ws_listener.py TLS setup (macOS Keychain + certifi fallback)
if os.environ.get("VIDEODB_WS_SKIP_CERTIFI") != "1":
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    try:
        import certifi

        _ca = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", _ca)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca)
    except ImportError:
        pass

import videodb  # noqa: E402
from videodb.capture import CaptureClient  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VideoDB screen recording (optional mic + system audio)")
    p.add_argument(
        "--events-dir",
        default=os.environ.get("VIDEODB_EVENTS_DIR", "/tmp"),
        help="Directory with videodb_ws_id from ws_listener (default: /tmp or VIDEODB_EVENTS_DIR)",
    )
    p.add_argument(
        "--end-user-id",
        default="desktop-user",
        help="End-user id for create_capture_session",
    )
    p.add_argument(
        "--with-audio",
        action="store_true",
        help="Also capture microphone + system audio (default: screen only)",
    )
    p.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip indexing (default: visual description of screen; with --with-audio also transcript/audio)",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=None,
        metavar="SEC",
        help="Stop capture automatically after this many seconds",
    )
    p.add_argument(
        "--rtstream-timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for RTStreams after start_session",
    )
    return p.parse_args()


def read_ws_id(events_dir: Path) -> str:
    path = events_dir / "videodb_ws_id"
    if not path.exists():
        print(
            f"Missing {path}. Start the listener first:\n"
            f"  python scripts/ws_listener.py --clear --cwd={ROOT}",
            file=sys.stderr,
        )
        sys.exit(1)
    ws_id = path.read_text(encoding="utf-8").strip()
    if not ws_id:
        print(f"Empty ws id in {path}", file=sys.stderr)
        sys.exit(1)
    return ws_id


async def wait_for_rtstreams(conn, session_id: str, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = await asyncio.to_thread(conn.get_capture_session, session_id)
        if session.rtstreams:
            return session
        await asyncio.sleep(0.5)
    raise TimeoutError(
        f"No RTStreams after {timeout}s. Grant screen recording permission (and mic if using --with-audio)."
    )


def attach_ai_pipelines(session, ws_id: str, *, with_audio: bool) -> None:
    """Screen-only: visual index on display. With audio: also transcript + audio index."""
    for stream in session.rtstreams:
        name = (stream.name or stream.channel_id or "").lower()
        if name.startswith("display") or name.startswith("screen"):
            stream.index_visuals(
                prompt="Respond ONLY with the exact name of the active foreground application (e.g., 'Chrome', 'VS Code', 'Terminal'). Do not include any other text.",
                batch_config={"type": "time", "value": 4, "frame_count": 3},
                model_name="basic",
                name="screen_visual",
                ws_connection_id=ws_id,
            )
            print(f"[ai] visual index → {stream.name}")
        elif with_audio and name.startswith("mic:"):
            stream.start_transcript(ws_connection_id=ws_id)
            print(f"[ai] transcript → {stream.name}")
        elif with_audio and "system_audio" in name:
            stream.index_audio(
                prompt="Summarize notable speech or sounds from system audio.",
                batch_config={"type": "time", "value": 30},
                name="system_audio_index",
                ws_connection_id=ws_id,
            )
            print(f"[ai] audio index → {stream.name}")


async def run(args: argparse.Namespace) -> None:
    events_dir = Path(args.events_dir).expanduser().resolve()
    ws_id = read_ws_id(events_dir)

    conn = videodb.connect()
    token = conn.generate_client_token()
    mode = "screen+audio" if args.with_audio else "screen"
    session = conn.create_capture_session(
        end_user_id=args.end_user_id,
        collection_id="default",
        ws_connection_id=ws_id,
        metadata={"script": "videodb_tracker/capture.py", "mode": mode},
    )
    print(f"Capture session: {session.id} ({mode})")

    client = CaptureClient(client_token=token)

    # Capture binary requires microphone permission to be *requested* before startRecording,
    # even when only the display channel is used. We do not add a mic track unless --with-audio.
    if not args.with_audio:
        print(
            "Requesting permissions (recorder API requires mic + screen handshakes; "
            "only the screen is recorded — use --with-audio to capture mic/system audio).",
            flush=True,
        )
    await client.request_permission("microphone")
    await client.request_permission("screen_capture")

    channels = await client.list_channels()
    mic = channels.mics.default
    display = channels.displays.default
    system_audio = channels.system_audio.default

    selected: list = []
    if display is None:
        print("No display channel found — cannot record screen.", file=sys.stderr)
        await client.shutdown()
        sys.exit(1)
    display.store = True
    display.is_primary = True
    selected.append(display)

    if args.with_audio:
        for ch in (mic, system_audio):
            if ch is not None:
                ch.store = True
                selected.append(ch)

    await client.start_session(session.id, selected)

    session = await wait_for_rtstreams(conn, session.id, args.rtstream_timeout)
    print(f"RTStreams ready: {len(session.rtstreams)}")

    if not args.no_ai:
        attach_ai_pipelines(session, ws_id, with_audio=args.with_audio)

    stop_event = asyncio.Event()

    def handle_signal() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    if args.duration and args.duration > 0:
        asyncio.create_task(asyncio.sleep(args.duration)).add_done_callback(
            lambda _: stop_event.set()
        )

    print("Capturing (Ctrl+C to stop)… WebSocket events:", events_dir / "videodb_events.jsonl")
    await stop_event.wait()

    try:
        await client.stop_session()
    except Exception as e:
        if "forced stop already in progress" not in str(e):
            raise
    await client.shutdown()
    print("Stopped local capture. Wait for capture_session.exported in events, then stop ws_listener.")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
