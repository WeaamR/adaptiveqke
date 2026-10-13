# OQS-OpenSSL configuration

`core/tls_server.py` from the submitted project expects an OpenSSL configuration that exposes the OQS provider and the three evaluated hybrid groups:

- `x25519_mlkem512`
- `X25519MLKEM768`
- `SecP384r1MLKEM1024`

The exact `openssl-oqs.cnf` used on the experimental machine was not among the files supplied for this web-demo build, so this package intentionally does **not** invent or replace it.

For **Live Lab** mode, either:

1. copy the exact experiment file to `config/openssl-oqs.cnf`, or
2. point to it without copying:

```bash
export ADAPTIVEQKE_OPENSSL_CONF=/absolute/path/to/openssl-oqs.cnf
./run_demo.sh
```

Without that file, **Dataset Replay** and **Policy Sandbox** remain fully usable.
