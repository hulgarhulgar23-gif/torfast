import re
import tempfile
import unittest
from pathlib import Path

from torfast.theme import (
    THEME_PREF_LINE,
    ZEN_USERCHROME_CSS,
    apply_ui_theme_to_profile,
)

# Properties that would change chrome layout metrics and therefore the
# content viewport websites can measure. The zen theme must never use
# them; only colors, radii, shadows, outlines, opacity, and transitions
# are geometry-safe.
FORBIDDEN_CSS_PATTERNS = (
    r"\bdisplay\s*:",
    r"\bvisibility\s*:",
    r"[^-]\bborder\s*:",
    r"\bborder-width\s*:",
    r"\bborder-top\s*:",
    r"\bborder-bottom\s*:",
    r"(?<!(--torfast-))height\s*:",
    r"(?<!outline-)(?<!border-)(?<!--torfast-)width\s*:",
    r"\bpadding[^:]*:",
    r"\bmargin[^:]*:",
    r"\bposition\s*:",
    r"\bfont-size\s*:",
    r"\btop\s*:",
    r"\bbottom\s*:",
)


def css_without_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", ZEN_USERCHROME_CSS, flags=re.DOTALL)


class ZenCssSafetyTests(unittest.TestCase):
    def test_css_contains_no_geometry_changing_properties(self) -> None:
        css = css_without_comments()
        for pattern in FORBIDDEN_CSS_PATTERNS:
            match = re.search(pattern, css)
            self.assertIsNone(
                match,
                f"geometry-unsafe css matched {pattern!r}: "
                f"{match.group(0) if match else ''}",
            )

    def test_css_documents_the_geometry_rule(self) -> None:
        self.assertIn("geometry-safe", ZEN_USERCHROME_CSS)

    def test_css_styles_the_core_chrome_surfaces(self) -> None:
        for selector in ("#navigator-toolbox", ".tab-background", "#urlbar-background"):
            self.assertIn(selector, ZEN_USERCHROME_CSS)


class ApplyThemeTests(unittest.TestCase):
    def test_apply_writes_userchrome_and_pref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            report = apply_ui_theme_to_profile(profile_dir)
            self.assertTrue(report["ok"])
            self.assertTrue(report["applied"])
            self.assertEqual(report["theme"], "zen")
            css = (profile_dir / "chrome" / "userChrome.css").read_text()
            self.assertEqual(css, ZEN_USERCHROME_CSS)
            user_js = (profile_dir / "user.js").read_text()
            self.assertIn(THEME_PREF_LINE, user_js)

    def test_apply_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            apply_ui_theme_to_profile(profile_dir)
            apply_ui_theme_to_profile(profile_dir)
            user_js = (profile_dir / "user.js").read_text()
            self.assertEqual(user_js.count(THEME_PREF_LINE), 1)

    def test_apply_preserves_existing_user_js_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            existing = 'user_pref("keep.me", true);\n'
            (profile_dir / "user.js").write_text(existing)
            apply_ui_theme_to_profile(profile_dir)
            user_js = (profile_dir / "user.js").read_text()
            self.assertIn('user_pref("keep.me", true);', user_js)
            self.assertIn(THEME_PREF_LINE, user_js)

    def test_theme_only_touches_chrome_files(self) -> None:
        # The theme must never write content-visible files (userContent.css
        # styles web pages and would break fingerprint equality).
        with tempfile.TemporaryDirectory() as tmp:
            profile_dir = Path(tmp)
            apply_ui_theme_to_profile(profile_dir)
            written = sorted(
                str(path.relative_to(profile_dir))
                for path in profile_dir.rglob("*")
                if path.is_file()
            )
            self.assertEqual(written, ["chrome/userChrome.css", "user.js"])


if __name__ == "__main__":
    unittest.main()
