import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from render_terminal_demo import DEFAULT_OUTPUT, demo_script, render_svg


class TerminalDemoTests(unittest.TestCase):
    def test_render_is_deterministic(self) -> None:
        self.assertEqual(
            render_svg(demo_script()),
            render_svg(demo_script()),
        )

    def test_committed_asset_matches_generator(self) -> None:
        """The SVG is generated, never hand-edited; regenerate on change."""
        self.assertTrue(DEFAULT_OUTPUT.exists(), str(DEFAULT_OUTPUT))
        self.assertEqual(
            DEFAULT_OUTPUT.read_text(),
            render_svg(demo_script()) + "\n",
        )

    def test_svg_structure_is_balanced(self) -> None:
        svg = render_svg(demo_script())
        self.assertTrue(svg.startswith("<svg "))
        self.assertTrue(svg.endswith("</svg>"))
        self.assertEqual(svg.count("<text"), svg.count("</text>"))
        self.assertEqual(svg.count("<tspan"), svg.count("</tspan>"))
        # every ampersand must belong to an entity
        for match in re.finditer(r"&", svg):
            self.assertRegex(
                svg[match.start() : match.start() + 6],
                r"&(amp|lt|gt|quot|apos);",
            )

    def test_demo_shows_verified_numbers_and_proof(self) -> None:
        svg = render_svg(demo_script())
        self.assertIn("torfast open --url https://check.torproject.org/", svg)
        self.assertIn("4.4s", svg)
        self.assertIn("11.2s", svg)
        self.assertIn("torfast-promoted-quality-check-20260707T002336", svg)
        self.assertIn("30/30 quality gates", svg)

    def test_transient_lines_are_hidden_without_animation(self) -> None:
        svg = render_svg(demo_script())
        transient_classes = re.findall(r'class="(l\d+) transient"', svg)
        self.assertGreaterEqual(len(transient_classes), 1)
        for name in transient_classes:
            self.assertIn(f".{name} {{ opacity: 0;", svg)
        self.assertIn("prefers-reduced-motion", svg)

    def test_rows_can_be_shared_without_growing_height(self) -> None:
        script = demo_script()
        rows = [line.row for line in script.lines]
        self.assertLess(script.row_count, len(script.lines) + 1)
        self.assertEqual(sorted(set(rows)), list(range(script.row_count)))


if __name__ == "__main__":
    unittest.main()
