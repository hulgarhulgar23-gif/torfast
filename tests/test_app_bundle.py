import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from torfast.app_bundle import (
    APP_NAME,
    BUNDLE_IDENTIFIER,
    QUICK_ACTION_NAME,
    install_app,
    install_summon_service,
)
from torfast.app_icon import render_master_png


def read_png_size(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", payload[16:24])
    return width, height


class AppIconTests(unittest.TestCase):
    def test_master_png_is_valid_and_square(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "icon.png"
            render_master_png(target, size=64)
            self.assertEqual(read_png_size(target), (64, 64))
            # decompressing the image data proves the chunk layout is sound
            payload = target.read_bytes()
            idat_start = payload.index(b"IDAT") + 4
            idat_length = struct.unpack(">I", payload[idat_start - 8 : idat_start - 4])[0]
            raw = zlib.decompress(payload[idat_start : idat_start + idat_length])
            self.assertEqual(len(raw), 64 * (64 * 4 + 1))

    def test_icon_draws_bolt_over_tile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "icon.png"
            render_master_png(target, size=64)
            payload = target.read_bytes()
            idat_start = payload.index(b"IDAT") + 4
            idat_length = struct.unpack(">I", payload[idat_start - 8 : idat_start - 4])[0]
            raw = zlib.decompress(payload[idat_start : idat_start + idat_length])
            stride = 64 * 4 + 1
            colors = set()
            for y in range(64):
                row = raw[y * stride + 1 : (y + 1) * stride]
                for x in range(64):
                    pixel = tuple(row[x * 4 : x * 4 + 4])
                    if pixel[3] != 0:
                        colors.add(pixel[:3])
            self.assertIn((196, 178, 248), colors)  # bolt
            self.assertGreater(len(colors), 2)  # gradient tile


class InstallAppTests(unittest.TestCase):
    def test_install_creates_launchable_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "apps"
            services = Path(tmp) / "services"
            dest.mkdir()
            report = install_app(
                dest_root=dest,
                python_executable="/usr/bin/python3",
                repo_root=Path("/opt/torfast-repo"),
                version="9.9.9",
                services_dir=services,
                include_icon=False,
                browser_bin="/opt/branded/Contents/MacOS/firefox",
            )
            self.assertTrue(report["ok"])
            app = dest / f"{APP_NAME}.app"
            info = (app / "Contents" / "Info.plist").read_text()
            self.assertIn(BUNDLE_IDENTIFIER, info)
            self.assertIn("9.9.9", info)
            launcher = app / "Contents" / "MacOS" / "torfast"
            script = launcher.read_text()
            self.assertIn('cd "/opt/torfast-repo" || exit 1', script)
            self.assertIn('"/usr/bin/python3" -m torfast open --json', script)
            # app behavior contract: focus when open, no-op while opening,
            # detached launch otherwise
            self.assertIn("set frontmost", script)
            # bracket-trick patterns so the guards never match a process
            # that merely mentions them
            self.assertIn('pgrep -f "[-]m torfast open"', script)
            self.assertIn('pgrep -f "[M]acOS/firefox', script)
            self.assertIn("&!", script)
            self.assertIn(
                'export TORFAST_BROWSER_BIN="/opt/branded/Contents/MacOS/firefox"',
                script,
            )
            self.assertTrue(launcher.stat().st_mode & 0o111)

    def test_install_refuses_existing_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / f"{APP_NAME}.app").mkdir()
            report = install_app(
                dest_root=dest,
                include_summon_service=False,
                include_icon=False,
            )
            self.assertFalse(report["ok"])
            self.assertIn("--force", str(report["reason"]))
            report = install_app(
                dest_root=dest,
                force=True,
                include_summon_service=False,
                include_icon=False,
            )
            self.assertTrue(report["ok"])

    def test_summon_service_workflow_contents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            services = Path(tmp)
            report = install_summon_service(
                app_path=Path("/Applications/Torfast.app"),
                services_dir=services,
            )
            self.assertTrue(report["ok"])
            workflow = services / f"{QUICK_ACTION_NAME}.workflow" / "Contents"
            info = (workflow / "Info.plist").read_text()
            self.assertIn(QUICK_ACTION_NAME, info)
            self.assertIn("runWorkflowAsService", info)
            document = (workflow / "document.wflow").read_text()
            self.assertIn('/usr/bin/open "/Applications/Torfast.app"', document)
            self.assertIn("com.apple.Automator.servicesMenu", document)
            self.assertIn("com.apple.Automator.nothing", document)


class InstallAppCliTests(unittest.TestCase):
    def test_cli_install_app_json(self) -> None:
        import io
        import json
        from contextlib import redirect_stdout
        from unittest.mock import patch

        from torfast.cli import main as cli_main

        with tempfile.TemporaryDirectory() as tmp:
            services = Path(tmp) / "services"
            with patch(
                "torfast.app_bundle.SERVICES_DIR",
                services,
            ):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    exit_code = cli_main(
                        [
                            "install-app",
                            "--json",
                            "--dest",
                            tmp,
                            "--no-icon",
                            "--no-branded-browser",
                        ]
                    )
        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["app_path"].endswith("Torfast.app"))


if __name__ == "__main__":
    unittest.main()
