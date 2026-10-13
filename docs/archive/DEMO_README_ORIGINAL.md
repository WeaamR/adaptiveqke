# AdaptiveQKE Visual Lab

A visual demonstration layer for the AdaptiveQKE graduation-project prototype.

The demo intentionally keeps the project's cryptographic/policy implementation in `core/` and places the presentation layer above it. It supports:

- **Dataset Replay** — works fully offline and reports medians from the supplied experiment CSV (50 recorded trials per device/network/configuration cell).
- **Policy Sandbox** — interactively evaluates the original `policy_engine.py` with custom RTT / CPU / memory values.
- **Live Lab** — when the original Linux/OQS experiment environment is available, applies the device/network profile, performs context probing, calls the original policy engine, executes a real TLS 1.3 handshake, and displays the measured metrics.

## Run — no pip required

```bash
cd AdaptiveQKE_Web_Demo
chmod +x run_demo.sh
./run_demo.sh
```

Then open:

```text
http://127.0.0.1:8765
```

Python 3.10+ is sufficient. **Do not run `pip install -r requirements.txt`; no external Python packages are needed in v1.1.**

## Why v1.1 does not use FastAPI

The OQS/OpenSSL environment used by the experiment may export a custom `OPENSSL_CONF`/`OPENSSL_MODULES`. On some machines that config also affects Python's SSL module and causes pip/PyPI to fail with errors such as `LIBRARY_HAS_NO_CIPHERS`.

The v1.1 dashboard therefore uses Python's standard-library HTTP server and requires no Internet connection or package installation. `run_demo.sh` also protects the web process from a globally exported OQS config while preserving that config for Live Lab subprocesses.

## Dataset Replay

Dataset Replay is the safest mode for the defense/demo machine. It uses the included `data/results.csv`; the displayed values are medians of the recorded trials, not synthetic numbers.

The workflow shown in the UI is:

1. Environment profile
2. Context (RTT, CPU share, memory limit)
3. Policy Stage 1 — RTT candidate
4. Policy Stage 2 — device validation/cap
5. Final hybrid group
6. TLS 1.3 flow visualization
7. Metrics and comparison against the recorded static baselines

## Live Lab requirements

Live Lab additionally requires the same kind of host used for the experiment:

- Linux
- OQS-enabled OpenSSL / oqsprovider
- `tc`, `ip`, `sudo`, `taskset`
- libcgroup tools: `cgcreate`, `cgset`, `cgexec`, `cgdelete`
- the exact OQS/OpenSSL configuration from the experiment
- the three project groups visible to OpenSSL:
  - `x25519_mlkem512`
  - `X25519MLKEM768`
  - `SecP384r1MLKEM1024`

Put the exact configuration at:

```text
config/openssl-oqs.cnf
```

or launch with:

```bash
ADAPTIVEQKE_OPENSSL_CONF=/absolute/path/to/openssl-oqs.cnf ./run_demo.sh
```

If your provider modules are in a custom directory:

```bash
ADAPTIVEQKE_OPENSSL_MODULES=/absolute/path/to/ossl-modules \
ADAPTIVEQKE_OPENSSL_CONF=/absolute/path/to/openssl-oqs.cnf \
./run_demo.sh
```

The UI performs a preflight check and clearly labels Live Lab as unavailable if the environment is incomplete. Replay mode remains usable.

## Important scientific distinctions preserved in the UI

- Device profile is an **experimental environment setting**; the policy's actual device inputs are CPU share and memory limit.
- Network profile is an **environment setting**; Stage 1 uses the **measured RTT**, not the profile name.
- Stage 0 security bounds are shown as **conceptual / not implemented or evaluated**.
- First-connection cost follows the thesis convention: **wire latency + context-probe cost**. Policy evaluation cost is displayed separately.
- The dashboard never labels Replay data as a live measurement.
