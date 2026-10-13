# Data and reproducibility

| Dataset | Rows | SHA-256 |
|---|---:|---|
| `data/results.csv` | 1800 | `95c6d106209b64bfb74a56aefa27deff44ba79e32670aed91cb72de9e1280eef` |
| `data/crypto_latency.csv` | 450 | `12895f130473a92a7222003557c16f9938f698cee66669066740820e9fcfd2cc` |

These match dissertation Appendix A. `ORIGINAL_SHA256SUMS` uses repo-relative paths. The supplied `SOURCE_MANIFEST.sha256` is also retained with its original path convention.

## Main data dictionary

| Fields | Meaning |
|---|---|
| `enforced_profile`, `network_profile`, `config` | Experimental condition identifiers |
| `classified_profile` | Device tier from actual recorded limits |
| `cpu_share_pct`, `mem_limit_mb` | Trial limits; blank for unrestricted profile |
| `classified_network` | Network-only candidate group, not network-class label |
| `probed_rtt_ms`, `probe_cost_ms`, `policy_cost_ms` | Context/selection data; blank for static configurations |
| `trial`, `exec_order` | Trial identity and zero-based shuffled execution position |
| `requested_group` | Requested group; not a separately verified negotiated-group field |
| `success` | Original wrapper's recorded flag, with known false-positive issue |
| `handshake_latency_ms` | Client diagnostic-trace interval |
| `wire_latency_ms` | Proxy first-to-last observed chunk interval |
| `cpu_time_ms` | Python wrapper and child CPU delta |
| `handshake_size_bytes`, `handshake_c2s_bytes`, `handshake_s2c_bytes` | Stream bytes at snapshot |

The crypto CSV contains device, group, trial, execution order, the two timing fields, byte count, and the success flag.

## Independent repository analysis

`analysis/summarize.py` uses the standard library, retains all recorded rows, and generates `summary.csv`, `savings_vs_static1024.csv`, `crypto_summary.csv`, and `validation.json`. Optional independent percentile-bootstrap intervals are written to `matching_static_bootstrap.csv`.

Savings = 100 × (static median − adaptive median) / static median. Overall savings are an unweighted arithmetic mean of nine condition-level percentages, not a pooled-median percentage. Some presentation aggregates differ; the README explicitly uses this convention.

First-connection total = median of per-trial (wire latency + probe cost), with policy time separate. It is a derived comparison metric, not a complete process-start-to-application-readiness stopwatch measurement.

Bootstrap samples independently within Adaptive and matching-static cells. Its procedure and seed are disclosed. Original thesis analysis scripts/settings were not supplied, so exact confidence-interval endpoints need not match. An interval spanning zero is not proof of statistical equivalence.

No rows are removed, including three size anomalies. Integrity and structural checks establish consistency and provenance, not correctness of TLS measurement boundaries.
