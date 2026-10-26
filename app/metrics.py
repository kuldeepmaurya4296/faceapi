"""Tiny dependency-free metrics registry (Prometheus text format).

Keeps the service portable — no prometheus_client needed — while still giving
you something to scrape for dashboards and alerts.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_ms_sum: dict[str, float] = defaultdict(float)
        self._latency_count: dict[str, int] = defaultdict(int)
        self._faces_total: dict[str, int] = defaultdict(int)

    def observe(self, *, endpoint: str, method: str, status_code: int, latency_ms: float, faces: int = 0) -> None:
        with self._lock:
            self._requests[(endpoint, method, int(status_code))] += 1
            self._latency_ms_sum[endpoint] += float(latency_ms)
            self._latency_count[endpoint] += 1
            if faces:
                self._faces_total[endpoint] += int(faces)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            lines.append("# HELP faceapi_uptime_seconds Seconds since process start.")
            lines.append("# TYPE faceapi_uptime_seconds gauge")
            lines.append(f"faceapi_uptime_seconds {self.uptime_seconds:.3f}")

            lines.append("# HELP faceapi_requests_total HTTP requests handled.")
            lines.append("# TYPE faceapi_requests_total counter")
            for (endpoint, method, status_code), count in sorted(self._requests.items()):
                lines.append(
                    f'faceapi_requests_total{{endpoint="{endpoint}",method="{method}",status="{status_code}"}} {count}'
                )

            lines.append("# HELP faceapi_request_latency_ms_sum Total request latency in milliseconds.")
            lines.append("# TYPE faceapi_request_latency_ms_sum counter")
            for endpoint, total in sorted(self._latency_ms_sum.items()):
                lines.append(f'faceapi_request_latency_ms_sum{{endpoint="{endpoint}"}} {total:.3f}')

            lines.append("# HELP faceapi_request_latency_ms_count Request count for latency averaging.")
            lines.append("# TYPE faceapi_request_latency_ms_count counter")
            for endpoint, count in sorted(self._latency_count.items()):
                lines.append(f'faceapi_request_latency_ms_count{{endpoint="{endpoint}"}} {count}')

            lines.append("# HELP faceapi_faces_detected_total Faces detected.")
            lines.append("# TYPE faceapi_faces_detected_total counter")
            for endpoint, faces in sorted(self._faces_total.items()):
                lines.append(f'faceapi_faces_detected_total{{endpoint="{endpoint}"}} {faces}')
        return "\n".join(lines) + "\n"
