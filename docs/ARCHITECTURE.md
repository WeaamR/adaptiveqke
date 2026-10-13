# Architecture

The selection layer collects context, evaluates a deterministic policy, and configures OpenSSL. Cryptography is delegated to OpenSSL/providers; the project does not implement a new KEM or alter TLS message flow.

| Module | Responsibility |
|---|---|
| `core/context_probe.py` | Concurrent TCP RTT probes and cgroup-limit parsing |
| `core/policy_engine.py` | Network candidate, device classification, and group cap |
| `core/tls_client.py` | OpenSSL subprocess, trace timing, recorded success flag |
| `core/tls_server.py` | TLS service on port 4433 and RTT service on 9000 |
| `core/profile_enforcement.py` | Network shaping and CPU/memory quotas |
| `core/metrics.py` | One-shot TCP relay, byte counts, and timestamp snapshot |
| `core/experiment.py` | Profile loops, seeded order, coordination, CPU accounting |
| `core/results.py` | Timestamped CSV persistence |
| `app.py`, `web/` | Offline replay, policy sandbox, and live adapter |

## Classification

Constrained: CPU < 15% or memory < 64 MB. Mid-range: not constrained, and CPU < 60% or memory < 256 MB. Otherwise high-performance. The tighter constraint wins. `None` denotes unrestricted/unknown in the original code. CPU quota is a fraction of one core, not observed utilization. Memory is labeled MB but calculated using 1024² bytes (effectively MiB).

## Trial coordination

1. Apply profiles and select the next configuration in seeded interleaved order.
2. Probe/select for Adaptive; specify the group directly for static configurations.
3. Start a fresh proxy and runner; apply the client cgroup when configured.
4. The client completion detector triggers `HSCOMPLETE`.
5. The parent waits for proxy quiescence, snapshots counters, and sends `MARKED`.
6. The client closes; the runner returns JSON, and the parent appends the combined CSV row.

This describes implemented coordination, not independent proof of handshake success; see KNOWN_ISSUES.md.

| Device | CPU quota | Memory |
|---|---:|---:|
| High-performance | Unrestricted by profile | Unrestricted by profile |
| Mid-range | 25% of one core | 128 MB |
| Constrained | 10% of one core | 32 MB |

| Network | One-way configured delay | Rate | Loss |
|---|---:|---:|---:|
| Low-latency | 10 ms | 100 Mbit/s | 0% |
| Moderate | 35 ms | 15 Mbit/s | 0.5% |
| High-latency | 60 ms | 3 Mbit/s | 2% |

TLS relay traffic crosses shaped loopback multiple times. These absolute timings are not direct Internet-path measurements. The near-zero-network phase removes netem, pins the client to CPU 0, and discards five warm-ups per device/group.

## Demo

Replay computes historical medians. Sandbox calls the original policy with validated manual input. Live Lab serializes host-changing work. The frontend requests completed results and plays a staged explanation; it is not streaming TLS events. Comparisons always come from the archived dataset.
