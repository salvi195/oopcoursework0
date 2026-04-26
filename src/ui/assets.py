from __future__ import annotations

import math
from pathlib import Path

import pygame

FRINGE_CACHE_VERSION = "fringe_v8"


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
        self.cleaned_asset_dir = self.asset_dir / ".cleaned"
        self._cache: dict[tuple[str, tuple[int, int], bool, bool], pygame.Surface | None] = {}

    def image(
        self,
        name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        return self._load_image(name, size)

    def cover_image(
        self,
        name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        cache_key = (f"cover:{name}", size, False, False)
        if cache_key in self._cache:
            return self._cache[cache_key]

        for suffix in (".png", ".jpg", ".jpeg"):
            path = self.asset_dir / f"{name}{suffix}"
            if not path.exists():
                continue
            source = self._load_surface(path)
            if source is None:
                continue
            source_width, source_height = source.get_size()
            target_width, target_height = size
            scale = max(target_width / source_width, target_height / source_height)
            scaled_size = (
                max(1, int(source_width * scale)),
                max(1, int(source_height * scale)),
            )
            scaled = pygame.transform.smoothscale(source, scaled_size)
            crop = pygame.Rect(
                (scaled_size[0] - target_width) // 2,
                (scaled_size[1] - target_height) // 2,
                target_width,
                target_height,
            )
            result = scaled.subsurface(crop).copy()
            self._cache[cache_key] = result
            return result

        self._cache[cache_key] = None
        return None

    def transparent_image(
        self,
        name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        return self._load_image(name, size, remove_checkerboard=True, remove_white_fringe=True)

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
        for name in (f"portrait_{key}", f"character_{key}", key):
            image = self._load_image(
                name,
                size,
                remove_checkerboard=True,
                remove_white_fringe=key != "fox",
            )
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
        fill = (58, 7, 24) if not highlighted else (82, 17, 28)
        border = self.colors.get("gold", (207, 175, 102))
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, border, rect, 2, border_radius=8)
        pygame.draw.rect(surface, (132, 85, 45), rect.inflate(-12, -12), 1, 6)
        center = rect.center
        radius = max(10, min(rect.width, rect.height) // 5)
        pygame.draw.circle(surface, (222, 164, 67), center, radius, 4)
        for index in range(6):
            theta = -3.14159 / 2 + 6.28318 * index / 6
            hole = (
                int(center[0] + math.cos(theta) * radius * 0.58),
                int(center[1] + math.sin(theta) * radius * 0.58),
            )
            pygame.draw.circle(surface, (47, 7, 18), hole, max(3, radius // 5))
            pygame.draw.circle(surface, (244, 198, 105), hole, max(3, radius // 5), 1)
        return surface

    def card_face(
        self,
        rank_label: str,
        suit_name: str,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        asset_name = f"{rank_label.lower()}_{suit_name.lower()}"
        cache_key = (f"card_face:{asset_name}", size, False, False)
        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self.asset_dir / "cards" / f"{asset_name}.png"
        if not path.exists():
            self._cache[cache_key] = None
            return None

        source = pygame.image.load(path).convert_alpha()
        source = self._crop_card_source(source)
        scaled = pygame.transform.smoothscale(source, size)
        self._mask_card_corners(scaled)
        self._cache[cache_key] = scaled
        return scaled

    def character(
        self,
        profile_key: str | None,
        size: tuple[int, int],
    ) -> pygame.Surface | None:
        if profile_key is None:
            return None
        for name in (
            f"character_{profile_key}",
            f"{profile_key}_table",
            profile_key,
        ):
            image = self._load_image(
                name,
                size,
                remove_checkerboard=True,
                remove_white_fringe=profile_key != "fox",
            )
            if image is not None:
                return image
        return None

    def _load_image(
        self,
        name: str,
        size: tuple[int, int],
        *,
        remove_checkerboard: bool = False,
        remove_white_fringe: bool = False,
    ) -> pygame.Surface | None:
        cache_key = (name, size, remove_checkerboard, remove_white_fringe)
        if cache_key in self._cache:
            return self._cache[cache_key]

        for suffix in (".png", ".jpg", ".jpeg"):
            path = self.asset_dir / f"{name}{suffix}"
            if path.exists():
                image = self._load_clean_source(
                    path,
                    remove_checkerboard=remove_checkerboard,
                    remove_white_fringe=remove_white_fringe,
                )
                if image is None:
                    continue

                scaled = pygame.transform.smoothscale(image, size)
                if remove_checkerboard:
                    self._remove_edge_checkerboard(scaled)
                if remove_white_fringe:
                    scaled = self.remove_fringe(scaled)
                self._remove_asset_white_spots(scaled, path.stem)
                self._clear_transparent_pixels(scaled)
                self._cache[cache_key] = scaled
                return scaled
        self._cache[cache_key] = None
        return None

    def _load_clean_source(
        self,
        path: Path,
        *,
        remove_checkerboard: bool,
        remove_white_fringe: bool,
    ) -> pygame.Surface | None:
        if not remove_checkerboard and not remove_white_fringe:
            return self._load_surface(path)

        cache_path = self._clean_cache_path(path)
        if self._clean_cache_is_current(path, cache_path):
            cached = self._load_surface(cache_path)
            if cached is not None:
                return cached
            self._discard_clean_cache(cache_path)

        image = self._load_surface(path)
        if image is None:
            return None
        if remove_checkerboard:
            self._remove_edge_checkerboard(image)
        if remove_white_fringe:
            image = self.remove_fringe(image)
        self._remove_asset_white_spots(image, path.stem)
        self._clear_transparent_pixels(image)
        self.cleaned_asset_dir.mkdir(parents=True, exist_ok=True)
        try:
            pygame.image.save(image, cache_path)
        except (OSError, pygame.error):
            pass
        return image

    def _load_surface(self, path: Path) -> pygame.Surface | None:
        try:
            return pygame.image.load(path).convert_alpha()
        except (OSError, pygame.error, ValueError):
            return None

    def _discard_clean_cache(self, cache_path: Path) -> None:
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _clean_cache_path(self, path: Path) -> Path:
        return self.cleaned_asset_dir / f"{path.stem}_{FRINGE_CACHE_VERSION}.png"

    def _clean_cache_is_current(self, source_path: Path, cache_path: Path) -> bool:
        if not cache_path.exists():
            return False
        return cache_path.stat().st_mtime >= source_path.stat().st_mtime

    def _crop_card_source(self, surface: pygame.Surface) -> pygame.Surface:
        width, height = surface.get_size()
        xs: list[int] = []
        ys: list[int] = []
        for x in range(width):
            for y in range(height):
                color = surface.get_at((x, y))
                if self._is_card_source_pixel(color):
                    xs.append(x)
                    ys.append(y)

        if not xs or not ys:
            return surface

        pad = 6
        left = max(0, min(xs) - pad)
        top = max(0, min(ys) - pad)
        right = min(width, max(xs) + pad + 1)
        bottom = min(height, max(ys) + pad + 1)
        if right - left < width * 0.45 or bottom - top < height * 0.45:
            return surface
        return surface.subsurface(pygame.Rect(left, top, right - left, bottom - top)).copy()

    def _is_card_source_pixel(self, color: pygame.Color) -> bool:
        if color.a < 20:
            return False
        channels = (color.r, color.g, color.b)
        if min(channels) < 215:
            return True
        if color.r > 120 and color.g < 150 and color.b < 150:
            return True
        return False

    def _mask_card_corners(self, surface: pygame.Surface) -> None:
        rect = surface.get_rect()
        radius = max(6, int(min(rect.size) * 0.09))
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), rect, border_radius=radius)
        surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    def remove_fringe(self, surface: pygame.Surface) -> pygame.Surface:
        """
        Removes white/light fringe pixels left after background removal.
        Targets semi-transparent edge pixels that are too bright.
        """
        surface = surface.convert_alpha()
        width, height = surface.get_size()
        if width == 0 or height == 0:
            return surface

        self._remove_near_transparent_light_pixels(surface, radius=7, alpha_cutoff=245)
        self._peel_light_edge(surface, passes=3)
        return surface

    def _remove_near_transparent_light_pixels(
        self,
        surface: pygame.Surface,
        *,
        radius: int,
        alpha_cutoff: int,
    ) -> None:
        width, height = surface.get_size()
        fringe_pixels: list[tuple[int, int]] = []
        for x in range(width):
            for y in range(height):
                r, g, b, a = surface.get_at((x, y))
                if a == 0:
                    continue
                if not self._is_light_fringe_pixel(r, g, b):
                    continue
                if a < alpha_cutoff or self._has_nearby_transparency(surface, x, y, radius=radius):
                    fringe_pixels.append((x, y))

        for x, y in fringe_pixels:
            surface.set_at((x, y), (0, 0, 0, 0))

    def _peel_light_edge(self, surface: pygame.Surface, *, passes: int = 2) -> None:
        for _ in range(passes):
            edge_pixels: list[tuple[int, int]] = []
            width, height = surface.get_size()
            for x in range(width):
                for y in range(height):
                    r, g, b, a = surface.get_at((x, y))
                    if a == 0:
                        continue
                    if not self._is_bright_edge_cast(r, g, b):
                        continue
                    if self._touches_clear_alpha(surface, x, y):
                        edge_pixels.append((x, y))

            if not edge_pixels:
                return
            for x, y in edge_pixels:
                surface.set_at((x, y), (0, 0, 0, 0))

    def _is_bright_edge_cast(self, r: int, g: int, b: int) -> bool:
        luminance = int(r * 0.299 + g * 0.587 + b * 0.114)
        spread = max(r, g, b) - min(r, g, b)
        if min(r, g, b) >= 225:
            return True
        if min(r, g, b) >= 185 and spread <= 28:
            return True
        return luminance >= 210 and spread <= 58

    def _clear_transparent_pixels(self, surface: pygame.Surface) -> None:
        width, height = surface.get_size()
        for x in range(width):
            for y in range(height):
                if surface.get_at((x, y))[3] == 0:
                    surface.set_at((x, y), (0, 0, 0, 0))

    def _remove_asset_white_spots(self, surface: pygame.Surface, asset_name: str) -> None:
        if asset_name == "revolver":
            self._remove_near_white_pixels(surface)
        elif asset_name == "table":
            self._remove_near_white_pixels(surface)
        elif asset_name == "character_ash":
            self._remove_near_transparent_light_pixels(surface, radius=9, alpha_cutoff=250)
            self._peel_light_edge(surface, passes=2)
        elif asset_name == "character_mr_fold":
            self._remove_near_white_pixels(surface, min_y_ratio=0.45)

    def _remove_near_white_pixels(
        self,
        surface: pygame.Surface,
        *,
        min_y_ratio: float = 0.0,
    ) -> None:
        width, height = surface.get_size()
        min_y = int(height * min_y_ratio)
        for x in range(width):
            for y in range(min_y, height):
                r, g, b, a = surface.get_at((x, y))
                if a == 0:
                    continue
                if min(r, g, b) >= 228 and max(r, g, b) - min(r, g, b) <= 48:
                    surface.set_at((x, y), (0, 0, 0, 0))

    def _is_light_fringe_pixel(self, r: int, g: int, b: int) -> bool:
        lowest = min(r, g, b)
        spread = max(r, g, b) - lowest
        if lowest >= 215:
            return True
        return lowest >= 170 and spread <= 80

    def _touches_clear_alpha(self, surface: pygame.Surface, x: int, y: int) -> bool:
        width, height = surface.get_size()
        for nx in range(max(0, x - 1), min(width, x + 2)):
            for ny in range(max(0, y - 1), min(height, y + 2)):
                if nx == x and ny == y:
                    continue
                if surface.get_at((nx, ny))[3] == 0:
                    return True
        return False

    def _has_nearby_transparency(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        *,
        radius: int,
    ) -> bool:
        width, height = surface.get_size()
        for nx in range(max(0, x - radius), min(width, x + radius + 1)):
            for ny in range(max(0, y - radius), min(height, y + radius + 1)):
                if nx == x and ny == y:
                    continue
                if surface.get_at((nx, ny))[3] < 180:
                    return True
        return False

    def _remove_edge_checkerboard(self, surface: pygame.Surface) -> None:
        width, height = surface.get_size()
        if width == 0 or height == 0:
            return

        visited = bytearray(width * height)
        queue: list[tuple[int, int]] = []

        def add(x: int, y: int) -> None:
            if 0 <= x < width and 0 <= y < height:
                index = y * width + x
                if not visited[index]:
                    queue.append((x, y))

        for x in range(width):
            add(x, 0)
            add(x, height - 1)
        for y in range(height):
            add(0, y)
            add(width - 1, y)

        head = 0
        while head < len(queue):
            x, y = queue[head]
            head += 1
            index = y * width + x
            if visited[index]:
                continue
            visited[index] = 1
            color = surface.get_at((x, y))
            if not self._is_checkerboard_pixel(color):
                continue
            surface.set_at((x, y), (0, 0, 0, 0))
            add(x + 1, y)
            add(x - 1, y)
            add(x, y + 1)
            add(x, y - 1)

    def _is_checkerboard_pixel(self, color: pygame.Color) -> bool:
        if color.a < 20:
            return True
        channels = (color.r, color.g, color.b)
        return min(channels) >= 218 and max(channels) - min(channels) <= 28
