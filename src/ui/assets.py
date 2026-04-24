from __future__ import annotations

from pathlib import Path

import pygame


def build_label(text: str, fallback: str = "Unknown") -> str:
    cleaned = text.strip()
    return cleaned or fallback


class AssetLibrary:
    def __init__(
        self,
        asset_dir: Path,
        colors: dict[str, tuple[int, int, int]],
        profile_colors: dict[str, tuple[int, int, int]],
        profile_lookup: dict[str, object],
    ) -> None:
        self.asset_dir = asset_dir
        self.colors = colors
        self.profile_colors = profile_colors
        self.profile_lookup = profile_lookup

    def background(
        self,
        name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        image = self._load_image(name, size)
        if image is not None:
            return image

        surface = pygame.Surface(size)
        top = self.colors.get("bg", (18, 24, 31))
        bottom = (33, 47, 50)
        for y in range(size[1]):
            amount = y / max(1, size[1] - 1)
            color = tuple(
                int(top[index] * (1 - amount) + bottom[index] * amount)
                for index in range(3)
            )
            pygame.draw.line(surface, color, (0, y), (size[0], y))
        return surface

    def portrait(self, profile_key: str | None, size: tuple[int, int]) -> pygame.Surface:
        key = profile_key or "dealer"
        image = self._load_image(key, size)
        if image is not None:
            return image

        color = self.profile_colors.get(key, self.colors.get("gold", (207, 175, 102)))
        surface = pygame.Surface(size, pygame.SRCALPHA)
        rect = surface.get_rect()
        pygame.draw.ellipse(surface, (*color, 255), rect.inflate(-8, -8))
        pygame.draw.ellipse(surface, (20, 24, 28), rect.inflate(-8, -8), 3)
        return surface

    def card_back(
        self,
        size: tuple[int, int],
        highlighted: bool = False,
    ) -> pygame.Surface:
        surface = pygame.Surface(size, pygame.SRCALPHA)
        rect = surface.get_rect()
        fill = (53, 39, 42) if not highlighted else (76, 53, 48)
        border = self.colors.get("gold", (207, 175, 102))
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, border, rect, 3, border_radius=8)
        pygame.draw.rect(surface, (19, 23, 28), rect.inflate(-20, -20), 2, 6)
        return surface

    def _load_image(
        self,
        name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        for suffix in (".png", ".jpg", ".jpeg"):
            path = self.asset_dir / f"{name}{suffix}"
            if path.exists():
                image = pygame.image.load(path).convert_alpha()
                return pygame.transform.smoothscale(image, size)
        return None
