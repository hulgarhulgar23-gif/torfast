import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast.term import (
    Spinner,
    color_enabled,
    format_seconds,
    human_output_enabled,
    presence_symbol,
    render_check_line,
    render_panel,
    render_wordmark,
    status_symbol,
    style,
)


class FakeTty(io.StringIO):
    def isatty(self) -> bool:
        return True


class StyleTests(unittest.TestCase):
    def test_style_disabled_returns_plain_text(self) -> None:
        self.assertEqual(style("hello", "bold", "green", enabled=False), "hello")

    def test_style_enabled_wraps_with_codes_and_reset(self) -> None:
        styled = style("hello", "bold", enabled=True)
        self.assertIn("hello", styled)
        self.assertTrue(styled.startswith("\x1b[1m"))
        self.assertTrue(styled.endswith("\x1b[0m"))

    def test_status_symbol_plain_mode_has_no_ansi(self) -> None:
        self.assertEqual(status_symbol(True, enabled=False), "✓")
        self.assertEqual(status_symbol(False, enabled=False), "✗")
        self.assertEqual(status_symbol(None, enabled=False), "✗")

    def test_presence_symbol_plain_mode(self) -> None:
        self.assertEqual(presence_symbol(True, enabled=False), "●")
        self.assertEqual(presence_symbol(False, enabled=False), "○")

    def test_format_seconds(self) -> None:
        self.assertEqual(format_seconds(4.51), "4.5s")
        self.assertEqual(format_seconds(None), "-")
        self.assertEqual(format_seconds("x"), "-")

    def test_wordmark_is_multiline(self) -> None:
        self.assertEqual(len(render_wordmark(enabled=False).splitlines()), 2)


class ColorEnabledTests(unittest.TestCase):
    def test_no_color_env_disables_color_even_on_tty(self) -> None:
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(color_enabled(FakeTty()))

    def test_dumb_term_disables_color(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        env["TERM"] = "dumb"
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(color_enabled(FakeTty()))

    def test_tty_without_no_color_enables_color(self) -> None:
        env = {
            k: v for k, v in os.environ.items() if k not in {"NO_COLOR", "TERM"}
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(color_enabled(FakeTty()))

    def test_non_tty_disables_color(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertFalse(color_enabled(io.StringIO()))


class HumanOutputEnabledTests(unittest.TestCase):
    def test_json_flag_forces_machine_output(self) -> None:
        args = mock.Mock(json=True)
        self.assertFalse(human_output_enabled(args, FakeTty()))

    def test_tty_without_json_flag_is_human(self) -> None:
        args = mock.Mock(json=False)
        self.assertTrue(human_output_enabled(args, FakeTty()))

    def test_pipe_is_machine_output(self) -> None:
        args = mock.Mock(json=False)
        self.assertFalse(human_output_enabled(args, io.StringIO()))


class RenderTests(unittest.TestCase):
    def test_render_panel_aligns_labels(self) -> None:
        panel = render_panel(
            "title",
            [("a", "1"), ("longer", "2")],
            enabled=False,
        )
        lines = panel.splitlines()
        self.assertEqual(lines[0], "title")
        self.assertEqual(lines[1], "  a       1")
        self.assertEqual(lines[2], "  longer  2")

    def test_render_check_line_with_detail(self) -> None:
        line = render_check_line(True, "thing", "detail", enabled=False)
        self.assertEqual(line, "  ✓ thing  detail")


class SpinnerTests(unittest.TestCase):
    def test_spinner_is_silent_on_non_tty(self) -> None:
        stream = io.StringIO()
        with Spinner("working", stream=stream, interval=0.01) as spinner:
            self.assertFalse(spinner.enabled)
        self.assertEqual(stream.getvalue(), "")

    def test_spinner_writes_and_clears_on_tty(self) -> None:
        stream = FakeTty()
        env = {k: v for k, v in os.environ.items() if k != "TERM"}
        with mock.patch.dict(os.environ, env, clear=True):
            with Spinner("working", stream=stream, interval=0.005):
                import time

                time.sleep(0.05)
        output = stream.getvalue()
        self.assertIn("working", output)
        self.assertTrue(output.endswith("\r\x1b[2K"))

    def test_spinner_reports_elapsed_seconds(self) -> None:
        with Spinner("x", stream=io.StringIO()) as spinner:
            pass
        self.assertGreaterEqual(spinner.elapsed_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
