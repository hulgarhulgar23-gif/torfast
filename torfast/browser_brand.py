"""Create the Torfast-branded copy of the verified Tor Browser bundle.

The user-facing identity of the running browser (Dock icon, app name in
Cmd-Tab and menus) comes from the .app bundle, so a launcher alone always
"opens Tor". This module clones the verified Tor Browser bundle to a
torfast-owned copy (APFS clonefile when available, so it costs almost no
disk) and rebrands only OS-level identity surfaces:

- Contents/Info.plist: CFBundleName/CFBundleDisplayName/CFBundleIdentifier
- Contents/Resources/*.lproj/InfoPlist.strings: localized name overrides
- Contents/Resources/firefox.icns: the torfast bolt icon

Nothing content-visible changes: executable code, libraries, omni.ja, defaults,
and every byte a website can measure stay identical to the verified build,
and the source bundle is never touched. Editing signed bundle resources
invalidates Tor Browser's original seal, so the private clone is re-signed
ad hoc for macOS. This rewrites signature metadata in Mach-O files, but not
executable code or browser content.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .app_icon import build_icns

BRANDED_APP_NAME = "Torfast"
BRANDED_BUNDLE_IDENTIFIER = "org.torfast.browser"
BRANDED_BUNDLE_DIRNAME = "Torfast Browser.app"


def branded_browser_bin(target_app: Path) -> Path:
    return target_app / "Contents" / "MacOS" / "firefox"


def source_app_root_for_bin(browser_bin: Path) -> Path | None:
    # .../Something.app/Contents/MacOS/firefox -> .../Something.app
    candidate = browser_bin.resolve().parents[2]
    return candidate if candidate.suffix == ".app" else None


def _clone_bundle(source_app: Path, target_app: Path) -> str:
    completed = subprocess.run(
        ["cp", "-Rc", str(source_app), str(target_app)],
        capture_output=True,
    )
    if completed.returncode == 0:
        return "clonefile"
    if target_app.exists():
        shutil.rmtree(target_app)
    shutil.copytree(source_app, target_app, symlinks=True)
    return "copy"


def _rebrand_info_plist(plist_path: Path) -> dict[str, object]:
    text = plist_path.read_text(encoding="utf-8")
    replacements = {
        "CFBundleName": BRANDED_APP_NAME,
        "CFBundleDisplayName": BRANDED_APP_NAME,
        "CFBundleIdentifier": BRANDED_BUNDLE_IDENTIFIER,
    }
    changed: list[str] = []
    for key, value in replacements.items():
        pattern = rf"(<key>{key}</key>\s*<string>)[^<]*(</string>)"
        (text, count) = re.subn(pattern, rf"\g<1>{value}\g<2>", text)
        if count:
            changed.append(key)
    if "CFBundleDisplayName" not in changed and "CFBundleName" in changed:
        # Tor Browser's plist has no display name; add one so every OS
        # surface (Dock, notifications, Cmd-Tab) agrees on the name.
        text = text.replace(
            f"<key>CFBundleName</key>\n\t<string>{BRANDED_APP_NAME}</string>",
            f"<key>CFBundleName</key>\n\t<string>{BRANDED_APP_NAME}</string>\n"
            f"\t<key>CFBundleDisplayName</key>\n\t<string>{BRANDED_APP_NAME}</string>",
            1,
        )
        changed.append("CFBundleDisplayName(added)")
    plist_path.write_text(text, encoding="utf-8")
    return {"ok": "CFBundleName" in changed, "changed_keys": changed}


def _rebrand_localized_strings(resources_dir: Path) -> list[str]:
    rewritten: list[str] = []
    for strings_path in resources_dir.glob("*.lproj/InfoPlist.strings"):
        # Preserve comments and unrelated localized keys. utf-16 writes the
        # BOM macOS expects; utf-16-le would not.
        text = strings_path.read_text(encoding="utf-16")
        changed = False
        for key in ("CFBundleName", "CFBundleDisplayName"):
            pattern = rf'({key}\s*=\s*")[^"]*("\s*;)'
            (text, count) = re.subn(
                pattern,
                rf"\g<1>{BRANDED_APP_NAME}\g<2>",
                text,
            )
            changed = changed or bool(count)
        if "CFBundleDisplayName" not in text:
            text = f'{text.rstrip()}\nCFBundleDisplayName = "{BRANDED_APP_NAME}";\n'
            changed = True
        if changed:
            strings_path.write_text(text, encoding="utf-16")
            rewritten.append(str(strings_path.relative_to(resources_dir)))
    return rewritten


def create_branded_browser(
    source_app: Path,
    target_app: Path,
    *,
    force: bool = True,
) -> dict[str, object]:
    report: dict[str, object] = {
        "ok": True,
        "source_app": str(source_app),
        "target_app": str(target_app),
        "browser_bin": str(branded_browser_bin(target_app)),
    }
    source_bin = source_app / "Contents" / "MacOS" / "firefox"
    if not source_bin.exists():
        report.update(
            {"ok": False, "reason": f"source browser binary missing: {source_bin}"}
        )
        return report
    if target_app.exists():
        if not force:
            report.update(
                {"ok": False, "reason": f"{target_app} already exists"}
            )
            return report
        shutil.rmtree(target_app)

    target_app.parent.mkdir(parents=True, exist_ok=True)
    report["clone_mode"] = _clone_bundle(source_app, target_app)

    if shutil.which("xattr"):
        subprocess.run(
            ["xattr", "-dr", "com.apple.quarantine", str(target_app)],
            capture_output=True,
        )

    plist_path = target_app / "Contents" / "Info.plist"
    try:
        report["info_plist"] = _rebrand_info_plist(plist_path)
    except (OSError, UnicodeDecodeError) as exc:
        report.update({"ok": False, "reason": f"Info.plist rebrand failed: {exc}"})
        return report
    if not report["info_plist"]["ok"]:
        report.update({"ok": False, "reason": "CFBundleName not found in Info.plist"})
        return report

    resources = target_app / "Contents" / "Resources"
    report["localized_strings"] = _rebrand_localized_strings(resources)

    with tempfile.TemporaryDirectory() as work:
        report["icon"] = build_icns(resources / "firefox.icns", Path(work))

    if shutil.which("codesign"):
        completed = subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(target_app)],
            capture_output=True,
        )
        report["codesign"] = {
            "ok": completed.returncode == 0,
            "detail": completed.stderr.decode("utf-8", "replace")[-300:],
        }
        if completed.returncode != 0:
            report.update({"ok": False, "reason": "ad-hoc codesign failed"})
    else:
        report["codesign"] = {
            "ok": True,
            "skipped": True,
            "reason": "codesign not available",
        }
    return report
