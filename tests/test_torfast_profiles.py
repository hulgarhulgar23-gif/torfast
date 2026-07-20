import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from torfast import profiles
from torfast.fast_runtime import (
    AUTO_STATE_ROOT,
    DEFAULT_STATE_ROOT,
    build_launcher_args,
    parse_runtime_action_args,
)
from torfast.profiles import (
    PROFILES,
    ProfileError,
    active_profile_name,
    apply_profile_to_args,
    describe_profiles,
    read_saved_profile_name,
    save_profile,
)

MANAGED_ROOT = str(DEFAULT_STATE_ROOT)


def clean_env() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "TORFAST_PROFILE",
            "TORFAST_DISABLE_RUNTIME_HELPER",
            "TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART",
        }
    }


def runtime_args(command: str, **overrides) -> SimpleNamespace:
    values = {
        "state_root": MANAGED_ROOT if command not in {"launch", "plan"} else AUTO_STATE_ROOT,
        "no_dir_cache_seed": False,
        "no_browser_startup_seed": True,
        "profile": None,
    }
    values.update(overrides)
    return SimpleNamespace(command=command, **values)


def apply(args: SimpleNamespace, config_path: Path | None = None):
    return apply_profile_to_args(
        args,
        managed_state_root=MANAGED_ROOT,
        auto_state_root=AUTO_STATE_ROOT,
        fresh_state_root=lambda command: Path(f"/tmp/fresh-{command}"),
        config_path=config_path,
    )


class ProfileSelectionTests(unittest.TestCase):
    def test_default_is_balanced(self) -> None:
        with patch.dict(os.environ, clean_env(), clear=True):
            with tempfile.TemporaryDirectory() as tmp:
                missing = Path(tmp) / "missing.json"
                self.assertEqual(active_profile_name(config_path=missing), "balanced")

    def test_explicit_beats_env_and_saved(self) -> None:
        with patch.dict(os.environ, {"TORFAST_PROFILE": "turbo"}):
            self.assertEqual(active_profile_name("paranoid"), "paranoid")

    def test_env_beats_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "profile.json"
            save_profile("paranoid", config)
            with patch.dict(os.environ, {"TORFAST_PROFILE": "turbo"}):
                self.assertEqual(active_profile_name(config_path=config), "turbo")

    def test_save_and_read_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "profile.json"
            report = save_profile("turbo", config)
            self.assertTrue(report["ok"])
            self.assertEqual(read_saved_profile_name(config), "turbo")
            payload = json.loads(config.read_text())
            self.assertEqual(payload["profile"], "turbo")

    def test_unknown_profile_rejected(self) -> None:
        with self.assertRaises(ProfileError):
            active_profile_name("ludicrous")
        with self.assertRaises(ProfileError):
            save_profile("ludicrous", Path("/tmp/unused.json"))

    def test_corrupt_config_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "profile.json"
            config.write_text("not json")
            self.assertIsNone(read_saved_profile_name(config))

    def test_describe_lists_all_profiles_with_active_flag(self) -> None:
        with patch.dict(os.environ, {"TORFAST_PROFILE": "turbo"}):
            report = describe_profiles()
        self.assertTrue(report["ok"])
        self.assertEqual(report["active"], "turbo")
        names = [entry["name"] for entry in report["profiles"]]
        self.assertEqual(names, ["turbo", "balanced", "paranoid"])
        active_flags = {
            entry["name"]: entry["active"] for entry in report["profiles"]
        }
        self.assertTrue(active_flags["turbo"])
        self.assertFalse(active_flags["balanced"])


class ApplyProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_balanced_open_keeps_current_behavior(self) -> None:
        args = runtime_args("open", profile="balanced")
        profile = apply(args)
        self.assertEqual(profile.name, "balanced")
        self.assertEqual(args.state_root, MANAGED_ROOT)
        self.assertFalse(args.no_dir_cache_seed)
        self.assertTrue(args.managed_reuse_on_open)
        self.assertFalse(args.keep_tor_warm_after_launch)
        self.assertNotIn("TORFAST_DISABLE_RUNTIME_HELPER", os.environ)

    def test_paranoid_open_is_cold_one_shot(self) -> None:
        args = runtime_args("open", profile="paranoid")
        apply(args)
        self.assertEqual(args.state_root, "/tmp/fresh-open")
        self.assertTrue(args.no_dir_cache_seed)
        self.assertTrue(args.no_browser_startup_seed)
        self.assertFalse(args.managed_reuse_on_open)
        self.assertEqual(os.environ.get("TORFAST_DISABLE_RUNTIME_HELPER"), "1")

    def test_paranoid_respects_explicit_state_root(self) -> None:
        args = runtime_args("open", profile="paranoid", state_root="/tmp/pinned")
        apply(args)
        self.assertEqual(args.state_root, "/tmp/pinned")

    def test_paranoid_warm_is_rejected(self) -> None:
        args = runtime_args("warm", profile="paranoid")
        with self.assertRaises(ProfileError):
            apply(args)

    def test_turbo_launch_moves_to_managed_root_and_stays_warm(self) -> None:
        args = runtime_args("launch", profile="turbo")
        apply(args)
        self.assertEqual(args.state_root, MANAGED_ROOT)
        self.assertTrue(args.keep_tor_warm_after_launch)
        self.assertEqual(
            os.environ.get("TORFAST_ENABLE_WARM_RUNTIME_HELPER_PRESTART"), "1"
        )

    def test_turbo_launch_respects_explicit_state_root(self) -> None:
        args = runtime_args("launch", profile="turbo", state_root="/tmp/pinned")
        apply(args)
        self.assertEqual(args.state_root, "/tmp/pinned")

    def test_every_profile_keeps_quality_untouchable_fields(self) -> None:
        # Profiles must never reach for anonymity-relevant knobs: no
        # profile may define gate, circuit, or fingerprint overrides.
        for profile in PROFILES.values():
            field_names = set(vars(profile))
            self.assertFalse(
                field_names
                & {"browser_launch_gate", "conflux_client_ux", "hops", "stock_ui"},
                f"profile {profile.name} must not carry quality overrides",
            )


class FastPathProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_parse_accepts_profile_and_stock_ui(self) -> None:
        args = parse_runtime_action_args(
            ["open", "--profile", "paranoid", "--stock-ui"]
        )
        self.assertIsNotNone(args)
        assert args is not None
        self.assertEqual(args.profile, "paranoid")
        self.assertTrue(args.stock_ui)

    def test_parse_rejects_unknown_profile(self) -> None:
        self.assertIsNone(parse_runtime_action_args(["open", "--profile", "nope"]))

    def test_paranoid_launcher_args_drop_managed_reuse(self) -> None:
        args = parse_runtime_action_args(["open", "--profile", "paranoid"])
        assert args is not None
        apply(args)
        with patch(
            "torfast.fast_runtime.discover_browser_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ), patch(
            "torfast.fast_runtime.discover_tor_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ):
            launcher_args = build_launcher_args(args)
        self.assertNotIn("--leave-tor-running", launcher_args)
        self.assertNotIn("--reuse-tor-if-running", launcher_args)
        self.assertIn("--no-dir-cache-seed", launcher_args)
        self.assertIn("--profile-label", launcher_args)
        self.assertIn("paranoid", launcher_args)

    def test_turbo_launch_launcher_args_keep_tor_warm(self) -> None:
        args = parse_runtime_action_args(["launch", "--profile", "turbo"])
        assert args is not None
        apply(args)
        with patch(
            "torfast.fast_runtime.discover_browser_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ), patch(
            "torfast.fast_runtime.discover_tor_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ):
            launcher_args = build_launcher_args(args)
        self.assertIn("--leave-tor-running", launcher_args)
        self.assertIn("--reuse-tor-if-running", launcher_args)

    def test_stock_ui_is_forwarded(self) -> None:
        args = parse_runtime_action_args(["open", "--stock-ui"])
        assert args is not None
        apply(args)
        with patch(
            "torfast.fast_runtime.discover_browser_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ), patch(
            "torfast.fast_runtime.discover_tor_bin",
            return_value={"found": True, "path": "/bin/echo"},
        ):
            launcher_args = build_launcher_args(args)
        self.assertIn("--stock-ui", launcher_args)


class ProfileCliTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch.dict(os.environ, clean_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_profile_command_lists_profiles_as_json(self) -> None:
        from torfast.cli import main as cli_main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "profile.json"
            with patch.object(profiles, "PROFILE_CONFIG_PATH", config):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    exit_code = cli_main(["profile", "--json"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["active"], "balanced")
        self.assertEqual(len(payload["profiles"]), 3)

    def test_profile_command_sets_profile(self) -> None:
        from torfast.cli import main as cli_main
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "profile.json"
            with patch.object(profiles, "PROFILE_CONFIG_PATH", config):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    exit_code = cli_main(["profile", "turbo", "--json"])
                self.assertEqual(exit_code, 0)
                payload = json.loads(buffer.getvalue())
                self.assertEqual(payload["profile"], "turbo")
                self.assertEqual(read_saved_profile_name(config), "turbo")


if __name__ == "__main__":
    unittest.main()
