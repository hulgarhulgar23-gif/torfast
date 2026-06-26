"""Verified Tor Browser fetch and install helpers for the tor-fast runtime."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .browser_defaults import read_browser_default_prefs, validate_default_prefs


TOR_BROWSER_DOWNLOAD_BASE = "https://dist.torproject.org/torbrowser"
TOR_BROWSER_SIGNING_KEY_FINGERPRINT = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
TOR_BROWSER_SIGNING_KEY_URL = (
    "https://keys.openpgp.org/vks/v1/by-fingerprint/"
    + TOR_BROWSER_SIGNING_KEY_FINGERPRINT
)
TOR_BROWSER_APP_NAME = "Tor Browser.app"


class BrowserInstallError(RuntimeError):
    """Raised when Tor Browser install or verification fails."""


@dataclass(frozen=True)
class BrowserInstallPlan:
    version: str
    install_root: Path
    downloads_root: Path
    downloads_dir: Path
    app_path: Path
    browser_bin: Path
    manifest_json: Path
    dmg_name: str
    dmg_path: Path
    dmg_signature_path: Path
    signed_checksums_path: Path
    signed_checksums_signature_path: Path
    public_key_path: Path
    dmg_url: str
    dmg_signature_url: str
    signed_checksums_url: str
    signed_checksums_signature_url: str
    public_key_url: str

    def as_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "install_root": str(self.install_root),
            "downloads_root": str(self.downloads_root),
            "downloads_dir": str(self.downloads_dir),
            "app_path": str(self.app_path),
            "browser_bin": str(self.browser_bin),
            "manifest_json": str(self.manifest_json),
            "dmg_name": self.dmg_name,
            "dmg_path": str(self.dmg_path),
            "dmg_signature_path": str(self.dmg_signature_path),
            "signed_checksums_path": str(self.signed_checksums_path),
            "signed_checksums_signature_path": str(
                self.signed_checksums_signature_path
            ),
            "public_key_path": str(self.public_key_path),
            "dmg_url": self.dmg_url,
            "dmg_signature_url": self.dmg_signature_url,
            "signed_checksums_url": self.signed_checksums_url,
            "signed_checksums_signature_url": self.signed_checksums_signature_url,
            "public_key_url": self.public_key_url,
            "signing_key_fingerprint": TOR_BROWSER_SIGNING_KEY_FINGERPRINT,
        }


def build_install_plan(
    *,
    version: str,
    install_root: Path,
    downloads_root: Path,
    public_key_url: str = TOR_BROWSER_SIGNING_KEY_URL,
) -> BrowserInstallPlan:
    dmg_name = f"tor-browser-macos-{version}.dmg"
    downloads_dir = downloads_root / version
    base_url = f"{TOR_BROWSER_DOWNLOAD_BASE}/{version}"
    app_path = install_root / TOR_BROWSER_APP_NAME
    return BrowserInstallPlan(
        version=version,
        install_root=install_root,
        downloads_root=downloads_root,
        downloads_dir=downloads_dir,
        app_path=app_path,
        browser_bin=app_path / "Contents" / "MacOS" / "firefox",
        manifest_json=install_root / "tor-browser-install.json",
        dmg_name=dmg_name,
        dmg_path=downloads_dir / dmg_name,
        dmg_signature_path=downloads_dir / f"{dmg_name}.asc",
        signed_checksums_path=downloads_dir / "sha256sums-signed-build.txt",
        signed_checksums_signature_path=downloads_dir
        / "sha256sums-signed-build.txt.asc",
        public_key_path=downloads_dir / "tor-browser-signing-key.asc",
        dmg_url=f"{base_url}/{dmg_name}",
        dmg_signature_url=f"{base_url}/{dmg_name}.asc",
        signed_checksums_url=f"{base_url}/sha256sums-signed-build.txt",
        signed_checksums_signature_url=f"{base_url}/sha256sums-signed-build.txt.asc",
        public_key_url=public_key_url,
    )


def parse_release_index_versions(text: str) -> list[str]:
    versions = {
        match.group(1)
        for match in re.finditer(r'href="((\d+)\.(\d+)\.(\d+))/?"', text)
        if re.fullmatch(r"\d+\.\d+\.\d+", match.group(1))
    }
    return sorted(versions, key=version_sort_key)


def version_sort_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def resolve_browser_version(version: str) -> str:
    requested = version.strip()
    if requested.lower() not in {"latest", "stable"}:
        return requested
    completed = run_checked(["curl", "-fsSL", f"{TOR_BROWSER_DOWNLOAD_BASE}/"])
    assert isinstance(completed.stdout, str)
    versions = parse_release_index_versions(completed.stdout)
    if not versions:
        raise BrowserInstallError("could not find any stable Tor Browser releases")
    return versions[-1]


def parse_signed_checksums_text(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    pattern = re.compile(r"^([0-9a-fA-F]{64})\s+\*?(.+)$")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = pattern.match(line)
        if not match:
            continue
        checksums[Path(match.group(2)).name] = match.group(1).lower()
    return checksums


def extract_gpg_fingerprints(text: str) -> list[str]:
    fingerprints: list[str] = []
    for line in text.splitlines():
        if not line.startswith("fpr:"):
            continue
        fields = line.split(":")
        if len(fields) > 9 and fields[9]:
            fingerprints.append(fields[9].upper())
    return fingerprints


def extract_mount_points(plist_payload: bytes) -> list[Path]:
    pattern = re.compile(rb"<key>mount-point</key>\s*<string>(.*?)</string>", re.DOTALL)
    mount_points: list[Path] = []
    for match in pattern.finditer(plist_payload):
        mount_point = html.unescape(match.group(1).decode("utf-8", errors="replace"))
        mount_points.append(Path(mount_point))
    return mount_points


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def install_browser(
    *,
    version: str,
    install_root: Path,
    downloads_root: Path,
    public_key_url: str = TOR_BROWSER_SIGNING_KEY_URL,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, object]:
    resolved_version = resolve_browser_version(version)
    plan = build_install_plan(
        version=resolved_version,
        install_root=install_root,
        downloads_root=downloads_root,
        public_key_url=public_key_url,
    )
    if dry_run:
        return {"ok": True, "dry_run": True, "plan": plan.as_dict()}

    ensure_required_commands()
    if plan.app_path.exists():
        if not force:
            verification = verify_installed_browser(plan.app_path)
            report = {
                "ok": True,
                "version": resolved_version,
                "installed": False,
                "reused_existing": True,
                "downloads": {},
                "plan": plan.as_dict(),
                "verification": verification,
            }
            plan.manifest_json.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            return report
        shutil.rmtree(plan.app_path)
    if plan.manifest_json.exists() and force:
        plan.manifest_json.unlink()

    plan.install_root.mkdir(parents=True, exist_ok=True)
    plan.downloads_dir.mkdir(parents=True, exist_ok=True)

    downloads = {
        "dmg": download_file(plan.dmg_url, plan.dmg_path),
        "dmg_signature": download_file(plan.dmg_signature_url, plan.dmg_signature_path),
        "signed_checksums": download_file(
            plan.signed_checksums_url, plan.signed_checksums_path
        ),
        "signed_checksums_signature": download_file(
            plan.signed_checksums_signature_url, plan.signed_checksums_signature_path
        ),
        "public_key": download_file(plan.public_key_url, plan.public_key_path),
    }

    with tempfile.TemporaryDirectory(prefix="torfast-gpg-") as temp_dir_name:
        gpg_home = Path(temp_dir_name) / "gnupg"
        gpg_home.mkdir(mode=0o700)
        import_signing_key(gpg_home, plan.public_key_path)
        verify_detached_signature(gpg_home, plan.dmg_signature_path, plan.dmg_path)
        verify_detached_signature(
            gpg_home,
            plan.signed_checksums_signature_path,
            plan.signed_checksums_path,
        )

    checksums = parse_signed_checksums_text(plan.signed_checksums_path.read_text())
    expected_sha256 = checksums.get(plan.dmg_name)
    if expected_sha256 is None:
        raise BrowserInstallError(
            f"signed checksums did not include {plan.dmg_name}"
        )
    actual_sha256 = sha256_file(plan.dmg_path)
    if actual_sha256 != expected_sha256:
        raise BrowserInstallError(
            "downloaded dmg checksum mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    mount_points: list[Path] = []
    try:
        mount_points = attach_dmg(plan.dmg_path)
        source_app = locate_mounted_app(mount_points)
        copy_app_bundle(source_app, plan.app_path)
    finally:
        detach_mount_points(mount_points)

    verification = verify_installed_browser(plan.app_path)

    report = {
        "ok": True,
        "version": resolved_version,
        "installed": True,
        "downloads": downloads,
        "plan": plan.as_dict(),
        "verification": {
            **verification,
            "signature_verified": True,
            "checksums_verified": True,
            "expected_sha256": expected_sha256,
            "actual_sha256": actual_sha256,
        },
    }
    plan.manifest_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def ensure_required_commands() -> None:
    missing = [
        name
        for name in ("curl", "ditto", "gpg", "hdiutil", "codesign", "spctl")
        if shutil.which(name) is None
    ]
    if missing:
        raise BrowserInstallError(
            "required commands not found: " + ", ".join(sorted(missing))
        )


def run_checked(
    command: list[str],
    *,
    text: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=text,
            check=False,
        )
    except OSError as exc:
        raise BrowserInstallError(f"{command[0]} failed to start: {exc}") from exc
    if completed.returncode == 0:
        return completed
    if text:
        assert isinstance(completed.stderr, str)
        assert isinstance(completed.stdout, str)
        detail = (completed.stderr or completed.stdout).strip()
    else:
        assert isinstance(completed.stderr, bytes)
        assert isinstance(completed.stdout, bytes)
        detail = (completed.stderr or completed.stdout).decode(
            "utf-8", errors="replace"
        ).strip()
    raise BrowserInstallError(
        f"{command[0]} failed with exit code {completed.returncode}: {detail}"
    )


def download_file(url: str, path: Path) -> dict[str, object]:
    cached = path.exists()
    if not cached:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            run_checked(["curl", "-fsSL", "--retry", "3", "-o", str(path), url])
        except BrowserInstallError as exc:
            raise BrowserInstallError(f"download failed for {url}: {exc}") from exc
    return {"url": url, "path": str(path), "cached": cached}


def import_signing_key(gpg_home: Path, public_key_path: Path) -> None:
    run_checked(
        ["gpg", "--batch", "--homedir", str(gpg_home), "--import", str(public_key_path)]
    )
    completed = run_checked(
        [
            "gpg",
            "--batch",
            "--homedir",
            str(gpg_home),
            "--with-colons",
            "--fingerprint",
        ]
    )
    assert isinstance(completed.stdout, str)
    fingerprints = extract_gpg_fingerprints(completed.stdout)
    if TOR_BROWSER_SIGNING_KEY_FINGERPRINT not in fingerprints:
        raise BrowserInstallError(
            "imported signing key fingerprint mismatch: "
            + ", ".join(fingerprints or ["<none>"])
        )


def verify_detached_signature(
    gpg_home: Path,
    signature_path: Path,
    content_path: Path,
) -> None:
    run_checked(
        [
            "gpg",
            "--batch",
            "--homedir",
            str(gpg_home),
            "--verify",
            str(signature_path),
            str(content_path),
        ]
    )


def attach_dmg(dmg_path: Path) -> list[Path]:
    completed = run_checked(
        [
            "hdiutil",
            "attach",
            str(dmg_path),
            "-nobrowse",
            "-readonly",
            "-plist",
        ],
        text=False,
    )
    assert isinstance(completed.stdout, bytes)
    mount_points = extract_mount_points(completed.stdout)
    if not mount_points:
        raise BrowserInstallError(f"no mount points found for {dmg_path}")
    return mount_points


def locate_mounted_app(mount_points: list[Path]) -> Path:
    for mount_point in mount_points:
        candidate = mount_point / TOR_BROWSER_APP_NAME
        if candidate.exists():
            return candidate
    raise BrowserInstallError(
        "mounted dmg did not contain Tor Browser.app at its root"
    )


def copy_app_bundle(source_app: Path, destination_app: Path) -> None:
    run_checked(["ditto", str(source_app), str(destination_app)])


def detach_mount_points(mount_points: list[Path]) -> None:
    for mount_point in reversed(mount_points):
        try:
            run_checked(["hdiutil", "detach", str(mount_point)])
        except BrowserInstallError:
            continue


def verify_codesign(app_path: Path) -> None:
    run_checked(["codesign", "--verify", "--deep", "--strict", str(app_path)])


def verify_notarization(app_path: Path) -> None:
    run_checked(["spctl", "--assess", "--type", "execute", str(app_path)])


def verify_installed_browser(app_path: Path) -> dict[str, object]:
    browser_bin = app_path / "Contents" / "MacOS" / "firefox"
    verify_codesign(app_path)
    verify_notarization(app_path)
    default_pref_proof = read_browser_default_prefs(browser_bin)
    default_pref_check = validate_default_prefs(default_pref_proof)
    if not default_pref_check.get("ok"):
        failures = default_pref_check.get("failures", [])
        raise BrowserInstallError(
            "installed browser default pref check failed: " + "; ".join(failures)
        )
    return {
        "codesign_verified": True,
        "notarization_verified": True,
        "default_pref_proof": default_pref_proof,
        "default_pref_check": default_pref_check,
    }
