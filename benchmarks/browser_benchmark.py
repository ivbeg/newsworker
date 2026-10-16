"""Local Playwright latency/RSS benchmark with no external network access."""

# ruff: noqa: E402, I001 -- the source checkout is added before project imports.

from __future__ import annotations

import resource
import statistics
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from newsworker.fetch import FetchPolicy
from newsworker.jsrender import PlaywrightRenderer

PAGE = b"""<!doctype html><html><body><main id='app'></main><script>
document.getElementById('app').innerHTML = '<article><a href="/one">Rendered headline</a></article>';
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, format, *args):
        return None


def rss_megabytes(usage):
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return usage.ru_maxrss / divisor


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/listing"
    renderer = PlaywrightRenderer(
        FetchPolicy(
            block_private_hosts=True,
            allow_private_hosts=True,
            allowed_hosts=("127.0.0.1",),
        ),
        timeout=15,
        max_bytes=10 * 1024 * 1024,
        concurrency=1,
    )
    latencies = []
    try:
        for _ in range(5):
            started = time.perf_counter()
            result = renderer.render(url)
            latencies.append((time.perf_counter() - started) * 1000)
            assert b"Rendered headline" in result.body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    self_rss = rss_megabytes(resource.getrusage(resource.RUSAGE_SELF))
    child_rss = rss_megabytes(resource.getrusage(resource.RUSAGE_CHILDREN))
    print(f"median render latency: {statistics.median(latencies):.1f} ms")
    print(f"p95 render latency: {max(latencies):.1f} ms (5-sample approximation)")
    print(f"parent peak RSS: {self_rss:.1f} MiB")
    print(f"browser-child peak RSS: {child_rss:.1f} MiB")


if __name__ == "__main__":
    main()
