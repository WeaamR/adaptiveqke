# Known issues and research boundaries

The core and datasets are retained exactly as supplied. Original PDFs are archival documents and have not been silently rewritten. These review findings qualify interpretation of their results.

## Handshake success can be a false positive

`core/tls_client.py::run_handshake` recognizes `---`, `CONNECTED`, and a TLS 1.3/cipher string in stdout. It does not require verification success, a client Finished marker, or a successful process exit code.

A focused review test on OpenSSL 3.0.13 with ordinary X25519 and an untrusted self-signed certificate returned `success=True` in three trials despite OpenSSL exit status 1 and certificate verification failure. This tested the wrapper, not the original OpenSSL 3.4.1/OQS experiment.

Thus, CSV success flags do not independently prove completion of authenticated handshakes. Original logs and trust configuration are needed to determine the impact on original measurements. Certificate generation alone does not establish trust. Before relying on new experiments, configure explicit trust and peer-identity validation, require the expected Finished transition, retain verification output/exit status, and test failure paths. Do not disable verification as a workaround.

## TLS 1.3 tickets and timing boundaries

The server uses `-no_ticket`. OpenSSL 3.4 documents that TLS 1.3 ticket emission is controlled by `-num_tickets`, with two tickets by default; `-no_ticket` does not disable it. A local check observed ticket transitions with `-no_ticket` and none with `-num_tickets 0`.

The client uses the last `SSL_connect:` transition across all collected stderr, not an explicit Finished boundary. Post-handshake tickets may extend the recorded time. The proxy also counts all data relayed before its quiescence snapshot, potentially including post-handshake traffic. The exact impact on the archived dataset needs original traces or a validated rerun. Fresh client processes without reused state are distinct from disabling new ticket transmission.

Reference: https://docs.openssl.org/3.4/man1/openssl-s_server/

## Byte-count anomalies

The dominant 1024-group size is 4,886 bytes. Three High-performance / High-latency / Static-1024 rows differ: trials 46 and 13 contain 4,850 bytes; trial 37 contains 4,879 bytes. The CSV alone does not establish why. These rows are retained, not silently excluded or declared failed.

## Measurement scope

- Proxy bytes are TCP-stream bytes, excluding IP/TCP headers and packet retransmissions.
- Proxy latency spans first-to-last observed chunk at the snapshot, not explicit cryptographic boundaries.
- The observer runs outside the client cgroup; real scheduling delays in the client still affect observed traffic.
- CPU time includes the Python trial wrapper and OpenSSL child, including startup/shutdown work. It is not pure ML-KEM runtime.
- Group 1024 changes the classical curve as well as ML-KEM parameters; its extra cost cannot be attributed to ML-KEM alone.
- Direct RTT probes and relayed TLS use different shaped paths.

## Policy and research scope

- Thresholds align with the tested profiles; rule agreement does not establish optimality.
- Delay, rate, and loss vary together. Their independent causal effects are not isolated.
- The policy does not directly measure bandwidth or current CPU utilization.
- Selection uses configured device limits; actual cgroup limits are logged separately in the trial.
- Invalid numeric core inputs such as negative RTT and NaN are not rejected. The demo API validates manual inputs separately.
- Unknown/unreadable and unrestricted cgroup values both become `None`, which can classify an endpoint as high-performance.
- Device tiers are cgroup emulations on one host, not distinct physical mobile/IoT hardware.
- The 512 group uses a private-use identifier and requires compatible peer support.
- Stage 0 bounds are unimplemented. No formal security analysis or demonstrated downgrade resistance is supplied.
- RSA certificate authentication remains classical; the entire connection is not fully post-quantum authenticated.

## Probe cost and fallback

Every Adaptive trial probes again. Context caching and amortization are future work. Post-selection savings are not first-connection savings.

The client offers one group and has no implemented alternate-group retry. HelloRetryRequest requires a mutually supported group; it is not automatic fallback when none overlaps. Some thesis wording is broader than the code.

Reference: https://www.rfc-editor.org/rfc/rfc8446.html (Sections 4.1.1 and 4.2.8).

## Operational limitations

The experiment changes loopback MTU/qdisc, congestion control, and cgroups. It does not restore every pre-existing setting; default qdisc is not restored. Some initialization precedes cleanup protection, and crypto-only failure cleanup is incomplete. Blocking stdout reads occur before `wait(timeout=...)`, so that timeout does not bound the entire operation.

Live Lab preflight checks availability of files/tools/groups, not all privilege or trust requirements. Live mode inherits core defects. Use a dedicated disposable Linux test host for validation. The web server defaults to localhost and has no production authentication layer.

## Repository preparation

Replay now computes median(wire + probe) per trial instead of median(wire) + median(probe), matching the thesis table numerically. Labels distinguish historical flags and explanatory animation from independent success validation and event streaming. No core code or raw dataset was changed.
