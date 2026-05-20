"""Prometheus-compatible metrics for CyberClaw.

Exposes /metrics endpoint for monitoring. Tracks:
- Request counts per endpoint and status
- LLM call latency and token usage
- Channel message counts
- Active session count
- Streaming chunk throughput
"""

import time
import threading
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Thread-safe Prometheus-style metrics collector."""

    def __init__(self):
        self._lock = threading.Lock()

        # Counters
        self._counters: dict[str, float] = defaultdict(float)

        # Gauges (current values)
        self._gauges: dict[str, float] = defaultdict(float)

        # Histograms (simplified: just store observations)
        self._histograms: dict[str, list[float]] = defaultdict(list)

        # Info labels
        self._info: dict[str, dict[str, str]] = {}

        # Boot time
        self._start_time = time.time()

    # ── Counters ───────────────────────────────────────────────────

    def inc(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter."""
        key = self._label_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        key = self._label_key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    # ── Gauges ─────────────────────────────────────────────────────

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge value."""
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def inc_gauge(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] = self._gauges.get(key, 0.0) + value

    def dec_gauge(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] = self._gauges.get(key, 0.0) - value

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        key = self._label_key(name, labels)
        with self._lock:
            return self._gauges.get(key, 0.0)

    # ── Histograms ─────────────────────────────────────────────────

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record an observation for a histogram."""
        key = self._label_key(name, labels)
        with self._lock:
            obs = self._histograms[key]
            obs.append(value)
            # Keep last 1000 observations to bound memory
            if len(obs) > 1000:
                self._histograms[key] = obs[-1000:]

    # ── Info ───────────────────────────────────────────────────────

    def set_info(self, name: str, labels: dict[str, str]) -> None:
        """Set info-style labels."""
        with self._lock:
            self._info[name] = labels

    # ── Timer context manager ──────────────────────────────────────

    class _Timer:
        def __init__(self, collector: "MetricsCollector", name: str, labels: dict[str, str] | None):
            self.collector = collector
            self.name = name
            self.labels = labels
            self.start = 0.0

        def __enter__(self):
            self.start = time.time()
            return self

        def __exit__(self, *args):
            elapsed = time.time() - self.start
            self.collector.observe(self.name, elapsed, self.labels)

    def timer(self, name: str, labels: dict[str, str] | None = None) -> "_Timer":
        """Return a context manager that records elapsed time."""
        return self._Timer(self, name, labels)

    # ── Export ─────────────────────────────────────────────────────

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []

        # Info
        with self._lock:
            for name, labels in self._info.items():
                label_str = ",".join(f'{k}="{v}"' for k, v in labels.items())
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{{{label_str}}} 1")

            # Uptime
            lines.append("# TYPE cyberclaw_uptime_seconds gauge")
            lines.append(f"cyberclaw_uptime_seconds {time.time() - self._start_time:.1f}")

            # Counters
            for key, value in sorted(self._counters.items()):
                name, label_str = self._parse_key(key)
                if not any(l.startswith(f"# TYPE {name}") for l in lines):
                    lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{{{label_str}}} {value}")

            # Gauges
            for key, value in sorted(self._gauges.items()):
                name, label_str = self._parse_key(key)
                if not any(l.startswith(f"# TYPE {name}") for l in lines):
                    lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name}{{{label_str}}} {value}")

            # Histograms (simplified: export count, sum, avg)
            for key, observations in sorted(self._histograms.items()):
                name, label_str = self._parse_key(key)
                if observations:
                    count = len(observations)
                    total = sum(observations)
                    avg = total / count
                    lines.append(f"# TYPE {name} summary")
                    lines.append(f"{name}_count{{{label_str}}} {count}")
                    lines.append(f"{name}_sum{{{label_str}}} {total:.4f}")
                    lines.append(f"{name}_avg{{{label_str}}} {avg:.4f}")

        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Export as a JSON-friendly dict."""
        with self._lock:
            return {
                "uptime_seconds": round(time.time() - self._start_time, 1),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {
                    k: {
                        "count": len(v),
                        "sum": round(sum(v), 4) if v else 0,
                        "avg": round(sum(v) / len(v), 4) if v else 0,
                    }
                    for k, v in self._histograms.items()
                },
                "info": dict(self._info),
            }

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _label_key(name: str, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return name
        label_parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_parts}"

    @staticmethod
    def _parse_key(key: str) -> tuple[str, str]:
        if "|" in key:
            name, label_part = key.split("|", 1)
            # Convert k=v to k="v"
            pairs = label_part.split(",")
            quoted = ",".join(
                f'{p.split("=")[0]}="{p.split("=")[1]}"' for p in pairs
            )
            return name, quoted
        return key, ""


# Global singleton
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector."""
    return _metrics


# ── Pre-defined metric helpers ─────────────────────────────────────

def record_llm_call(provider: str, model: str, latency: float, tokens_in: int, tokens_out: int) -> None:
    """Record an LLM API call."""
    labels = {"provider": provider, "model": model}
    m = get_metrics()
    m.inc("cyberclaw_llm_calls_total", labels=labels)
    m.observe("cyberclaw_llm_latency_seconds", latency, labels=labels)
    m.inc("cyberclaw_llm_tokens_in_total", tokens_in, labels=labels)
    m.inc("cyberclaw_llm_tokens_out_total", tokens_out, labels=labels)


def record_channel_message(channel: str, direction: str = "in") -> None:
    """Record a channel message (in/out)."""
    m = get_metrics()
    m.inc("cyberclaw_channel_messages_total", labels={"channel": channel, "direction": direction})


def record_api_request(method: str, path: str, status: int, latency: float) -> None:
    """Record an API request."""
    m = get_metrics()
    m.inc("cyberclaw_api_requests_total", labels={"method": method, "path": path, "status": str(status)})
    m.observe("cyberclaw_api_latency_seconds", latency, labels={"method": method, "path": path})


def record_active_sessions(count: int) -> None:
    """Set the active session gauge."""
    get_metrics().set_gauge("cyberclaw_active_sessions", count)
