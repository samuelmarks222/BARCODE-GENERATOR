"""Vercel serverless function: generate PDF417 barcode from AAMVA data."""

import base64
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import pdf417gen
except Exception:  # pragma: no cover - dependency not installed locally
    pdf417gen = None

MAX_INPUT = 20000


def serialize(value):
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    return value


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

        if pdf417gen is None:
            self._send(500, {"error": "pdf417gen not installed."})
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
            # Build AAMVA string from structured fields (minimal)
            data = self._build_aamva_string(body)

        if len(data) > MAX_INPUT:
            self._send(413, {"error": "Input data too large."})
            return

        try:
            # pdf417gen expects the raw AAMVA string
            columns = int(body.get("columns", 6))
            security = int(body.get("security_level", 2))
            scale = int(body.get("scale", 3))
            ratio = int(body.get("ratio", 3))

            codes = pdf417gen.encode(data, columns=columns, security_level=security)
            img = pdf417gen.render_image(codes, scale=scale, ratio=ratio)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")

            self._send(
                200,
                {
                    "format": "png",
                    "data": b64,
                    "width": img.width,
                    "height": img.height,
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._send(422, {"error": "%s: %s" % (type(exc).__name__, exc)})

    @staticmethod
    def _build_aamva_string(fields):
        """Very small helper: build a minimal AAMVA string from common fields.
        This is a stub; real generation needs full AAMVA formatting.
        """
        # For now just join known field codes
        lines = []
        for k, v in fields.items():
            if v is not None and v != "":
                lines.append(f"{k}{v}")
        return "\n".join(lines)