# Upload to GitHub

Suggested name: **adaptiveqke**

Suggested description: Research prototype for context-aware ECDH + ML-KEM selection before TLS 1.3, with recorded experiments and an interactive visual lab.

Topics: `tls13`, `post-quantum-cryptography`, `ml-kem`, `openssl`, `python`, `network-security`, `cryptography`, `research`, `graduation-project`.

## Upload

Create an empty repository under `WeaamR`. Upload the contents of the extracted `adaptiveqke` folder, with README.md at the repository root. Git is preferable if browser upload omits hidden configuration files.

```bash
cd adaptiveqke
git init
git branch -M main
git add .
git commit -m "Add AdaptiveQKE research prototype and visual lab"
git remote add origin https://github.com/WeaamR/adaptiveqke.git
git push -u origin main
```

The URL is the proposed destination, not an assertion that it exists. This package has not been published or pushed.

Run the README tests first. No keys, generated certificates, bytecode, or local environment files are packaged. The original PDFs retain team authorship; new review caveats live in README/KNOWN_ISSUES. No open-source license has been selected. A future license should reflect the team's decision.

GitHub Actions runs offline tests and integrity checks, not privileged experiments. Keep revised measurements separate with new provenance; preserve the historical data.
