#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# IMPORTANT:
# A project-wide OQS OpenSSL config can break Python/pip HTTPS with
# "LIBRARY_HAS_NO_CIPHERS". Preserve it for the Live Lab, but do not expose it
# to the Python web server itself. The Live adapter passes it only to OQS/OpenSSL
# subprocesses when needed.
if [[ -n "${OPENSSL_CONF:-}" && -z "${ADAPTIVEQKE_OPENSSL_CONF:-}" ]]; then
  export ADAPTIVEQKE_OPENSSL_CONF="$OPENSSL_CONF"
fi
if [[ -n "${OPENSSL_MODULES:-}" && -z "${ADAPTIVEQKE_OPENSSL_MODULES:-}" ]]; then
  export ADAPTIVEQKE_OPENSSL_MODULES="$OPENSSL_MODULES"
fi
unset OPENSSL_CONF || true
unset OPENSSL_MODULES || true

if [[ ! -f core/certs/server.crt || ! -f core/certs/server.key ]]; then
  echo "[AdaptiveQKE] TLS demo certificate is missing."
  echo "[AdaptiveQKE] Replay + Policy Sandbox do NOT need it."
  echo "[AdaptiveQKE] For Live Lab later, run: ./core/generate_certs.sh"
fi

if [[ ! -f config/openssl-oqs.cnf && -z "${ADAPTIVEQKE_OPENSSL_CONF:-}" ]]; then
  echo "[AdaptiveQKE] NOTE: OQS OpenSSL config is not present."
  echo "[AdaptiveQKE] Dataset Replay + Policy Sandbox will work normally."
  echo "[AdaptiveQKE] Live Lab will stay unavailable until you copy the exact"
  echo "[AdaptiveQKE] experiment config to config/openssl-oqs.cnf or set:"
  echo "[AdaptiveQKE] ADAPTIVEQKE_OPENSSL_CONF=/absolute/path/to/openssl-oqs.cnf"
fi

export ADAPTIVEQKE_HOST="${ADAPTIVEQKE_HOST:-127.0.0.1}"
export ADAPTIVEQKE_PORT="${ADAPTIVEQKE_PORT:-8765}"

echo "[AdaptiveQKE] Starting Visual Lab at http://${ADAPTIVEQKE_HOST}:${ADAPTIVEQKE_PORT}"
echo "[AdaptiveQKE] Offline mode: no pip install required."
exec python3 app.py
