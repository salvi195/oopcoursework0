from __future__ import annotations

from dataclasses import dataclass

from constants import ACCENT_GOLD, TABLE_BACKGROUND, TABLE_FELT, TEXT_MUTED, TEXT_PRIMARY


@dataclass(frozen=True, slots=True)
class ThemePalette:
    background: tuple[int, int, int] = TABLE_BACKGROUND
    felt: tuple[int, int, int] = TABLE_FELT
    accent: tuple[int, int, int] = ACCENT_GOLD
    text_primary: tuple[int, int, int] = TEXT_PRIMARY
    text_muted: tuple[int, int, int] = TEXT_MUTED


DEFAULT_THEME = ThemePalette()
