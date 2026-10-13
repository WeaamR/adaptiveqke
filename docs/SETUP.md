# Setup

## Offline demo

Python 3.10+ is sufficient; no pip dependencies are required.

```bash
bash run_demo.sh
```

Open http://127.0.0.1:8765. Alternatively use `python app.py` in a clean Python environment. Replay and Policy Sandbox need neither certificates nor privileges. A busy port can be changed with `ADAPTIVEQKE_PORT=8766 bash run_demo.sh`.

The launcher preserves custom OpenSSL variables under `ADAPTIVEQKE_OPENSSL_CONF` and `ADAPTIVEQKE_OPENSSL_MODULES` while isolating them from the dashboard process. Keep localhost binding.

## Historical live environment

The dissertation reports Ubuntu 22.04, kernel 6.8.0-124-generic, Python 3.10.12, OpenSSL 3.4.1, oqs-provider 0.9.0 (848b4e6), and liboqs 0.13.0 on VMware. Exact build options, provider configuration, trust setup, and original traces were not supplied. This package cannot promise one-command recreation of that environment.

The harness calls `sudo`, `ip`, `tc`, `cgcreate`, `cgset`, `cgexec`, `cgdelete`, `taskset`, `stdbuf`, `sysctl`, and `modprobe`. It needs cgroup v2, netem, and BBR support. Privileged calls must work non-interactively for the dashboard. No broad passwordless-sudo policy is supplied.

Provide the original configuration at `config/openssl-oqs.cnf`, or for the demo:

```bash
ADAPTIVEQKE_OPENSSL_CONF=/absolute/path/to/openssl-oqs.cnf bash run_demo.sh
```

Optionally supply `ADAPTIVEQKE_OPENSSL_MODULES=/absolute/path/to/ossl-modules`. The direct frozen experiment expects the repository configuration path and does not implement this demo override.

The Live Lab preflight uses `openssl list -tls-groups`, whose availability is version-dependent. Check the exact group names for your OpenSSL/provider build.

On the dedicated live test host, certificates can be generated with:

```bash
bash core/generate_certs.sh
```

Generating a certificate does not establish client trust. Explicit trust/identity validation and the [success/timing issues](KNOWN_ISSUES.md) must be resolved before relying on new results. Keys and generated certificates are ignored by Git.

## Historical experiment entry points

After validating measurement fixes on a disposable host:

```bash
python core/experiment.py
python core/experiment.py --crypto-only
```

The first runs both phases. Output goes to `results/`, separate from archived `data/`. These commands alter host settings and are not part of the offline quick start. Preserve revised measurements separately from the thesis dataset.

## Troubleshooting

| Symptom | Check |
|---|---|
| Live Lab unavailable | Inspect preflight reasons; offline modes still work |
| Certificate verification failed | Trust source and peer identity, not just certificate existence |
| Python SSL/cipher errors | Isolate custom OQS configuration with the launcher |
| Unknown hybrid group | Exact OpenSSL/provider versions, module path, and config |
| Live request hangs | Privileged calls and documented blocking-read timeout limitation |

## Tests

```bash
python analysis/verify_integrity.py
python -m unittest discover -s tests -v
```

These validate offline policy/data/replay behavior, not OQS interoperability or authenticated handshake completion.
