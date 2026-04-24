from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pygame

from constants import ACCENT_GOLD, TABLE_BACKGROUND, TABLE_FELT, TEXT_MUTED, TEXT_PRIMARY


@dataclass(frozen=True, slots=True)
class GameTheme:
    colors: dict[str, tuple[int, int, int]]
    fonts: dict[str, pygame.font.Font]
    profile_colors: dict[str, tuple[int, int, int]]


def build_theme(asset_dir: Path) -> GameTheme:
    del asset_dir
    return GameTheme(
        colors={
            "bg": TABLE_BACKGROUND,
            "panel": (31, 38, 44),
            "panel_soft": (25, 33, 39),
            "border": (83, 93, 93),
            "text": TEXT_PRIMARY,
            "muted": TEXT_MUTED,
            "gold": ACCENT_GOLD,
            "cream": (239, 226, 196),
            "felt": TABLE_FELT,
        },
        fonts={
            "title": pygame.font.Font(None, 76),
            "subtitle": pygame.font.Font(None, 34),
            "dealer": pygame.font.Font(None, 30),
            "body": pygame.font.Font(None, 28),
            "body_bold": pygame.font.Font(None, 30),
            "small": pygame.font.Font(None, 22),
            "tiny": pygame.font.Font(None, 18),
            "hud_title": pygame.font.Font(None, 34),
            "hud_body": pygame.font.Font(None, 26),
            "hud_small": pygame.font.Font(None, 20),
            "card": pygame.font.Font(None, 30),
        },
        profile_colors={
            "dante": (172, 67, 58),
            "ash": (120, 137, 150),
            "mr_fold": (91, 136, 109),
            "vesper": (112, 96, 148),
            "fox": (190, 122, 63),
            "dealer": ACCENT_GOLD,
        },
    )
