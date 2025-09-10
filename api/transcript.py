from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

def _respond(handler, code, payload):
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    # If you ever call this from a browser, CORS helps:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(json.dumps(payload).encode("utf-8"))

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            video_id = qs.get("id", [None])[0]
            if not video_id:
                return _respond(self, 400, {"error": "Missing ?id=VIDEO_ID"})

            # Try English first; the helper also works with auto-captions
            try:
                srt = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            except NoTranscriptFound:
                # One more attempt via transcript list (sometimes finds auto-en)
                try:
                    tlist = YouTubeTranscriptApi.list_transcripts(video_id)
                    srt = tlist.find_transcript(["en"]).fetch()
                except Exception as e:
                    raise NoTranscriptFound(str(e))

            chunks = [
                {"text": c.get("text", ""), "start": float(c["start"]), "duration": float(c["duration"])}
                for c in srt
                if c.get("text")
            ]
            full_text = " ".join(c["text"] for c in chunks).strip()

            return _respond(self, 200, {"videoId": video_id, "chunks": chunks, "full_text": full_text})

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
            return _respond(self, 404, {"error": "Transcript not available", "details": str(e)})
        except Exception as e:
            return _respond(self, 500, {"error": "Internal error", "details": str(e)})
