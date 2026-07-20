import tempfile
import unittest
from pathlib import Path

from torfast.browser_brand import (
    BRANDED_APP_NAME,
    BRANDED_BUNDLE_IDENTIFIER,
    branded_browser_bin,
    create_branded_browser,
    source_app_root_for_bin,
)

FAKE_INFO_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
	<key>CFBundleIconFile</key>
	<string>firefox.icns</string>
	<key>CFBundleIdentifier</key>
	<string>org.torproject.torbrowser</string>
	<key>CFBundleName</key>
	<string>Tor Browser</string>
</dict>
</plist>
"""


def make_fake_bundle(root: Path) -> Path:
    app = root / "Tor Browser.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources" / "en.lproj").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text(FAKE_INFO_PLIST)
    (app / "Contents" / "MacOS" / "firefox").write_text("#!/bin/zsh\n")
    (app / "Contents" / "Resources" / "firefox.icns").write_bytes(b"onion")
    (app / "Contents" / "Resources" / "en.lproj" / "InfoPlist.strings").write_text(
        "/* Keep this localized metadata comment. */\n"
        'CFBundleName = "Tor Browser";\n'
        'UnrelatedKey = "Unchanged";\n',
        encoding="utf-16",
    )
    return app


class BrowserBrandTests(unittest.TestCase):
    def test_source_app_root_for_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = make_fake_bundle(Path(tmp))
            bin_path = app / "Contents" / "MacOS" / "firefox"
            self.assertEqual(source_app_root_for_bin(bin_path), app.resolve())

    def test_rebrand_changes_identity_not_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_fake_bundle(Path(tmp))
            target = Path(tmp) / "Torfast Browser.app"
            source_bin = source / "Contents" / "MacOS" / "firefox"
            report = create_branded_browser(source, target)
            self.assertTrue(report["ok"], report)

            plist = (target / "Contents" / "Info.plist").read_text()
            self.assertIn(f"<string>{BRANDED_APP_NAME}</string>", plist)
            self.assertIn(BRANDED_BUNDLE_IDENTIFIER, plist)
            self.assertNotIn("Tor Browser", plist)

            strings_path = (
                target / "Contents" / "Resources" / "en.lproj" / "InfoPlist.strings"
            )
            self.assertTrue(strings_path.read_bytes().startswith(b"\xff\xfe"))
            strings = strings_path.read_text(encoding="utf-16")
            self.assertIn(f'CFBundleName = "{BRANDED_APP_NAME}"', strings)
            self.assertIn(f'CFBundleDisplayName = "{BRANDED_APP_NAME}"', strings)
            self.assertIn("Keep this localized metadata comment", strings)
            self.assertIn('UnrelatedKey = "Unchanged"', strings)

            # Executable layout and payload remain present. On macOS,
            # codesign may rewrite only the embedded Mach-O signature region.
            target_bin = branded_browser_bin(target)
            self.assertTrue(target_bin.exists())
            self.assertEqual(target_bin.read_text(), source_bin.read_text())
            self.assertTrue(report["codesign"]["ok"])

            # the source bundle keeps its stock identity
            source_plist = (source / "Contents" / "Info.plist").read_text()
            self.assertIn("Tor Browser", source_plist)
            source_strings = (
                source / "Contents" / "Resources" / "en.lproj" / "InfoPlist.strings"
            ).read_text(encoding="utf-16")
            self.assertIn("Tor Browser", source_strings)

    def test_rebrand_replaces_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_fake_bundle(Path(tmp))
            target = Path(tmp) / "Torfast Browser.app"
            self.assertTrue(create_branded_browser(source, target)["ok"])
            self.assertTrue(create_branded_browser(source, target)["ok"])

    def test_missing_source_binary_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = create_branded_browser(
                Path(tmp) / "Missing.app", Path(tmp) / "Out.app"
            )
            self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
