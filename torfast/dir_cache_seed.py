"""Helpers for safe C Tor directory-cache seeding."""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
import functools
import hashlib
import json
import os
from pathlib import Path
import shutil
import time


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_C_TOR_DIR_CACHE_SEED_ROOT = REPO_ROOT / "tmp" / "torfast-c-tor-dir-cache-seed"
SEED_FILES_DIRNAME = "files"
SEED_MANIFEST_NAME = "seed.json"

# These are documented CacheDirectory files, not DataDirectory state files.
ALLOWED_CACHE_FILE_NAMES = (
    "cached-certs",
    "cached-consensus",
    "cached-microdesc-consensus",
    "cached-descriptors",
    "cached-descriptors.new",
    "cached-microdescs",
    "cached-microdescs.new",
)


@dataclass(frozen=True)
class DirCacheSeedPaths:
    root: Path
    files_dir: Path
    manifest_json: Path


def resolve_seed_paths(seed_root: Path) -> DirCacheSeedPaths:
    return DirCacheSeedPaths(
        root=seed_root,
        files_dir=seed_root / SEED_FILES_DIRNAME,
        manifest_json=seed_root / SEED_MANIFEST_NAME,
    )


def seedable_cache_paths(data_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for name in ALLOWED_CACHE_FILE_NAMES:
        path = data_dir / name
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            paths.append(path)
    return paths


def has_any_seedable_cache(data_dir: Path) -> bool:
    return bool(seedable_cache_paths(data_dir))


def has_any_files(data_dir: Path) -> bool:
    return any(path.is_file() for path in data_dir.iterdir()) if data_dir.exists() else False


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
    available_files = sorted(
        path.name for path in paths.files_dir.iterdir()
        if paths.files_dir.exists() and path.is_file()
    ) if paths.files_dir.exists() else []
    return {
        "seed_root": str(paths.root),
        "manifest_json": str(paths.manifest_json),
        "present": manifest is not None,
        "available_files": available_files,
        "manifest": manifest,
    }


@functools.lru_cache(maxsize=1)
def _clonefile_function():
    library_name = ctypes.util.find_library("System")
    if not library_name:
        return None
    try:
        library = ctypes.CDLL(library_name)
        clonefile = library.clonefile
    except (AttributeError, OSError):
        return None
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    return clonefile


def copy_file_clone_or_copy2(source: Path, destination: Path) -> str:
    clonefile = _clonefile_function()
    if clonefile is not None:
        result = clonefile(os.fsencode(source), os.fsencode(destination), 0)
        if result == 0:
            shutil.copystat(source, destination)
            return "clone"
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
    shutil.copy2(source, destination)
    return "copy"


def apply_seed_to_data_dir(data_dir: Path, seed_root: Path) -> dict[str, object]:
    paths = resolve_seed_paths(seed_root)
    manifest = read_seed_manifest(seed_root)
    if manifest is None:
        return {
            "ok": True,
            "applied": False,
            "reason": "seed manifest missing",
            "seed_root": str(paths.root),
        }
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
    if has_any_files(data_dir):
        return {
            "ok": True,
            "applied": False,
            "reason": "data dir already has files",
            "seed_root": str(paths.root),
        }
    copied: list[dict[str, object]] = []
    files = manifest.get("files")
    if not isinstance(files, list):
        return {
            "ok": False,
            "applied": False,
            "reason": "seed manifest files entry missing",
            "seed_root": str(paths.root),
        }
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        name = file_entry.get("name")
        if not isinstance(name, str):
            continue
        source = paths.files_dir / name
        if not source.exists():
            return {
                "ok": False,
                "applied": False,
                "reason": f"seed file missing: {source}",
                "seed_root": str(paths.root),
            }
        destination = data_dir / name
        copied_file = copy_seed_file_from_manifest(source, destination, file_entry)
        copied.append(
            {
                "name": name,
                "bytes": copied_file["bytes"],
                "copy_mode": copied_file["copy_mode"],
                "mtime_ns": copied_file["mtime_ns"],
                "sha256": copied_file["sha256"],
            }
        )
    return {
        "ok": True,
        "applied": bool(copied),
        "seed_root": str(paths.root),
        "copied_files": copied,
        "manifest_updated_epoch_ms": manifest.get("updated_epoch_ms"),
    }


def update_seed_from_data_dir(data_dir: Path, seed_root: Path) -> dict[str, object]:
    seed_paths = resolve_seed_paths(seed_root)
    existing_manifest = read_seed_manifest(seed_root)
    existing_entries = {
        str(entry.get("name")): entry
        for entry in manifest_file_entries(existing_manifest)
        if isinstance(entry.get("name"), str)
    }
    cache_paths = seedable_cache_paths(data_dir)
    if not cache_paths:
        return {
            "ok": True,
            "updated": False,
            "reason": "no seedable cache files found",
            "seed_root": str(seed_paths.root),
        }
    if seed_manifest_matches_data_dir(
        manifest=existing_manifest,
        seed_root=seed_root,
        cache_paths=cache_paths,
    ):
        return {
            "ok": True,
            "updated": False,
            "reason": "seed already current",
            "seed_root": str(seed_paths.root),
            "file_count": len(cache_paths),
            "files": manifest_file_entries(existing_manifest),
        }
    tmp_root = seed_paths.root.with_name(seed_paths.root.name + ".tmp")
    shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_paths = resolve_seed_paths(tmp_root)
    tmp_paths.files_dir.mkdir(parents=True, exist_ok=True)

    files: list[dict[str, object]] = []
    reused_files: list[str] = []
    updated_files: list[str] = []
    for source in cache_paths:
        destination = tmp_paths.files_dir / source.name
        existing_entry = existing_entries.get(source.name)
        existing_seed_file = seed_paths.files_dir / source.name
        if existing_entry is not None and seed_entry_matches_source(
            entry=existing_entry,
            source=source,
            seed_file=existing_seed_file,
        ):
            reuse_seed_file(existing_seed_file, destination)
            files.append(dict(existing_entry))
            reused_files.append(source.name)
            continue
        copied_file = copy_file_with_sha256(source, destination)
        files.append(
            {
                "name": source.name,
                "bytes": copied_file["bytes"],
                "mtime_ns": copied_file["mtime_ns"],
                "sha256": copied_file["sha256"],
            }
        )
        updated_files.append(source.name)
    manifest = {
        "updated_epoch_ms": round(time.time() * 1000, 3),
        "source_data_dir": str(data_dir.resolve()),
        "files": files,
    }
    tmp_paths.manifest_json.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(seed_paths.root, ignore_errors=True)
    tmp_root.rename(seed_paths.root)
    return {
        "ok": True,
        "updated": True,
        "seed_root": str(seed_paths.root),
        "file_count": len(files),
        "files": files,
        "reused_files": reused_files,
        "updated_files": updated_files,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def copy_file_with_sha256(source: Path, destination: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    source_stat = source.stat()
    with source.open("rb") as src_handle, destination.open("wb") as dst_handle:
        while True:
            chunk = src_handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            dst_handle.write(chunk)
    shutil.copystat(source, destination)
    return {
        "bytes": source_stat.st_size,
        "mtime_ns": source_stat.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def copy_seed_file_from_manifest(
    source: Path,
    destination: Path,
    manifest_entry: dict[str, object],
) -> dict[str, object]:
    copy_mode = copy_file_clone_or_copy2(source, destination)
    source_stat = source.stat()
    manifest_sha256 = manifest_entry.get("sha256")
    if isinstance(manifest_sha256, str) and manifest_sha256:
        sha256 = manifest_sha256
    else:
        sha256 = sha256_file(source)
    return {
        "bytes": source_stat.st_size,
        "copy_mode": copy_mode,
        "mtime_ns": source_stat.st_mtime_ns,
        "sha256": sha256,
    }


def reuse_seed_file(source: Path, destination: Path) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


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
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        entries.append(entry)
    return entries


def seed_manifest_matches_data_dir(
    *,
    manifest: dict[str, object] | None,
    seed_root: Path,
    cache_paths: list[Path],
) -> bool:
    entries = manifest_file_entries(manifest)
    if len(entries) != len(cache_paths):
        return False
    seed_paths = resolve_seed_paths(seed_root)
    entry_by_name = {
        str(entry.get("name")): entry
        for entry in entries
        if isinstance(entry.get("name"), str)
    }
    if len(entry_by_name) != len(entries):
        return False
    for source in cache_paths:
        entry = entry_by_name.get(source.name)
        if entry is None or not seed_entry_matches_source(
            entry=entry,
            source=source,
            seed_file=seed_paths.files_dir / source.name,
        ):
            return False
    return True


def seed_entry_matches_source(
    *,
    entry: dict[str, object],
    source: Path,
    seed_file: Path,
) -> bool:
    if not seed_file.exists():
        return False
    source_stat = source.stat()
    return (
        entry.get("bytes") == source_stat.st_size
        and entry.get("mtime_ns") == source_stat.st_mtime_ns
    )
