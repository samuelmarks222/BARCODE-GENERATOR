"""Vercel serverless function: generate compliant AAMVA PDF417 barcode."""

import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from aamva.encode import build_aamva_string, encode_to_png
except Exception:  # pragma: no cover - dependency not installed locally
    build_aamva_string = None
    encode_to_png = None

MAX_INPUT = 20000


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload, content_type="application/json; charset=utf-8"):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        else:
            body = payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        self._send(
            200,
            {
                "service": "py-aamva PDF417 generator",
                "usage": 'POST JSON with AAMVA fields or raw "data" string. Returns base64 PNG.',
            },
        )

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "Invalid Content-Length header."})
            return

        if length <= 0:
            self._send(400, {"error": "Empty request body."})
            return
        if length > MAX_INPUT * 4:
            self._send(413, {"error": "Request body too large."})
            return

        if build_aamva_string is None or encode_to_png is None:
            self._send(500, {"error": "Encoder not available (missing pdf417gen)."})
            return

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "Request body must be valid JSON."})
            return

        if not isinstance(body, dict):
            self._send(400, {"error": "Request body must be a JSON object."})
            return

        # Accept either raw "data" string or structured fields
        data = body.get("data")
        if not isinstance(data, str) or not data.strip():
            # Build compliant AAMVA string from structured fields
            data = build_aamva_string(**body)

        if len(data) > MAX_INPUT:
            self._send(413, {"error": "Input data too large."})
            return

        try:
            columns = int(body.get("columns", 6))
            security = int(body.get("security_level", 2))
            scale = int(body.get("scale", 3))
            ratio = int(body.get("ratio", 3))

            png_bytes = encode_to_png(data, columns=columns, security_level=security, scale=scale, ratio=ratio)
            b64 = base64.b64encode(png_bytes).decode("ascii")

            # For response metadata, we'd need image dimensions; decode from base64 PNG
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(png_bytes))
            width, height = img.size

            self._send(
                200,
                {
                    "format": "png",
                    "data": b64,
                    "width": width,
                    "height": height,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._send(422, {"error": "%s: %s" % (type(exc).__name__, exc)})