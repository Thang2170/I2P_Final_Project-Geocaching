"""Smaller downloads: gzip styles, scripts, pages and JSON when the browser can unpack them (owner: B).

(Not called compression.py: Python 3.14 has its own "compression" package, which gzip needs.)

Flask sends everything uncompressed. sprites.css alone is 170 KB, more than half of a first visit;
gzipped it is a fraction of that. The rule is plain Python (should_compress) and easy to test;
add_compression() hooks it into the app (app.py calls it).

Static files are compressed once and kept in memory (keyed by their path and ETag), so a busy
page costs no extra work. Pictures, photos and 3D models are already compressed and are left alone.
"""

import gzip

from flask import request

COMPRESS_TYPES = frozenset({"text/css", "text/javascript", "application/javascript", "application/json",
                            "text/html", "image/svg+xml", "application/manifest+json"})
MIN_BYTES = 1024   # smaller than this, gzip saves almost nothing
LEVEL = 6

_static_cache = {}  # (path, etag) -> gzipped bytes


def wants_gzip(accept_encoding):
    """Does the browser accept gzip? (From the Accept-Encoding header.)"""
    return any(part.split(";")[0].strip().lower() == "gzip" for part in (accept_encoding or "").split(","))


def should_compress(mimetype, size, status, already_encoded, accept_encoding):
    """True if this response should be gzipped."""
    return (status == 200 and not already_encoded and size >= MIN_BYTES
            and mimetype in COMPRESS_TYPES and wants_gzip(accept_encoding))


def add_compression(app):
    @app.after_request
    def compress(response):
        if response.is_streamed and not response.direct_passthrough:
            return response  # made piece by piece: leave it alone
        response.direct_passthrough = False  # static files: read them so they can be compressed
        data = response.get_data()
        if not should_compress(response.mimetype, len(data), response.status_code,
                               bool(response.headers.get("Content-Encoding")),
                               request.headers.get("Accept-Encoding")):
            return response
        etag = response.get_etag()[0]
        key = (request.path, etag) if etag and request.path.startswith("/static/") else None
        packed = _static_cache.get(key) if key else None
        if packed is None:
            packed = gzip.compress(data, LEVEL)
            if key:
                _static_cache[key] = packed
        response.set_data(packed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(packed))
        response.vary.add("Accept-Encoding")
        return response
