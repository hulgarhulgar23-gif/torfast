"""Shared Tor Browser default-pref proof helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREF_CACHE_DIR = REPO_ROOT / "tmp" / "browser-default-prefs-cache"
REQUIRED_DEFAULT_PREFS = {
    "browser.privatebrowsing.autostart": True,
    "extensions.torbutton.use_nontor_proxy": False,
    "network.dns.disabled": True,
    "network.http.http3.enable": False,
    "network.proxy.allow_bypass": False,
    "network.proxy.failover_direct": False,
    "network.proxy.no_proxies_on": "",
    "network.proxy.socks_remote_dns": True,
    "privacy.firstparty.isolate": True,
    "privacy.resistFingerprinting": True,
    "privacy.resistFingerprinting.letterboxing": True,
}

DEFAULT_PREF_KEYS = list(REQUIRED_DEFAULT_PREFS)


def parse_pref_value(raw: str) -> object:
    raw = raw.strip()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        return raw


def parse_default_pref_text(text: str) -> dict[str, object]:
    prefs: dict[str, object] = {}
    pattern = re.compile(r'^\s*pref\("([^"]+)",\s*(.*?)\);\s*(?://.*)?$')
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        key = match.group(1)
        value_text = match.group(2)
        if value_text.endswith(", locked"):
            value_text = value_text.removesuffix(", locked").strip()
        prefs[key] = parse_pref_value(value_text)
    return prefs


def default_pref_cache_path(omni: Path) -> Path:
    cache_key = hashlib.sha256(str(omni.resolve()).encode("utf-8")).hexdigest()[:16]
    return DEFAULT_PREF_CACHE_DIR / f"{cache_key}.json"


def load_cached_default_prefs(
    *,
    omni: Path,
    source_mtime_ns: int,
    source_size: int,
) -> dict[str, object] | None:
    cache_path = default_pref_cache_path(omni)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("source") != str(omni):
        return None
    if payload.get("source_mtime_ns") != source_mtime_ns:
        return None
    if payload.get("source_size") != source_size:
        return None
    cached_prefs = payload.get("prefs")
    if not isinstance(cached_prefs, dict):
        return None
    return {
        "ok": True,
        "source": str(omni),
        "prefs": {key: cached_prefs.get(key) for key in DEFAULT_PREF_KEYS},
        "cache_hit": True,
        "cache_path": str(cache_path),
    }


def write_default_prefs_cache(
    *,
    omni: Path,
    source_mtime_ns: int,
    source_size: int,
    prefs: dict[str, object],
) -> None:
    cache_path = default_pref_cache_path(omni)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "source": str(omni),
                    "source_mtime_ns": source_mtime_ns,
                    "source_size": source_size,
                    "prefs": {key: prefs.get(key) for key in DEFAULT_PREF_KEYS},
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        tmp_path.replace(cache_path)
    except OSError:
        return


def read_browser_default_prefs(browser_bin: Path) -> dict[str, object]:
    contents_dir = browser_bin.parent.parent
    omni = contents_dir / "Resources" / "browser" / "omni.ja"
    if not omni.exists():
        return {"ok": False, "error": f"not found: {omni}"}
    try:
        source_stat = omni.stat()
    except OSError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    cached = load_cached_default_prefs(
        omni=omni,
        source_mtime_ns=source_stat.st_mtime_ns,
        source_size=source_stat.st_size,
    )
    if cached is not None:
        return cached
    try:
        with zipfile.ZipFile(omni) as archive:
            text = archive.read("defaults/preferences/000-tor-browser.js").decode(
                "utf-8", errors="replace"
            )
    except Exception as exc:  # noqa: BLE001 - metadata only.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    prefs = parse_default_pref_text(text)
    filtered_prefs = {key: prefs.get(key) for key in DEFAULT_PREF_KEYS}
    write_default_prefs_cache(
        omni=omni,
        source_mtime_ns=source_stat.st_mtime_ns,
        source_size=source_stat.st_size,
        prefs=filtered_prefs,
    )
    return {
        "ok": True,
        "source": str(omni),
        "prefs": filtered_prefs,
        "cache_hit": False,
        "cache_path": str(default_pref_cache_path(omni)),
    }


def validate_default_prefs(default_prefs: dict[str, object]) -> dict[str, object]:
    failures: list[str] = []
    if not default_prefs.get("ok"):
        failures.append(str(default_prefs.get("error", "default prefs missing")))
        return {"ok": False, "failures": failures}
    prefs = default_prefs.get("prefs", {})
    if not isinstance(prefs, dict):
        return {"ok": False, "failures": ["default prefs payload is not a dict"]}
    for key, expected in REQUIRED_DEFAULT_PREFS.items():
        actual = prefs.get(key)
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    return {"ok": not failures, "failures": failures}
