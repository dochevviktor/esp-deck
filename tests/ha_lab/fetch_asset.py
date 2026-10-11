"""Bounded host HTTP adapter. This does not exercise the ESP-IDF HTTP worker.

One child process per fetch keeps DNS and network I/O off the ESPHome loop.
stdout is a private binary pipe: little-endian status/error followed by PNG.
The parent bounds the bytes again, enforces the pipeline deadline and drains
cancelled children before releasing the output buffer. No URLs/errors are logged.
"""
import socket
import struct
import sys
import urllib.error
import urllib.request

LIMIT = 128 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url):
    try:
        # Explicitly ignore workstation/container proxy environment variables.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        request = urllib.request.Request(url, headers={
            "Accept": "image/png", "Accept-Encoding": "identity", "Cache-Control": "no-cache"})
        with opener.open(request, timeout=5) as response:
            status = response.status
            if status != 200:
                return status, 2, b""
            headers = response.headers
            if (headers.get_content_type() != "image/png"
                    or headers.get("Content-Encoding", "identity") != "identity"):
                return status, 3, b""
            size = headers.get("Content-Length")
            if size is not None and (not size.isdecimal() or int(size) > LIMIT):
                return status, 4, b""
            body = response.read(LIMIT + 1)
            if len(body) > LIMIT:
                return status, 4, b""
            if size is not None and len(body) != int(size):
                return status, 1, b""
            return status, 0, body
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return status, 2, b""
    except (OSError, ValueError, urllib.error.URLError, socket.timeout):
        return 0, 1, b""


if __name__ == "__main__":
    status, error, body = fetch(sys.argv[1])
    sys.stdout.buffer.write(struct.pack("<II", status, error) + body)
