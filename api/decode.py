"""Vercel serverless function: decode AAMVA barcode / magstripe data."""

import datetime
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import aamva

MAX_INPUT = 20000

FORMATS = {
    "auto": [aamva.ANY],
    "magstripe": [aamva.MAGSTRIPE],
    "barcode": [aamva.PDF417],
}


def normalize(raw):
    """Repair control characters that browsers/scanners commonly mangle.

    Textareas normalise CR to LF, which breaks the AAMVA header (the segment
    terminator after the record separator must be a carriage return). Some
    scanners also drop the non-printable separators entirely.
    """
    data = raw.strip("\ufeff \t\r\n")
    at = data.find("@")
    if at > 0:
        data = data[at:]

    if data.startswith("@ANSI "):
        data = "@\n\x1e\r" + data[1:]
    elif data.startswith("@\nANSI "):
        data = data[:2] + "\x1e\r" + data[2:]

    if (
        len(data) > 3
        and data[0] == "@"
        and data[1] == "\n"
        and data[2] == "\x1e"
        and data[3] != "\r"
    ):
        data = data[:3] + "\r" + data[4:]

    return data


def serialize(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, aamva.Height):
        return {
            "type": "height",
            "value": value.height,
            "units": value.units,
            "display": str(value),
        }
    if isinstance(value, aamva.Weight):
        return {
            "type": "weight",
            "value": value.weight,
            "units": value.units,
            "display": str(value),
        }
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    return value


class handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
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
                "service": "py-aamva decoder",
                "usage": 'POST JSON {"data": "<raw AAMVA string>", "format": "auto|barcode|magstripe"}',
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

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "Request body must be valid JSON."})
            return

        if not isinstance(body, dict):
            self._send(400, {"error": "Request body must be a JSON object."})
            return

        data = body.get("data")
        if not isinstance(data, str) or not data.strip():
            self._send(400, {"error": "Field 'data' is required."})
            return
        if len(data) > MAX_INPUT:
            self._send(413, {"error": "Input data too large (max 20000 characters)."})
            return

        fmt = str(body.get("format", "auto")).lower()
        if fmt not in FORMATS:
            self._send(400, {"error": "Field 'format' must be auto, barcode or magstripe."})
            return

        # Try the original data first; if it fails, try a normalized version
        candidates = [data]
        norm = normalize(data)
        if norm != data:
            candidates.append(norm)

        decoded = None
        last_exc = None
        for candidate in candidates:
            try:
                decoded = aamva.AAMVA(format=FORMATS[fmt]).decode(candidate)
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

        if decoded is None:
            self._send(422, {"error": "%s: %s" % (type(last_exc).__name__, last_exc)})
            return

        self._send(200, {"format": fmt, "decoded": serialize(decoded)})
