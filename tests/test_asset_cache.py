from __future__ import annotations

import os
from pathlib import Path
import shutil
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.ui.assets import FRINGE_CACHE_VERSION, AssetLibrary


class AssetCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        self.asset_dir = Path("tests/.asset_cache_test")
        shutil.rmtree(self.asset_dir, ignore_errors=True)
        self.asset_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        pygame.quit()
        shutil.rmtree(self.asset_dir, ignore_errors=True)

    def test_corrupt_clean_cache_is_regenerated(self) -> None:
        source_path = self.asset_dir / "character_wolf.png"
        source = pygame.Surface((8, 8), pygame.SRCALPHA)
        source.fill((24, 38, 52, 255))
        pygame.image.save(source, source_path)

        cache_path = (
            self.asset_dir
            / ".cleaned"
            / f"character_wolf_{FRINGE_CACHE_VERSION}.png"
        )
        cache_path.parent.mkdir()
        cache_path.write_bytes(b"not a png")
        cache_time = source_path.stat().st_mtime + 10
        os.utime(cache_path, (cache_time, cache_time))

        assets = AssetLibrary(self.asset_dir, {"bg": (0, 0, 0)}, {}, {})
        image = assets._load_clean_source(
            source_path,
            remove_checkerboard=True,
            remove_white_fringe=False,
        )

        self.assertIsNotNone(image)
        self.assertEqual(image.get_size(), (8, 8))
        self.assertEqual(pygame.image.load(cache_path).get_size(), (8, 8))


if __name__ == "__main__":
    unittest.main()
