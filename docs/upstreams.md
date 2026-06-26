# Upstreams

Use real upstream code as the source of truth.

## Repos

- C Tor: `https://gitlab.torproject.org/tpo/core/tor.git`
- Arti: `https://gitlab.torproject.org/tpo/core/arti.git`
- Tor Browser releases: `https://dist.torproject.org/torbrowser/`

## Current remote check

Checked on 2026-06-07 local time:

- C Tor `main`: `5478318f2517d2189d41bacbc389fe8731d0ceea`
- Arti `main`: `cca1e63c806a584342c6a16c1e4d57c18672fc85`
- Tor Browser stable used for browser tests: `15.0.15` macOS DMG.

These SHAs can change. Refresh them before making real patches.

## 2026-06-20 browser refresh

- Tor Browser stable resolved from the live dist index during install:
  `15.0.16` macOS DMG.
- download directory: `https://dist.torproject.org/torbrowser/15.0.16/`
- file: `tor-browser-macos-15.0.16.dmg`
- signature file: `tor-browser-macos-15.0.16.dmg.asc`
- signed checksum file: `sha256sums-signed-build.txt`
- signed checksum signature file: `sha256sums-signed-build.txt.asc`
- signing key fingerprint:
  `EF6E286DDA85EA2A4BA7DE684E2C6E8793298290`
- `python3 -m torfast install-browser` fetched the public key from
  `https://keys.openpgp.org/vks/v1/by-fingerprint/EF6E286DDA85EA2A4BA7DE684E2C6E8793298290`,
  pinned the imported key to that fingerprint, verified both detached
  signatures, matched the DMG SHA256, passed `codesign --verify --deep
  --strict`, passed `spctl --assess --type execute`, and passed the Tor Browser
  default-pref proof.
- durable proof bundle:
  `results/torfast-runtime-20260620T163949/`

## Tor Browser test copy

The local test app is copied to `tmp/browser/Tor Browser.app`.

Verified before use:

- release page: `https://forum.torproject.org/t/new-release-tor-browser-15-0-15/21675`
- download directory: `https://dist.torproject.org/torbrowser/15.0.15/`
- file: `tor-browser-macos-15.0.15.dmg`
- signature file: `tor-browser-macos-15.0.15.dmg.asc`
- signed checksum file: `sha256sums-signed-build.txt`
- signing key fingerprint:
  `EF6E286DDA85EA2A4BA7DE684E2C6E8793298290`
- `gpgv` reported a good signature for the DMG and checksum file.
- `shasum -a 256 -c` reported `tor-browser-macos-15.0.15.dmg: OK`.
- `codesign --verify --deep --strict` passed.
- `spctl --assess --type execute` accepted it as notarized Developer ID.

## Fetch

```sh
sh scripts/fetch_upstreams.sh
```

This writes to `upstream/`, which is ignored by this lab repo.
