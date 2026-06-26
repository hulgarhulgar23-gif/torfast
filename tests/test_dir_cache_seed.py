import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from torfast import dir_cache_seed as dir_cache_seed_module
from torfast.dir_cache_seed import (
    apply_seed_to_data_dir,
    copy_file_clone_or_copy2,
    describe_seed,
    seedable_cache_paths,
    update_seed_from_data_dir,
)


class DirCacheSeedTests(unittest.TestCase):
    def test_seedable_cache_paths_excludes_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "cached-certs").write_text("certs")
            (data_dir / "cached-microdesc-consensus").write_text("consensus")
            (data_dir / "cached-microdescs").write_text("microdescs")
            (data_dir / "state").write_text("Guard foo")

            paths = seedable_cache_paths(data_dir)

        self.assertEqual(
            [path.name for path in paths],
            ["cached-certs", "cached-microdesc-consensus", "cached-microdescs"],
        )

    def test_update_and_apply_seed_copy_only_cache_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs")
            (source_data_dir / "cached-microdesc-consensus").write_text("consensus")
            (source_data_dir / "cached-microdescs").write_text("microdescs")
            (source_data_dir / "state").write_text("Guard foo")
            seed_root = root / "seed"

            update = update_seed_from_data_dir(source_data_dir, seed_root)
            target_data_dir = root / "target"
            applied = apply_seed_to_data_dir(target_data_dir, seed_root)

            self.assertTrue(update["updated"])
            self.assertTrue(applied["applied"])
            self.assertTrue((target_data_dir / "cached-certs").exists())
            self.assertTrue((target_data_dir / "cached-microdesc-consensus").exists())
            self.assertTrue((target_data_dir / "cached-microdescs").exists())
            self.assertFalse((target_data_dir / "state").exists())

    def test_apply_seed_skips_nonempty_target_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs")
            seed_root = root / "seed"
            update_seed_from_data_dir(source_data_dir, seed_root)

            target_data_dir = root / "target"
            target_data_dir.mkdir()
            (target_data_dir / "state").write_text("existing state")
            applied = apply_seed_to_data_dir(target_data_dir, seed_root)

            self.assertFalse(applied["applied"])
            self.assertEqual(applied["reason"], "data dir already has files")

    def test_apply_seed_uses_manifest_hash_without_rehashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs")
            (source_data_dir / "cached-microdescs").write_text("microdescs")
            seed_root = root / "seed"
            update_seed_from_data_dir(source_data_dir, seed_root)

            target_data_dir = root / "target"
            with patch(
                "torfast.dir_cache_seed.copy_file_with_sha256",
                side_effect=AssertionError("apply should not rehash seed files"),
            ):
                applied = apply_seed_to_data_dir(target_data_dir, seed_root)

            self.assertTrue(applied["applied"])
            self.assertEqual(len(applied["copied_files"]), 2)
            self.assertTrue(
                all(isinstance(entry.get("sha256"), str) for entry in applied["copied_files"])
            )
            self.assertTrue(
                all(entry.get("copy_mode") in {"clone", "copy"} for entry in applied["copied_files"])
            )

    def test_copy_file_clone_or_copy2_prefers_clone_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.write_text("seed-data")

            def fake_clonefile(source_path: bytes, destination_path: bytes, flags: int) -> int:
                self.assertEqual(flags, 0)
                shutil.copy2(
                    Path(os.fsdecode(source_path)),
                    Path(os.fsdecode(destination_path)),
                )
                return 0

            with patch(
                "torfast.dir_cache_seed._clonefile_function",
                return_value=fake_clonefile,
            ):
                mode = copy_file_clone_or_copy2(source, destination)

            self.assertEqual(mode, "clone")
            self.assertEqual(destination.read_text(), "seed-data")

    def test_copy_file_clone_or_copy2_falls_back_to_copy_when_clone_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.write_text("seed-data")

            def fake_clonefile(source_path: bytes, destination_path: bytes, flags: int) -> int:
                Path(os.fsdecode(destination_path)).write_text("partial")
                return -1

            with patch(
                "torfast.dir_cache_seed._clonefile_function",
                return_value=fake_clonefile,
            ):
                mode = copy_file_clone_or_copy2(source, destination)

            self.assertEqual(mode, "copy")
            self.assertEqual(destination.read_text(), "seed-data")

    def test_describe_seed_reports_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs")
            seed_root = root / "seed"
            update_seed_from_data_dir(source_data_dir, seed_root)

            description = describe_seed(seed_root)

            self.assertTrue(description["present"])
            self.assertIn("cached-certs", description["available_files"])
            self.assertIsInstance(description["manifest"], dict)

    def test_update_seed_skips_rewrite_when_manifest_is_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs")
            (source_data_dir / "cached-microdescs").write_text("microdescs")
            seed_root = root / "seed"

            initial = update_seed_from_data_dir(source_data_dir, seed_root)
            repeated = update_seed_from_data_dir(source_data_dir, seed_root)

            self.assertTrue(initial["updated"])
            self.assertFalse(repeated["updated"])
            self.assertEqual(repeated["reason"], "seed already current")
            manifest = json.loads((seed_root / "seed.json").read_text())
            self.assertEqual(len(manifest["files"]), 2)

    def test_update_seed_recopies_only_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data_dir = root / "source"
            source_data_dir.mkdir()
            (source_data_dir / "cached-certs").write_text("certs-v1")
            (source_data_dir / "cached-microdesc-consensus").write_text("consensus-v1")
            (source_data_dir / "cached-microdescs").write_text("microdescs-v1")
            seed_root = root / "seed"

            initial = update_seed_from_data_dir(source_data_dir, seed_root)
            self.assertTrue(initial["updated"])

            (source_data_dir / "cached-certs").write_text("certs-v2-longer")
            copied_sources: list[str] = []
            real_copy = dir_cache_seed_module.copy_file_with_sha256

            def record_copy(source: Path, destination: Path) -> dict[str, object]:
                copied_sources.append(source.name)
                return real_copy(source, destination)

            with patch(
                "torfast.dir_cache_seed.copy_file_with_sha256",
                side_effect=record_copy,
            ):
                updated = update_seed_from_data_dir(source_data_dir, seed_root)

            self.assertTrue(updated["updated"])
            self.assertEqual(copied_sources, ["cached-certs"])
            self.assertEqual(updated["updated_files"], ["cached-certs"])
            self.assertEqual(
                updated["reused_files"],
                ["cached-microdesc-consensus", "cached-microdescs"],
            )


if __name__ == "__main__":
    unittest.main()
