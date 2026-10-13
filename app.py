from __future__ import annotations

import atexit
import csv
import json
import math
import mimetypes
import os
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "core"
WEB = ROOT / "web"
DATA = ROOT / "data"

# The uploaded implementation uses same-directory imports (e.g. from tls_server import ...).
# Keep the frozen implementation copy first on sys.path so the web layer calls the original
# project policy logic rather than re-implementing it.
sys.path.insert(0, str(CORE))

import policy_engine  # noqa: E402


DEVICE_PROFILES: dict[str, dict[str, Any]] = {
    "High-performance": {
        "name": "High-performance",
        "cpu_quota": None,
        "mem_limit": None,
        "cpu_share_pct": None,
        "memory_mb": None,
        "class_label": "Desktop / cloud server",
        "short": "HIGH",
    },
    "Mid-range": {
        "name": "Mid-range",
        "cpu_quota": 25000,
        "mem_limit": 128,
        "cpu_share_pct": 25.0,
        "memory_mb": 128.0,
        "class_label": "Smartphone / tablet",
        "short": "MID",
    },
    "Constrained": {
        "name": "Constrained",
        "cpu_quota": 10000,
        "mem_limit": 32,
        "cpu_share_pct": 10.0,
        "memory_mb": 32.0,
        "class_label": "IoT sensor / embedded device",
        "short": "LOW",
    },
}

NETWORK_PROFILES: dict[str, dict[str, Any]] = {
    "Low-latency": {
        "name": "Low-latency",
        "delay_ms": 10,
        "rate_mbit": 100,
        "loss_pct": 0.0,
        "rtt_region": "< 50 ms",
        "short": "LOW",
    },
    "Moderate": {
        "name": "Moderate",
        "delay_ms": 35,
        "rate_mbit": 15,
        "loss_pct": 0.5,
        "rtt_region": "50–100 ms",
        "short": "MID",
    },
    "High-latency": {
        "name": "High-latency",
        "delay_ms": 60,
        "rate_mbit": 3,
        "loss_pct": 2.0,
        "rtt_region": "> 100 ms",
        "short": "HIGH",
    },
}

GROUP_META = {
    policy_engine.GROUP_512: {
        "tier": 512,
        "label": "x25519 + ML-KEM-512",
        "openssl_name": policy_engine.GROUP_512,
        "classical": "X25519",
        "pqc": "ML-KEM-512",
        "security_level": 1,
        "role": "Light",
    },
    policy_engine.GROUP_768: {
        "tier": 768,
        "label": "X25519 + ML-KEM-768",
        "openssl_name": policy_engine.GROUP_768,
        "classical": "X25519",
        "pqc": "ML-KEM-768",
        "security_level": 3,
        "role": "Balanced",
    },
    policy_engine.GROUP_1024: {
        "tier": 1024,
        "label": "P-384 + ML-KEM-1024",
        "openssl_name": policy_engine.GROUP_1024,
        "classical": "secp384r1",
        "pqc": "ML-KEM-1024",
        "security_level": 5,
        "role": "Strongest evaluated",
    },
}


