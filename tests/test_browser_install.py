import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast.browser_install import (
    TOR_BROWSER_SIGNING_KEY_FINGERPRINT,
    build_install_plan,
    extract_gpg_fingerprints,
    extract_mount_points,
    parse_signed_checksums_text,
    parse_release_index_versions,
    sha256_file,
)


class BrowserInstallTests(unittest.TestCase):
    def test_build_install_plan_uses_expected_paths_and_urls(self) -> None:
        plan = build_install_plan(
            version="15.0.15",
            install_root=Path("/tmp/browser"),
            downloads_root=Path("/tmp/browser-downloads"),
        )

        self.assertEqual(plan.dmg_name, "tor-browser-macos-15.0.15.dmg")
        self.assertEqual(
            plan.dmg_url,
            "https://dist.torproject.org/torbrowser/15.0.15/tor-browser-macos-15.0.15.dmg",
        )
        self.assertEqual(
            plan.dmg_signature_url,
            "https://dist.torproject.org/torbrowser/15.0.15/tor-browser-macos-15.0.15.dmg.asc",
        )
        self.assertEqual(
            plan.signed_checksums_url,
            "https://dist.torproject.org/torbrowser/15.0.15/sha256sums-signed-build.txt",
        )
        self.assertEqual(
            plan.signed_checksums_signature_url,
            "https://dist.torproject.org/torbrowser/15.0.15/sha256sums-signed-build.txt.asc",
        )
        self.assertEqual(plan.app_path, Path("/tmp/browser/Tor Browser.app"))
        self.assertEqual(
            plan.browser_bin,
            Path("/tmp/browser/Tor Browser.app/Contents/MacOS/firefox"),
        )

    def test_parse_signed_checksums_text_extracts_hashes(self) -> None:
        text = "\n".join(
            [
                "-----BEGIN PGP SIGNED MESSAGE-----",
                "",
                "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  tor-browser-macos-15.0.15.dmg",
                "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789 *other.tar.xz",
            ]
        )

        checksums = parse_signed_checksums_text(text)

        self.assertEqual(
            checksums["tor-browser-macos-15.0.15.dmg"],
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        )
        self.assertEqual(
            checksums["other.tar.xz"],
            "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
        )

    def test_extract_gpg_fingerprints_reads_colons_output(self) -> None:
        output = "\n".join(
            [
                "pub:-:4096:1:4E2C6E8793298290:0:0::-:::scESC::::::23::0:",
                f"fpr:::::::::{TOR_BROWSER_SIGNING_KEY_FINGERPRINT}:",
            ]
        )

        fingerprints = extract_gpg_fingerprints(output)

        self.assertEqual(fingerprints, [TOR_BROWSER_SIGNING_KEY_FINGERPRINT])

    def test_extract_mount_points_reads_hdiutil_plist(self) -> None:
        payload = (
            b'<?xml version="1.0" encoding="UTF-8"?>\n'
            b"<plist version=\"1.0\"><dict><key>system-entities</key><array>"
            b"<dict><key>dev-entry</key><string>/dev/disk4</string></dict>"
            b"<dict><key>mount-point</key><string>/Volumes/Tor Browser</string></dict>"
            b"</array></dict></plist>"
        )

        mount_points = extract_mount_points(payload)

        self.assertEqual(mount_points, [Path("/Volumes/Tor Browser")])

    def test_sha256_file_matches_known_digest(self) -> None:
        path = Path("/tmp/torfast-browser-install-sha256.txt")
        try:
            path.write_text("torfast\n")
            self.assertEqual(
                sha256_file(path),
                "f5bba67e221f9290691f71b010339d37a27f36f64fa4adb90c91405d87e28a36",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_parse_release_index_versions_keeps_only_stable_releases(self) -> None:
        html = "\n".join(
            [
                '<a href="15.0.16/">15.0.16/</a>',
                '<a href="16.0a7/">16.0a7/</a>',
                '<a href="14.5.2/">14.5.2/</a>',
            ]
        )

        versions = parse_release_index_versions(html)

        self.assertEqual(versions, ["14.5.2", "15.0.16"])


if __name__ == "__main__":
    unittest.main()
