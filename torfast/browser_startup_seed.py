"""Helpers for a shared startup-only Tor Browser profile seed."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROWSER_STARTUP_SEED_ROOT = (
    REPO_ROOT / "tmp" / "torfast-browser-startup-seed"
)
SEED_FILES_DIRNAME = "files"
SEED_MANIFEST_NAME = "seed.json"
EXTENSIONS_JSON_NAME = "extensions.json"
STARTUP_CACHE_RELATIVE_PATH = Path("startupCache") / "webext.sc.lz4"


@dataclass(frozen=True)
class BrowserStartupSeedPaths:
    root: Path
    files_dir: Path
    manifest_json: Path


def resolve_seed_paths(seed_root: Path) -> BrowserStartupSeedPaths:
    return BrowserStartupSeedPaths(
        root=seed_root,
        files_dir=seed_root / SEED_FILES_DIRNAME,
        manifest_json=seed_root / SEED_MANIFEST_NAME,
    )


def read_seed_manifest(seed_root: Path) -> dict[str, object] | None:
    manifest_path = resolve_seed_paths(seed_root).manifest_json
    if not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def describe_seed(seed_root: Path) -> dict[str, object]:
    paths = resolve_seed_paths(seed_root)
    manifest = read_seed_manifest(seed_root)
    return {
        "exists": paths.root.exists(),
        "seed_root": str(paths.root),
        "manifest": manifest,
        "distribution_app_profile_extension_ids": (
            manifest.get("distribution_app_profile_extension_ids", [])
            if isinstance(manifest, dict)
            else []
        ),
        "files": [
            str(path)
            for path in seed_manifest_relative_paths(manifest)
        ],
    }


def apply_seed_to_profile(profile_dir: Path, seed_root: Path) -> dict[str, object]:
    paths = resolve_seed_paths(seed_root)
    manifest = read_seed_manifest(seed_root)
    relative_paths = seed_manifest_relative_paths(manifest)
    if manifest is None:
        return {
            "ok": True,
            "applied": False,
            "reason": "seed manifest missing",
            "seed_root": str(paths.root),
        }
    if not relative_paths:
        return {
            "ok": True,
            "applied": False,
            "reason": "seed manifest files entry missing",
            "seed_root": str(paths.root),
        }
    profile_dir.mkdir(parents=True, exist_ok=True)
    if any(profile_dir.iterdir()):
        return {
            "ok": True,
            "applied": False,
            "reason": "profile dir not empty",
            "seed_root": str(paths.root),
            "profile_dir": str(profile_dir),
        }
    copied: list[str] = []
    for relative_path in relative_paths:
        source = paths.files_dir / relative_path
        if not source.exists():
            return {
                "ok": False,
                "applied": False,
                "reason": f"seed file missing: {source}",
                "seed_root": str(paths.root),
            }
        destination = profile_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(relative_path))
    return {
        "ok": True,
        "applied": True,
        "seed_root": str(paths.root),
        "profile_dir": str(profile_dir),
        "files": copied,
    }


def update_seed_from_profile(profile_dir: Path, seed_root: Path) -> dict[str, object]:
    seed_paths = resolve_seed_paths(seed_root)
    existing_manifest = read_seed_manifest(seed_root)
    allowed_extension_ids = manifest_distribution_app_profile_extension_ids(
        existing_manifest
    )
    collected = collect_seedable_profile_paths(
        profile_dir,
        allowed_app_profile_extension_ids=allowed_extension_ids,
    )
    if not collected["ok"]:
        return {
            "ok": True,
            "updated": False,
            "reason": collected["reason"],
            "seed_root": str(seed_paths.root),
            "profile_dir": str(profile_dir),
        }
    relative_paths = collected["relative_paths"]
    assert isinstance(relative_paths, list)
    if not relative_paths:
        return {
            "ok": True,
            "updated": False,
            "reason": "no seedable startup files found",
            "seed_root": str(seed_paths.root),
            "profile_dir": str(profile_dir),
        }
    preserved_entries = preserved_seed_entries(
        manifest=existing_manifest,
        seed_root=seed_root,
        profile_dir=profile_dir,
        relative_paths=relative_paths,
        distribution_app_profile_extension_ids=collected[
            "distribution_app_profile_extension_ids"
        ],
    )
    combined_relative_paths = [
        *relative_paths,
        *[
            Path(str(entry["path"]))
            for entry in preserved_entries
            if isinstance(entry.get("path"), str)
        ],
    ]
    if browser_seed_manifest_matches_profile(
        manifest=existing_manifest,
        seed_root=seed_root,
        profile_dir=profile_dir,
        relative_paths=relative_paths,
        distribution_app_profile_extension_ids=collected[
            "distribution_app_profile_extension_ids"
        ],
        preserved_entries=preserved_entries,
    ):
        return {
            "ok": True,
            "updated": False,
            "reason": "seed already current",
            "seed_root": str(seed_paths.root),
            "profile_dir": str(profile_dir),
            "files": [path.as_posix() for path in combined_relative_paths],
            "distribution_app_profile_extension_ids": collected[
                "distribution_app_profile_extension_ids"
            ],
        }

    tmp_root = seed_paths.root.with_name(seed_paths.root.name + ".tmp")
    shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_paths = resolve_seed_paths(tmp_root)
    tmp_paths.files_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: list[dict[str, object]] = []
    for relative_path in relative_paths:
        source = profile_dir / relative_path
        if not source.exists():
            continue
        destination = tmp_paths.files_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        source_stat = source.stat()
        manifest_files.append(
            {
                "path": relative_path.as_posix(),
                "bytes": source_stat.st_size,
                "mtime_ns": source_stat.st_mtime_ns,
            }
        )
    for entry in preserved_entries:
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        relative_path = Path(raw_path)
        source = seed_paths.files_dir / relative_path
        if not source.exists():
            continue
        destination = tmp_paths.files_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        manifest_files.append(dict(entry))

    if not manifest_files:
        shutil.rmtree(tmp_root, ignore_errors=True)
        return {
            "ok": True,
            "updated": False,
            "reason": "no seedable startup files found",
            "seed_root": str(seed_paths.root),
            "profile_dir": str(profile_dir),
        }

    manifest = {
        "kind": "browser_startup_seed",
        "version": 1,
        "distribution_app_profile_extension_ids": collected[
            "distribution_app_profile_extension_ids"
        ],
        "files": manifest_files,
    }
    tmp_paths.manifest_json.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )

    shutil.rmtree(seed_paths.root, ignore_errors=True)
    tmp_root.rename(seed_paths.root)
    return {
        "ok": True,
        "updated": True,
        "seed_root": str(seed_paths.root),
        "profile_dir": str(profile_dir),
        "files": [entry["path"] for entry in manifest_files],
        "distribution_app_profile_extension_ids": collected[
            "distribution_app_profile_extension_ids"
        ],
    }


def collect_seedable_profile_paths(
    profile_dir: Path,
    *,
    allowed_app_profile_extension_ids: list[str] | None = None,
) -> dict[str, object]:
    extensions_json = profile_dir / EXTENSIONS_JSON_NAME
    if not extensions_json.exists():
        return {
            "ok": False,
            "reason": "extensions.json missing",
        }
    try:
        payload = json.loads(extensions_json.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "reason": "extensions.json unreadable",
        }
    addons = payload.get("addons") if isinstance(payload, dict) else None
    if not isinstance(addons, list):
        return {
            "ok": False,
            "reason": "extensions.json addons missing",
        }

    allowed_ids = set(allowed_app_profile_extension_ids or [])
    distribution_ids: list[str] = []
    compatible_seed_ids: list[str] = []
    disallowed_ids: list[str] = []
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        if addon.get("location") != "app-profile":
            continue
        addon_id = addon.get("id")
        if not isinstance(addon_id, str):
            continue
        install_info = addon.get("installTelemetryInfo")
        source = install_info.get("source") if isinstance(install_info, dict) else None
        if source == "distribution":
            distribution_ids.append(addon_id)
        elif addon_id in allowed_ids:
            compatible_seed_ids.append(addon_id)
        else:
            disallowed_ids.append(addon_id)

    if disallowed_ids:
        joined = ", ".join(sorted(disallowed_ids)[:4])
        return {
            "ok": False,
            "reason": f"non-whitelisted app-profile addons present: {joined}",
        }

    selected_ids = sorted(set(distribution_ids) | set(compatible_seed_ids))
    relative_paths: list[Path] = []
    for addon_id in selected_ids:
        relative_path = Path("extensions") / f"{addon_id}.xpi"
        if (profile_dir / relative_path).exists():
            relative_paths.append(relative_path)
    startup_cache = profile_dir / STARTUP_CACHE_RELATIVE_PATH
    if startup_cache.exists() and selected_ids:
        relative_paths.append(STARTUP_CACHE_RELATIVE_PATH)

    return {
        "ok": True,
        "relative_paths": relative_paths,
        "distribution_app_profile_extension_ids": selected_ids,
    }


def seed_manifest_relative_paths(manifest: dict[str, object] | None) -> list[Path]:
    if not isinstance(manifest, dict):
        return []
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    relative_paths: list[Path] = []
    for entry in files:
        if isinstance(entry, str):
            relative_paths.append(Path(entry))
            continue
        if isinstance(entry, dict):
            raw_path = entry.get("path")
            if isinstance(raw_path, str) and raw_path:
                relative_paths.append(Path(raw_path))
    return relative_paths


def manifest_distribution_app_profile_extension_ids(
    manifest: dict[str, object] | None,
) -> list[str]:
    if not isinstance(manifest, dict):
        return []
    value = manifest.get("distribution_app_profile_extension_ids")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def manifest_file_entries(manifest: dict[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(manifest, dict):
        return []
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    entries: list[dict[str, object]] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        entries.append(entry)
    return entries


def browser_seed_manifest_matches_profile(
    *,
    manifest: dict[str, object] | None,
    seed_root: Path,
    profile_dir: Path,
    relative_paths: list[Path],
    distribution_app_profile_extension_ids: list[str],
    preserved_entries: list[dict[str, object]] | None = None,
) -> bool:
    if (
        manifest_distribution_app_profile_extension_ids(manifest)
        != distribution_app_profile_extension_ids
    ):
        return False
    entries = manifest_file_entries(manifest)
    preserved_entries = preserved_entries or []
    if len(entries) != len(relative_paths) + len(preserved_entries):
        return False
    seed_paths = resolve_seed_paths(seed_root)
    entry_by_path = {
        str(entry.get("path")): entry
        for entry in entries
        if isinstance(entry.get("path"), str)
    }
    if len(entry_by_path) != len(entries):
        return False
    for relative_path in relative_paths:
        entry = entry_by_path.get(relative_path.as_posix())
        if entry is None:
            return False
        source = profile_dir / relative_path
        if not source.exists():
            return False
        if not (seed_paths.files_dir / relative_path).exists():
            return False
        source_stat = source.stat()
        if entry.get("bytes") != source_stat.st_size:
            return False
        if entry.get("mtime_ns") != source_stat.st_mtime_ns:
            return False
    for entry in preserved_entries:
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            return False
        manifest_entry = entry_by_path.get(raw_path)
        if manifest_entry is None:
            return False
        if manifest_entry != entry:
            return False
        if not (seed_paths.files_dir / Path(raw_path)).exists():
            return False
    return True


def preserved_seed_entries(
    *,
    manifest: dict[str, object] | None,
    seed_root: Path,
    profile_dir: Path,
    relative_paths: list[Path],
    distribution_app_profile_extension_ids: list[str],
) -> list[dict[str, object]]:
    startup_cache_entry = preserved_startup_cache_entry(
        manifest=manifest,
        seed_root=seed_root,
        profile_dir=profile_dir,
        relative_paths=relative_paths,
        distribution_app_profile_extension_ids=distribution_app_profile_extension_ids,
    )
    if startup_cache_entry is None:
        return []
    return [startup_cache_entry]


def preserved_startup_cache_entry(
    *,
    manifest: dict[str, object] | None,
    seed_root: Path,
    profile_dir: Path,
    relative_paths: list[Path],
    distribution_app_profile_extension_ids: list[str],
) -> dict[str, object] | None:
    if STARTUP_CACHE_RELATIVE_PATH in relative_paths:
        return None
    if not distribution_app_profile_extension_ids:
        return None
    if (
        manifest_distribution_app_profile_extension_ids(manifest)
        != distribution_app_profile_extension_ids
    ):
        return None
    entry_by_path = {
        Path(str(entry["path"])): entry
        for entry in manifest_file_entries(manifest)
        if isinstance(entry.get("path"), str)
    }
    startup_cache_entry = entry_by_path.get(STARTUP_CACHE_RELATIVE_PATH)
    if startup_cache_entry is None:
        return None
    if not (resolve_seed_paths(seed_root).files_dir / STARTUP_CACHE_RELATIVE_PATH).exists():
        return None
    for addon_id in distribution_app_profile_extension_ids:
        relative_path = Path("extensions") / f"{addon_id}.xpi"
        if relative_path not in relative_paths:
            return None
        entry = entry_by_path.get(relative_path)
        if entry is None:
            return None
        source = profile_dir / relative_path
        if not source.exists():
            return None
        source_stat = source.stat()
        if entry.get("bytes") != source_stat.st_size:
            return None
        if entry.get("mtime_ns") != source_stat.st_mtime_ns:
            return None
    return dict(startup_cache_entry)