class DatasetStore:
    """Dependency-free reader over the frozen experiment CSVs.

    Replay mode reports medians of the 50 successful trials for the selected
    device/network/config cell. It never fabricates timing numbers.
    """

    def __init__(self, results_csv: Path, crypto_csv: Path):
        self.results_csv = results_csv
        self.crypto_csv = crypto_csv
        self.rows = self._load(results_csv)
        self.crypto_rows = self._load(crypto_csv)

    @staticmethod
    def _load(path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _num(row: dict[str, str], key: str) -> float | None:
        raw = row.get(key, "")
        if raw is None or raw == "":
            return None
        try:
            value = float(raw)
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _median(values: list[float | None]) -> float | None:
        clean = [v for v in values if v is not None and math.isfinite(v)]
        return round(statistics.median(clean), 4) if clean else None

    def _cell(self, device: str, network: str, config: str) -> list[dict[str, str]]:
        return [
            row for row in self.rows
            if row.get("enforced_profile") == device
            and row.get("network_profile") == network
            and row.get("config") == config
        ]

    def summary(self, device: str, network: str, config: str) -> dict[str, Any]:
        cell = self._cell(device, network, config)
        if not cell:
            raise KeyError(f"No dataset cell for {device}/{network}/{config}")

        successful = [row for row in cell if row.get("success", "").lower() == "true"]
        source = successful or cell

        groups: dict[str, int] = {}
        for row in source:
            group = row.get("requested_group", "")
            groups[group] = groups.get(group, 0) + 1
        group = max(groups, key=groups.get) if groups else ""

        med = lambda key: self._median([self._num(row, key) for row in source])
        wire = med("wire_latency_ms")
        probe = med("probe_cost_ms")
        policy = med("policy_cost_ms")

        return {
            "config": config,
            "group": group,
            "trials": len(cell),
            "successful_trials": len(successful),
            "aggregation": "median",
            "probed_rtt_ms": med("probed_rtt_ms"),
            "probe_cost_ms": probe,
            "policy_cost_ms": policy,
            "handshake_latency_ms": med("handshake_latency_ms"),
            "wire_latency_ms": wire,
            "cpu_time_ms": med("cpu_time_ms"),
            "handshake_size_bytes": med("handshake_size_bytes"),
            "handshake_c2s_bytes": med("handshake_c2s_bytes"),
            "handshake_s2c_bytes": med("handshake_s2c_bytes"),
            # Median of per-trial Wire + Probe totals, matching Table 4.5. Policy cost is separate.
            "first_connection_cost_ms": (
                self._median([
                    self._num(row, "wire_latency_ms") + self._num(row, "probe_cost_ms")
                    for row in source
                    if self._num(row, "wire_latency_ms") is not None
                    and self._num(row, "probe_cost_ms") is not None
                ])
                if wire is not None and probe is not None
                else None
            ),
        }

    def compare(self, device: str, network: str) -> list[dict[str, Any]]:
        order = ["Adaptive", "Static-512", "Static-768", "Static-1024"]
        return [self.summary(device, network, config) for config in order]

    def adaptive_rows_count(self) -> int:
        return sum(1 for row in self.rows if row.get("config") == "Adaptive")

    def total_rows_count(self) -> int:
        return len(self.rows)


DATASET = DatasetStore(DATA / "results.csv", DATA / "crypto_latency.csv")


def policy_trace(
    rtt_ms: float,
    cpu_share_pct: float | None,
    mem_limit_mb: float | None,
) -> dict[str, Any]:
    if not math.isfinite(rtt_ms) or rtt_ms < 0:
        raise ValueError("RTT must be a finite non-negative value")

    selection = policy_engine.select_group({
        "rtt_ms": float(rtt_ms),
        "cpu_share_pct": cpu_share_pct,
        "mem_limit_mb": mem_limit_mb,
    })
    tier = policy_engine.classify_device(cpu_share_pct, mem_limit_mb)

    return {
        "rtt_ms": round(float(rtt_ms), 4),
        "cpu_share_pct": cpu_share_pct,
        "mem_limit_mb": mem_limit_mb,
        "device_tier": tier,
        "network_candidate": selection.network_candidate,
        "final_group": selection.group,
        "stage1_rule": (
            "RTT > 100 ms → 512"
            if rtt_ms > policy_engine.T_HI
            else "RTT < 50 ms → 1024"
            if rtt_ms < policy_engine.T_LO
            else "50 ms ≤ RTT ≤ 100 ms → 768"
        ),
        "stage2_rule": (
            "Constrained → force 512"
            if tier == "Constrained"
            else "Mid-range → cap 1024 at 768"
            if tier == "Mid-range"
            else "High-performance → keep candidate"
        ),
        "candidate_meta": GROUP_META[selection.network_candidate],
        "final_meta": GROUP_META[selection.group],
    }


class LiveRuntime:
    """Adapter over the project's original implementation.

    Live execution is serialized because tc-netem and the named cgroup modify
    shared host state. The web server itself remains outside the test cgroup.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.tls_proc = None
        self.rtt_thread_started = False
        self._modules_loaded = False

    def config_path(self) -> Path:
        env = os.environ.get("ADAPTIVEQKE_OPENSSL_CONF")
        return Path(env).expanduser().resolve() if env else ROOT / "config" / "openssl-oqs.cnf"

    def _load(self):
        if self._modules_loaded:
            return

        # Importing experiment.py writes OPENSSL_CONF into os.environ. Preserve the
        # web server's clean environment and restore it immediately after import.
        old_conf = os.environ.get("OPENSSL_CONF")
        old_modules = os.environ.get("OPENSSL_MODULES")
        try:
            global experiment, profile_enforcement, tls_server, tls_client
            import experiment  # type: ignore
            import profile_enforcement  # type: ignore
            import tls_server  # type: ignore
            import tls_client  # type: ignore
        finally:
            if old_conf is None:
                os.environ.pop("OPENSSL_CONF", None)
            else:
                os.environ["OPENSSL_CONF"] = old_conf
            if old_modules is None:
                os.environ.pop("OPENSSL_MODULES", None)
            else:
                os.environ["OPENSSL_MODULES"] = old_modules

        conf = str(self.config_path())
        tls_server.OPENSSL_CONF = conf
        experiment.OPENSSL_CONF = conf

        self._modules_loaded = True

    def _openssl_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["OPENSSL_CONF"] = str(self.config_path())
        modules = os.environ.get("ADAPTIVEQKE_OPENSSL_MODULES")
        if modules:
            env["OPENSSL_MODULES"] = modules
        return env

    def preflight(self) -> dict[str, Any]:
        required_commands = [
            "openssl", "sudo", "tc", "ip", "cgcreate", "cgset", "cgexec",
            "cgdelete", "taskset",
        ]
        command_status = {cmd: bool(shutil.which(cmd)) for cmd in required_commands}
        conf = self.config_path()
        cert = CORE / "certs" / "server.crt"
        key = CORE / "certs" / "server.key"

        group_text = ""
        group_error = ""
        try:
            env = self._openssl_env() if conf.exists() else os.environ.copy()
            proc = subprocess.run(
                ["openssl", "list", "-tls-groups"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
            )
            group_text = (proc.stdout or "") + (proc.stderr or "")
        except Exception as exc:
            group_error = str(exc)

        groups = [
            policy_engine.GROUP_512,
            policy_engine.GROUP_768,
            policy_engine.GROUP_1024,
        ]
        group_status = {group: group.lower() in group_text.lower() for group in groups}

        checks = {
            "linux": platform.system().lower() == "linux",
            "commands": all(command_status.values()),
            "openssl_config": conf.exists(),
            "certificate": cert.exists(),
            "private_key": key.exists(),
            "all_hybrid_groups": all(group_status.values()),
        }

        reasons: list[str] = []
        if not checks["linux"]:
            reasons.append("Live Lab requires Linux.")
        missing = [name for name, ok in command_status.items() if not ok]
        if missing:
            reasons.append("Missing commands: " + ", ".join(missing))
        if not conf.exists():
            reasons.append("Missing config/openssl-oqs.cnf (or ADAPTIVEQKE_OPENSSL_CONF).")
        if not cert.exists() or not key.exists():
            reasons.append("TLS demo certificate/key not generated; run ./core/generate_certs.sh.")
        missing_groups = [name for name, ok in group_status.items() if not ok]
        if missing_groups:
            reasons.append("OpenSSL does not expose all project hybrid groups: " + ", ".join(missing_groups))
        if group_error:
            reasons.append("OpenSSL group probe failed: " + group_error)

        return {
            "ready": all(checks.values()),
            "checks": checks,
            "commands": command_status,
            "groups": group_status,
            "openssl_config": str(conf),
            "reasons": reasons,
        }

    def _with_oqs_env(self):
        """Context manager implemented as a tiny nested helper."""
        runtime = self

        class _Env:
            def __enter__(self):
                self.old_conf = os.environ.get("OPENSSL_CONF")
                self.old_modules = os.environ.get("OPENSSL_MODULES")
                os.environ["OPENSSL_CONF"] = str(runtime.config_path())
                modules = os.environ.get("ADAPTIVEQKE_OPENSSL_MODULES")
                if modules:
                    os.environ["OPENSSL_MODULES"] = modules
                return self

            def __exit__(self, exc_type, exc, tb):
                if self.old_conf is None:
                    os.environ.pop("OPENSSL_CONF", None)
                else:
                    os.environ["OPENSSL_CONF"] = self.old_conf
                if self.old_modules is None:
                    os.environ.pop("OPENSSL_MODULES", None)
                else:
                    os.environ["OPENSSL_MODULES"] = self.old_modules

        return _Env()

    def _ensure_servers(self):
        self._load()
        if not self.rtt_thread_started:
            ready = threading.Event()
            thread = threading.Thread(
                target=tls_server.start_rtt_probe_server,
                kwargs={
                    "host": experiment.SERVER_IP,
                    "port": tls_server.RTT_PROBE_PORT,
                    "ready_event": ready,
                },
                daemon=True,
            )
            thread.start()
            if not ready.wait(timeout=3.0):
                raise RuntimeError("RTT probe service did not become ready")
            self.rtt_thread_started = True

        with self._with_oqs_env():
            if self.tls_proc is None or self.tls_proc.poll() is not None:
                self.tls_proc = experiment._start_tls_server_process()
            else:
                self.tls_proc = experiment._ensure_healthy(
                    self.tls_proc, "web demo session"
                )

    def run_adaptive(self, device_name: str, network_name: str) -> dict[str, Any]:
        self._load()
        dev = DEVICE_PROFILES[device_name]
        net = NETWORK_PROFILES[network_name]

        with self.lock:
            preflight = self.preflight()
            if not preflight["ready"]:
                raise RuntimeError(
                    "Live Lab preflight failed: " + " | ".join(preflight["reasons"])
                )

            original_cc = None
            cgroup_setup = False
            network_applied = False
            try:
                original_cc = profile_enforcement.ensure_bbr()
                self._ensure_servers()
                profile_enforcement.setup_cgroup(dev)
                cgroup_setup = dev["cpu_quota"] is not None
                profile_enforcement.apply_network_profile(net)
                network_applied = True
                time.sleep(1.0)

                with self._with_oqs_env():
                    selected_group, probed_rtt, network_candidate, probe_cost_ms, policy_cost_ms = experiment._choose_group(
                        dev, {"name": "Adaptive", "group": None}
                    )
                    measurement = experiment.run_one_trial(
                        dev, selected_group, net_delay_ms=net["delay_ms"]
                    )

                if not measurement.get("success"):
                    with self._with_oqs_env():
                        self.tls_proc = experiment.restart_tls_server(self.tls_proc)

                actual_cpu = measurement.get("cpu_share_pct")
                actual_mem = measurement.get("mem_limit_mb")
                classified = policy_engine.classify_device(actual_cpu, actual_mem)
                trace = policy_trace(
                    float(probed_rtt),
                    dev["cpu_share_pct"],
                    dev["memory_mb"],
                )
                wire = measurement.get("wire_latency_ms")

                return {
                    "mode": "live",
                    "source_label": "LIVE LAB — TLS 1.3 attempt; original detector",
                    "device": device_name,
                    "network": network_name,
                    "context": {
                        "probed_rtt_ms": probed_rtt,
                        "probe_cost_ms": probe_cost_ms,
                        "policy_cost_ms": policy_cost_ms,
                        "cpu_share_pct": actual_cpu if actual_cpu is not None else dev["cpu_share_pct"],
                        "mem_limit_mb": actual_mem if actual_mem is not None else dev["memory_mb"],
                        "classified_device": classified,
                    },
                    "policy": trace,
                    "selected_group": selected_group,
                    "selected_group_meta": GROUP_META[selected_group],
                    "metrics": {
                        "success": bool(measurement.get("success")),
                        "handshake_latency_ms": measurement.get("handshake_latency_ms"),
                        "wire_latency_ms": wire,
                        "cpu_time_ms": measurement.get("cpu_time_ms"),
                        "handshake_size_bytes": measurement.get("handshake_size_bytes"),
                        "handshake_c2s_bytes": measurement.get("handshake_c2s_bytes"),
                        "handshake_s2c_bytes": measurement.get("handshake_s2c_bytes"),
                        "first_connection_cost_ms": (
                            round(float(wire) + float(probe_cost_ms), 4)
                            if wire is not None and probe_cost_ms is not None
                            else None
                        ),
                    },
                    "notes": [
                        "First-connection cost follows the thesis convention: wire latency + context-probe cost.",
                        "Policy evaluation cost is shown separately because it is computationally negligible relative to probing.",
                    ],
                }
            finally:
                if network_applied:
                    try:
                        profile_enforcement.clear_network_profile()
                    except Exception:
                        pass
                if cgroup_setup:
                    try:
                        profile_enforcement.teardown_cgroup(dev)
                    except Exception:
                        pass
                if original_cc:
                    try:
                        subprocess.run(
                            [
                                "sudo", "sysctl", "-w",
                                f"net.ipv4.tcp_congestion_control={original_cc}",
                            ],
                            capture_output=True,
                        )
                    except Exception:
                        pass

    def cleanup(self):
        if not self._modules_loaded:
            return
        try:
            profile_enforcement.clear_network_profile()
        except Exception:
            pass
        try:
            subprocess.run(
                [
                    "sudo", "cgdelete", "-g",
                    f"cpu,memory:{profile_enforcement.CGROUP_NAME}",
                ],
                capture_output=True,
            )
        except Exception:
            pass
        try:
            if self.tls_proc is not None:
                experiment.stop_servers(self.tls_proc)
        except Exception:
            pass


LIVE = LiveRuntime()
atexit.register(LIVE.cleanup)


def validate_condition(device: str, network: str) -> None:
    if device not in DEVICE_PROFILES:
        raise ValueError(f"Unknown device profile: {device}")
    if network not in NETWORK_PROFILES:
        raise ValueError(f"Unknown network profile: {network}")


def replay_session(device: str, network: str) -> dict[str, Any]:
    summary = DATASET.summary(device, network, "Adaptive")
    dev = DEVICE_PROFILES[device]
    rtt = summary["probed_rtt_ms"]
    if rtt is None:
        raise RuntimeError("Adaptive dataset cell has no RTT measurements")

    trace = policy_trace(rtt, dev["cpu_share_pct"], dev["memory_mb"])
    return {
        "mode": "replay",
        "source_label": "DATASET REPLAY — median of 50 recorded Adaptive trials",
        "device": device,
        "network": network,
        "context": {
            "probed_rtt_ms": summary["probed_rtt_ms"],
            "probe_cost_ms": summary["probe_cost_ms"],
            "policy_cost_ms": summary["policy_cost_ms"],
            "cpu_share_pct": dev["cpu_share_pct"],
            "mem_limit_mb": dev["memory_mb"],
            "classified_device": trace["device_tier"],
        },
        "policy": trace,
        "selected_group": summary["group"],
        "selected_group_meta": GROUP_META[summary["group"]],
        "metrics": {
            "success": summary["successful_trials"] == summary["trials"],
            "handshake_latency_ms": summary["handshake_latency_ms"],
            "wire_latency_ms": summary["wire_latency_ms"],
            "cpu_time_ms": summary["cpu_time_ms"],
            "handshake_size_bytes": summary["handshake_size_bytes"],
            "handshake_c2s_bytes": summary["handshake_c2s_bytes"],
            "handshake_s2c_bytes": summary["handshake_s2c_bytes"],
            "first_connection_cost_ms": summary["first_connection_cost_ms"],
        },
        "dataset": {
            "aggregation": summary["aggregation"],
            "trials": summary["trials"],
            "successful_trials": summary["successful_trials"],
        },
        "notes": [
            "Replay values are medians computed from the uploaded experimental CSV, not synthetic measurements.",
            "First-connection cost follows the thesis convention: wire latency + probe cost; policy cost is displayed separately.",
        ],
    }


def meta_payload() -> dict[str, Any]:
    return {
        "title": "AdaptiveQKE Visual Lab",
        "device_profiles": list(DEVICE_PROFILES.values()),
        "network_profiles": list(NETWORK_PROFILES.values()),
        "groups": list(GROUP_META.values()),
        "thresholds": {
            "rtt_low_ms": policy_engine.T_LO,
            "rtt_high_ms": policy_engine.T_HI,
            "cpu_constrained_pct": policy_engine.CPU_SHARE_CONSTRAINED_PCT,
            "cpu_mid_pct": policy_engine.CPU_SHARE_MID_PCT,
            "memory_constrained_mb": policy_engine.MEM_LIMIT_CONSTRAINED_MB,
            "memory_mid_mb": policy_engine.MEM_LIMIT_MID_MB,
        },
        "dataset": {
            "rows": DATASET.total_rows_count(),
            "adaptive_rows": DATASET.adaptive_rows_count(),
            "trials_per_cell": 50,
            "conditions": 9,
            "configurations": 4,
        },
        "live": LIVE.preflight(),
        "stage0": {
            "label": "Security Bounds (Stage 0)",
            "status": "Conceptual — not implemented or evaluated",
        },
    }


def compare_payload(device: str, network: str) -> dict[str, Any]:
    validate_condition(device, network)
    rows = DATASET.compare(device, network)
    return {
        "source_label": "RECORDED DATASET — median of 50 trials per configuration",
        "device": device,
        "network": network,
        "rows": [
            {**row, "group_meta": GROUP_META.get(row["group"])}
            for row in rows
        ],
    }


def parse_nullable_number(value: Any, *, minimum: float, maximum: float, label: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric or null") from exc
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return number


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "AdaptiveQKEVisualLab/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

    def _json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, detail: str) -> None:
        self._json({"detail": detail}, status)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length")
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def _serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            self._error(404, "Not found")
            return

        # Never permit path traversal outside the web directory.
        if resolved != (WEB / "index.html").resolve() and WEB.resolve() not in resolved.parents:
            self._error(403, "Forbidden")
            return
        if not resolved.is_file():
            self._error(404, "Not found")
            return

        mime, _ = mimetypes.guess_type(str(resolved))
        mime = mime or "application/octet-stream"
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime in {"application/javascript", "application/json"} else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        try:
            if path == "/":
                self._serve_file(WEB / "index.html")
                return
            if path.startswith("/static/"):
                rel = path[len("/static/"):]
                self._serve_file(WEB / rel)
                return
            if path == "/api/meta":
                self._json(meta_payload())
                return
            if path == "/api/health":
                self._json({"ok": True, "live": LIVE.preflight()})
                return
            if path == "/api/compare":
                device = query.get("device", [""])[0]
                network = query.get("network", [""])[0]
                self._json(compare_payload(device, network))
                return
            self._error(404, "Not found")
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception as exc:
            self._error(500, f"Request failed: {exc}")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        try:
            body = self._read_json()
            if path == "/api/session":
                mode = str(body.get("mode", "replay"))
                device = str(body.get("device", "High-performance"))
                network = str(body.get("network", "Low-latency"))
                if mode not in {"replay", "live"}:
                    raise ValueError("mode must be 'replay' or 'live'")
                validate_condition(device, network)
                if mode == "live":
                    self._json(LIVE.run_adaptive(device, network))
                else:
                    self._json(replay_session(device, network))
                return

            if path == "/api/policy":
                rtt = parse_nullable_number(
                    body.get("rtt_ms"), minimum=0, maximum=5000, label="RTT"
                )
                if rtt is None:
                    raise ValueError("RTT is required")
                cpu = parse_nullable_number(
                    body.get("cpu_share_pct"), minimum=0, maximum=100,
                    label="CPU share",
                )
                mem = parse_nullable_number(
                    body.get("mem_limit_mb"), minimum=0, maximum=1048576,
                    label="Memory limit",
                )
                self._json({"mode": "sandbox", "policy": policy_trace(rtt, cpu, mem)})
                return

            self._error(404, "Not found")
        except RuntimeError as exc:
            self._error(503, str(exc))
        except ValueError as exc:
            self._error(400, str(exc))
        except Exception as exc:
            self._error(500, f"Request failed: {exc}")


def main() -> None:
    host = os.environ.get("ADAPTIVEQKE_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ADAPTIVEQKE_PORT", "8765"))
    except ValueError:
        raise SystemExit("ADAPTIVEQKE_PORT must be an integer")

    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"[AdaptiveQKE] Visual Lab running at http://{host}:{port}")
    print("[AdaptiveQKE] No pip packages are required.")
    print("[AdaptiveQKE] Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n[AdaptiveQKE] Stopping...")
    finally:
        server.server_close()
        LIVE.cleanup()


if __name__ == "__main__":
    main()
