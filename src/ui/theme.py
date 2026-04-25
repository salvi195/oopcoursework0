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
    title_font = pygame.font.SysFont("georgia", 82, bold=True)
    neon_font = pygame.font.SysFont("agency fb", 104, bold=True)
    menu_font = pygame.font.SysFont("agency fb", 42, bold=True)
    menu_small_font = pygame.font.SysFont("agency fb", 26, bold=True)
    display_font = pygame.font.SysFont("palatino linotype", 34, italic=True)
    body_font = pygame.font.SysFont("segoe ui", 26)
    body_bold_font = pygame.font.SysFont("segoe ui", 28, bold=True)
    small_font = pygame.font.SysFont("segoe ui", 20)
    tiny_font = pygame.font.SysFont("segoe ui", 16)
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
            "title": title_font,
            "neon": neon_font,
            "menu": menu_font,
            "menu_small": menu_small_font,
            "subtitle": display_font,
            "dealer": display_font,
            "body": body_font,
            "body_bold": body_bold_font,
            "small": small_font,
            "tiny": tiny_font,
            "hud_title": pygame.font.SysFont("agency fb", 38, bold=True),
            "hud_body": pygame.font.SysFont("agency fb", 27, bold=True),
            "hud_small": pygame.font.SysFont("agency fb", 20, bold=True),
            "card": pygame.font.SysFont("georgia", 28, bold=True),
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
