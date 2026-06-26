import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


from torfast.browser_defaults import (
    read_browser_default_prefs,
)


TOR_PREFS_V1 = """
pref("browser.privatebrowsing.autostart", true);
pref("extensions.torbutton.use_nontor_proxy", false);
pref("network.dns.disabled", true);
pref("network.http.http3.enable", false);
pref("network.proxy.allow_bypass", false);
pref("network.proxy.failover_direct", false);
pref("network.proxy.no_proxies_on", "");
pref("network.proxy.socks_remote_dns", true);
pref("privacy.firstparty.isolate", true);
pref("privacy.resistFingerprinting", true);
pref("privacy.resistFingerprinting.letterboxing", true);
"""


TOR_PREFS_V2 = TOR_PREFS_V1.replace(
    'pref("privacy.resistFingerprinting", true);',
    'pref("privacy.resistFingerprinting", false);',
)


def write_test_omni(omni_path: Path, pref_text: str) -> None:
    omni_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(omni_path, "w") as archive:
        archive.writestr("defaults/preferences/000-tor-browser.js", pref_text)


class BrowserDefaultsTests(unittest.TestCase):
    def test_read_browser_default_prefs_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser_bin = root / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("")
            omni = (
                browser_bin.parent.parent
                / "Resources"
                / "browser"
                / "omni.ja"
            )
            write_test_omni(omni, TOR_PREFS_V1)
            cache_dir = root / "cache"

            with mock.patch("torfast.browser_defaults.DEFAULT_PREF_CACHE_DIR", cache_dir):
                result = read_browser_default_prefs(browser_bin)

            self.assertTrue(result["ok"])
            self.assertFalse(result["cache_hit"])
            cache_path = Path(str(result["cache_path"]))
            self.assertTrue(cache_path.exists())

    def test_read_browser_default_prefs_uses_cache_when_source_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser_bin = root / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("")
            omni = (
                browser_bin.parent.parent
                / "Resources"
                / "browser"
                / "omni.ja"
            )
            write_test_omni(omni, TOR_PREFS_V1)
            cache_dir = root / "cache"

            with mock.patch("torfast.browser_defaults.DEFAULT_PREF_CACHE_DIR", cache_dir):
                first = read_browser_default_prefs(browser_bin)
                self.assertFalse(first["cache_hit"])
                with mock.patch(
                    "torfast.browser_defaults.zipfile.ZipFile",
                    side_effect=AssertionError("should use cached proof"),
                ):
                    second = read_browser_default_prefs(browser_bin)

            self.assertTrue(second["ok"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(second["prefs"], first["prefs"])

    def test_read_browser_default_prefs_invalidates_cache_when_omni_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            browser_bin = root / "Tor Browser.app" / "Contents" / "MacOS" / "firefox"
            browser_bin.parent.mkdir(parents=True, exist_ok=True)
            browser_bin.write_text("")
            omni = (
                browser_bin.parent.parent
                / "Resources"
                / "browser"
                / "omni.ja"
            )
            write_test_omni(omni, TOR_PREFS_V1)
            cache_dir = root / "cache"

            with mock.patch("torfast.browser_defaults.DEFAULT_PREF_CACHE_DIR", cache_dir):
                first = read_browser_default_prefs(browser_bin)
                self.assertFalse(first["cache_hit"])
                write_test_omni(omni, TOR_PREFS_V2)
                second = read_browser_default_prefs(browser_bin)

            self.assertTrue(second["ok"])
            self.assertFalse(second["cache_hit"])
            self.assertFalse(second["prefs"]["privacy.resistFingerprinting"])


if __name__ == "__main__":
    unittest.main()
