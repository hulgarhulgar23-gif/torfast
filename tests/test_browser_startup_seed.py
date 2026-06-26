import json
import tempfile
import unittest
from pathlib import Path


from torfast.browser_startup_seed import (
    STARTUP_CACHE_RELATIVE_PATH,
    apply_seed_to_profile,
    describe_seed,
    update_seed_from_profile,
)


DEFAULT_ADDON_ID = "{73a6fe31-595d-460b-a920-fcc0f8843232}"


def write_extensions_json(
    profile_dir: Path,
    *,
    distribution_ids: list[str],
    other_app_profile_ids: list[str] | None = None,
) -> None:
    addons = []
    for addon_id in distribution_ids:
        addons.append(
            {
                "id": addon_id,
                "location": "app-profile",
                "installTelemetryInfo": {"source": "distribution"},
            }
        )
    for addon_id in other_app_profile_ids or []:
        addons.append(
            {
                "id": addon_id,
                "location": "app-profile",
                "installTelemetryInfo": {"source": "sideload"},
            }
        )
    addons.append({"id": "default-theme@mozilla.org", "location": "app-builtin"})
    (profile_dir / "extensions.json").write_text(
        json.dumps({"addons": addons}, indent=2, sort_keys=True) + "\n"
    )


class BrowserStartupSeedTests(unittest.TestCase):
    def test_update_and_apply_seed_only_copies_startup_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            (source_profile / "cookies.sqlite").write_bytes(b"do not seed")

            seed_root = root / "browser-startup-seed"
            updated = update_seed_from_profile(source_profile, seed_root)

            self.assertTrue(updated["ok"])
            self.assertTrue(updated["updated"])
            self.assertEqual(
                updated["distribution_app_profile_extension_ids"],
                [DEFAULT_ADDON_ID],
            )
            described = describe_seed(seed_root)
            self.assertEqual(
                described["files"],
                [
                    f"extensions/{DEFAULT_ADDON_ID}.xpi",
                    STARTUP_CACHE_RELATIVE_PATH.as_posix(),
                ],
            )

            dest_profile = root / "dest-profile"
            applied = apply_seed_to_profile(dest_profile, seed_root)

            self.assertTrue(applied["ok"])
            self.assertTrue(applied["applied"])
            self.assertEqual(
                (dest_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi").read_bytes(),
                b"xpi payload",
            )
            self.assertEqual(
                (dest_profile / STARTUP_CACHE_RELATIVE_PATH).read_bytes(),
                b"compiled extension cache",
            )
            self.assertFalse((dest_profile / "cookies.sqlite").exists())

    def test_update_seed_skips_non_distribution_app_profile_addons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile"
            profile.mkdir()
            write_extensions_json(
                profile,
                distribution_ids=[DEFAULT_ADDON_ID],
                other_app_profile_ids=["user-addon@example"],
            )
            addon = profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")

            updated = update_seed_from_profile(profile, root / "seed")

            self.assertTrue(updated["ok"])
            self.assertFalse(updated["updated"])
            self.assertIn("non-whitelisted app-profile addons present", updated["reason"])

    def test_update_seed_allows_existing_whitelisted_app_profile_addon_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            seed_root = root / "seed"
            initial = update_seed_from_profile(source_profile, seed_root)
            self.assertTrue(initial["updated"])

            seeded_profile = root / "seeded-profile"
            seeded_profile.mkdir()
            write_extensions_json(
                seeded_profile,
                distribution_ids=[],
                other_app_profile_ids=[DEFAULT_ADDON_ID],
            )
            seeded_addon = seeded_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            seeded_addon.parent.mkdir(parents=True)
            seeded_addon.write_bytes(b"xpi payload v2")
            seeded_startup_cache = seeded_profile / STARTUP_CACHE_RELATIVE_PATH
            seeded_startup_cache.parent.mkdir(parents=True)
            seeded_startup_cache.write_bytes(b"compiled extension cache v2")

            updated = update_seed_from_profile(seeded_profile, seed_root)

            self.assertTrue(updated["ok"])
            self.assertTrue(updated["updated"])
            self.assertEqual(
                (seed_root / "files" / "extensions" / f"{DEFAULT_ADDON_ID}.xpi").read_bytes(),
                b"xpi payload v2",
            )

    def test_update_seed_preserves_existing_startup_cache_when_profile_lacks_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            seed_root = root / "seed"
            initial = update_seed_from_profile(source_profile, seed_root)
            self.assertTrue(initial["updated"])

            later_profile = root / "later-profile"
            later_profile.mkdir()
            write_extensions_json(later_profile, distribution_ids=[DEFAULT_ADDON_ID])
            later_addon = later_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            later_addon.parent.mkdir(parents=True)
            later_addon.write_bytes(b"xpi payload")
            later_addon.touch()
            addon_stat = addon.stat()
            later_addon.touch()
            import os
            os.utime(later_addon, ns=(addon_stat.st_atime_ns, addon_stat.st_mtime_ns))

            updated = update_seed_from_profile(later_profile, seed_root)

            self.assertTrue(updated["ok"])
            self.assertFalse(updated["updated"])
            self.assertEqual(updated["reason"], "seed already current")
            described = describe_seed(seed_root)
            self.assertEqual(
                described["files"],
                [
                    f"extensions/{DEFAULT_ADDON_ID}.xpi",
                    STARTUP_CACHE_RELATIVE_PATH.as_posix(),
                ],
            )

    def test_update_seed_drops_startup_cache_when_addon_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload v1")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            seed_root = root / "seed"
            self.assertTrue(update_seed_from_profile(source_profile, seed_root)["updated"])

            changed_profile = root / "changed-profile"
            changed_profile.mkdir()
            write_extensions_json(changed_profile, distribution_ids=[DEFAULT_ADDON_ID])
            changed_addon = changed_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            changed_addon.parent.mkdir(parents=True)
            changed_addon.write_bytes(b"xpi payload v2")

            updated = update_seed_from_profile(changed_profile, seed_root)

            self.assertTrue(updated["ok"])
            self.assertTrue(updated["updated"])
            self.assertEqual(
                updated["files"],
                [f"extensions/{DEFAULT_ADDON_ID}.xpi"],
            )
            described = describe_seed(seed_root)
            self.assertEqual(
                described["files"],
                [f"extensions/{DEFAULT_ADDON_ID}.xpi"],
            )

    def test_apply_seed_skips_non_empty_profile_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            seed_root = root / "seed"
            self.assertTrue(update_seed_from_profile(source_profile, seed_root)["updated"])

            dest_profile = root / "dest-profile"
            dest_profile.mkdir()
            (dest_profile / "prefs.js").write_text("")
            applied = apply_seed_to_profile(dest_profile, seed_root)

            self.assertTrue(applied["ok"])
            self.assertFalse(applied["applied"])
            self.assertEqual(applied["reason"], "profile dir not empty")

    def test_update_seed_skips_rewrite_when_manifest_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_profile = root / "source-profile"
            source_profile.mkdir()
            write_extensions_json(source_profile, distribution_ids=[DEFAULT_ADDON_ID])
            addon = source_profile / "extensions" / f"{DEFAULT_ADDON_ID}.xpi"
            addon.parent.mkdir(parents=True)
            addon.write_bytes(b"xpi payload")
            startup_cache = source_profile / STARTUP_CACHE_RELATIVE_PATH
            startup_cache.parent.mkdir(parents=True)
            startup_cache.write_bytes(b"compiled extension cache")
            seed_root = root / "seed"

            initial = update_seed_from_profile(source_profile, seed_root)
            repeated = update_seed_from_profile(source_profile, seed_root)

            self.assertTrue(initial["updated"])
            self.assertFalse(repeated["updated"])
            self.assertEqual(repeated["reason"], "seed already current")


if __name__ == "__main__":
    unittest.main()
