from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import re, json

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

YT_ID_RE = re.compile(
    r"""(?x)
    (?:^|v=|\/)([0-9A-Za-z_-]{11})  # 11-char YouTube ID after start, v=, or a slash
    """
)

def extract_video_id(id_param: str | None, url_param: str | None) -> str | None:
    """Accepts either a raw ID or any YouTube URL and returns the 11-char video ID."""
    if id_param:
        # If user already passed an ID, strip whitespace and validate.
        m = YT_ID_RE.search(id_param.strip())
        return m.group(1) if m else None
    if url_param:
        u = url_param.strip()
        # Handle watch URL query param first
        parsed = urlparse(u)
        qs = parse_qs(parsed.query or "")
        if "v" in qs and qs["v"]:
            m = YT_ID_RE.search(qs["v"][0])
            return m.group(1) if m else None
        # Fall back to regex over whole URL (works for youtu.be/ID, shorts/ID, etc.)
        m = YT_ID_RE.search(u)
        return m.group(1) if m else None
    return None

def _respond(handler, code, payload):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query or "")
            raw_id = (qs.get("id", [None])[0]) or None
            raw_url = (qs.get("url", [None])[0]) or None

            video_id = extract_video_id(raw_id, raw_url)
            if not video_id:
                return _respond(self, 400, {
                    "error": "Missing or invalid video identifier. Use ?id=VIDEO_ID or ?url=YOUTUBE_URL"
                })

            # Try English first; will pick up auto-captions too
            try:
                srt = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            except NoTranscriptFound:
                # Second attempt via transcript list
                try:
                    tlist = YouTubeTranscriptApi.list_transcripts(video_id)
                    srt = tlist.find_transcript(["en"]).fetch()
                except Exception as e:
                    raise NoTranscriptFound(str(e))

            chunks = [
                {"text": c.get("text", ""), "start": float(c["start"]), "duration": float(c["duration"])}
                for c in srt if c.get("text")
            ]
            full_text = " ".join(c["text"] for c in chunks).strip()

            return _respond(self, 200, {"videoId": video_id, "chunks": chunks, "full_text": full_text})

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            return _respond(self, 404, {"error": "Transcript not available", "details": str(e)})
        except Exception as e:
            return _respond(self, 500, {"error": "Internal error", "details": str(e)})
