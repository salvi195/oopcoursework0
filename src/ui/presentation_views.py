from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from constants import SCREEN_HEIGHT, SCREEN_WIDTH


@dataclass(slots=True)
class PresentationEvent:
    kind: str
    title: str
    subtitle: str = ""
    detail: str = ""
    actor_name: str | None = None
    target_name: str | None = None
    duration_ms: int = 2600
    allow_input: bool = False
    emphasis: str = "neutral"
    chance_percent: int | None = None
    chamber_index: int | None = None


class PresentationViewsMixin:
    """Drawing for the round/claim/challenge/verdict/bullet/reputation overlays."""

    def _draw_presentation_overlay(self, now: int) -> None:
        event = self.presentation_event
        if event is None:
            return
        remaining_ms = max(0, self.presentation_until - now)
        progress = 1 - remaining_ms / max(1, event.duration_ms)

        if event.kind == "bullet":
            self._draw_revolver_presentation(event, progress)
            return
        if event.kind == "reputation":
            self._draw_reputation_presentation(event, progress)
            return
        self._draw_minimal_presentation(event, progress, remaining_ms)

    def _draw_minimal_presentation(
        self,
        event: PresentationEvent,
        progress: float,
        remaining_ms: int,
    ) -> None:
        color = (232, 78, 55) if event.emphasis == "danger" else (222, 176, 86)
        center = self._presentation_text_center(event)
        title = event.title.upper()
        subtitle = event.subtitle.upper() if event.subtitle else ""
        detail = event.detail.upper() if event.detail else ""

        if event.kind == "claim":
            title_font = self._font_for_width(
                title,
                (self.fonts["hud_title"], self.fonts["hud_body"], self.fonts["hud_small"]),
                360,
            )
            self._blit_hud_text(title_font, title, center, anchor="center")
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (center[0], center[1] + 34),
                anchor="center",
                color=(255, 236, 179),
            )
            self._blit_hud_text(
                self.fonts["hud_body"],
                detail,
                (center[0], center[1] + 68),
                anchor="center",
                color=(255, 248, 220),
            )
            if event.allow_input and remaining_ms > 0:
                self._draw_call_liar_prompt(
                    (center[0], center[1] + 108),
                    remaining_ms,
                    progress,
                )
            return

        self._blit_hud_text(
            self.fonts["hud_title"],
            title,
            center,
            anchor="center",
            color=(255, 241, 199) if event.emphasis != "danger" else (255, 168, 132),
        )
        if subtitle:
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (center[0], center[1] + 46),
                anchor="center",
                color=color,
            )
        if detail:
            self._draw_centered_hud_lines(
                detail,
                pygame.Rect(center[0] - 330, center[1] + 78, 660, 58),
                self.fonts["hud_small"],
                (255, 235, 190),
            )
        self._draw_minimal_progress(
            pygame.Rect(center[0] - 170, center[1] + 144, 340, 4),
            color,
            progress,
        )

    def _presentation_text_center(self, event: PresentationEvent) -> tuple[int, int]:
        if event.kind == "reputation":
            return (SCREEN_WIDTH // 2, 592)
        return (SCREEN_WIDTH // 2, 350)

    def _draw_call_liar_prompt(
        self,
        center: tuple[int, int],
        remaining_ms: int,
        progress: float,
    ) -> None:
        font = self.fonts["hud_body"]
        label = font.render("CALL LIAR", True, (255, 241, 199))
        key_rect = pygame.Rect(0, 0, 32, 26)
        timer_text = str(math.ceil(remaining_ms / 1000))
        timer = font.render(timer_text, True, (255, 241, 199))
        gap = 10
        total_width = label.get_width() + gap + key_rect.width + gap + timer.get_width()
        left = center[0] - total_width // 2
        label_rect = self._blit_hud_text(
            font,
            "CALL LIAR",
            (left, center[1]),
            anchor="midleft",
            color=(255, 241, 199),
        )
        key_rect.midleft = (label_rect.right + gap, center[1])
        pygame.draw.rect(self.screen, (68, 38, 18), key_rect, border_radius=4)
        pygame.draw.rect(self.screen, (224, 172, 78), key_rect, 1, 4)
        key = font.render("X", True, (255, 241, 199))
        self.screen.blit(key, key.get_rect(center=key_rect.center))
        self._blit_hud_text(
            font,
            timer_text,
            (key_rect.right + gap, center[1]),
            anchor="midleft",
            color=(255, 241, 199),
        )
        self._draw_minimal_progress(
            pygame.Rect(center[0] - 92, center[1] + 20, 184, 4),
            (224, 172, 78),
            progress,
        )

    def _draw_minimal_progress(
        self,
        rect: pygame.Rect,
        color: tuple[int, int, int],
        progress: float,
    ) -> None:
        pygame.draw.rect(self.screen, (68, 38, 18), rect, border_radius=2)
        pygame.draw.rect(
            self.screen,
            color,
            pygame.Rect(rect.x, rect.y, max(2, int(rect.width * progress)), rect.height),
            border_radius=2,
        )

    def _draw_revolver_presentation(
        self,
        event: PresentationEvent,
        progress: float,
    ) -> None:
        reveal_at = 0.62
        reveal = progress >= reveal_at
        detail_lower = event.detail.lower()
        eliminated = "eliminated" in detail_lower
        loaded = "loaded" in detail_lower or event.emphasis == "danger"
        danger_result = reveal and (loaded or eliminated)
        accent = (232, 78, 55) if danger_result else (222, 176, 86)
        if reveal and eliminated:
            dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 34))
            self.screen.blit(dim, (0, 0))

        wheel_center = (SCREEN_WIDTH // 2, 226)
        spin_amount = min(progress / reveal_at, 1.0)
        spin_chamber = int(spin_amount * 28) % 6
        locked = reveal and event.chamber_index is not None
        active_chamber = event.chamber_index if locked else spin_chamber
        chamber_angle = (
            -math.tau * active_chamber / 6
            if locked
            else spin_amount * math.tau * 3.2
        )

        self._draw_revolver_chamber_wheel(
            wheel_center,
            active_chamber,
            chamber_angle,
            reveal=reveal,
            loaded=loaded,
            accent=accent,
        )
        pygame.draw.polygon(
            self.screen,
            accent,
            [
                (wheel_center[0], wheel_center[1] - 104),
                (wheel_center[0] - 9, wheel_center[1] - 86),
                (wheel_center[0] + 9, wheel_center[1] - 86),
            ],
        )

        title = (
            "ELIMINATED"
            if reveal and eliminated
            else "LOADED"
            if reveal and loaded
            else "SURVIVED"
            if reveal
            else "TRYING CHAMBER"
        )
        detail = event.detail.upper() if reveal else "THE CHAMBER TURNS"
        subtitle = event.subtitle.upper() if event.subtitle else ""
        title_color = (255, 160, 116) if danger_result else (255, 241, 199)
        self._blit_hud_text(
            self.fonts["hud_body"],
            "REVOLVER",
            (SCREEN_WIDTH // 2, wheel_center[1] + 110),
            anchor="center",
            color=(222, 176, 86),
        )
        self._blit_hud_text(
            self.fonts["hud_title"],
            title,
            (SCREEN_WIDTH // 2, wheel_center[1] + 150),
            anchor="center",
            color=title_color,
        )
        if subtitle:
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (SCREEN_WIDTH // 2, wheel_center[1] + 190),
                anchor="center",
                color=accent,
            )
        self._draw_centered_hud_lines(
            detail,
            pygame.Rect(SCREEN_WIDTH // 2 - 330, wheel_center[1] + 220, 660, 58),
            self.fonts["hud_small"],
            (255, 235, 190),
        )
        target = self._player_by_name(event.target_name)
        if target is not None:
            self._draw_revolver_status_chip(
                target,
                pygame.Rect(SCREEN_WIDTH // 2 - 54, wheel_center[1] + 286, 108, 26),
            )
        elif event.chance_percent is not None:
            self._blit_hud_text(
                self.fonts["hud_body"],
                f"{event.chance_percent}% LOADED",
                (SCREEN_WIDTH // 2, wheel_center[1] + 292),
                anchor="center",
                color=(222, 176, 86),
            )
        self._draw_minimal_progress(
            pygame.Rect(SCREEN_WIDTH // 2 - 210, wheel_center[1] + 324, 420, 5),
            accent,
            progress,
        )

    def _draw_revolver_chamber_wheel(
        self,
        center: tuple[int, int],
        active_chamber: int,
        chamber_angle: float,
        *,
        reveal: bool,
        loaded: bool,
        accent: tuple[int, int, int],
    ) -> None:
        shadow = pygame.Surface((190, 176), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 98), shadow.get_rect())
        self.screen.blit(shadow, shadow.get_rect(center=(center[0] + 7, center[1] + 12)))

        pygame.draw.circle(self.screen, (18, 11, 7), center, 82)
        pygame.draw.circle(self.screen, (92, 55, 27), center, 78)
        pygame.draw.circle(self.screen, (37, 26, 18), center, 66)
        pygame.draw.circle(self.screen, (226, 170, 73), center, 80, 2)
        pygame.draw.circle(self.screen, (139, 90, 38), center, 66, 3)
        pygame.draw.circle(self.screen, (12, 9, 7), center, 27)
        pygame.draw.circle(self.screen, (226, 170, 73), center, 27, 2)

        for index in range(6):
            theta = -math.pi / 2 + math.tau * index / 6 + chamber_angle
            chamber_center = (
                int(center[0] + math.cos(theta) * 43),
                int(center[1] + math.sin(theta) * 43),
            )
            is_active = index == active_chamber
            hole_radius = 16 if not is_active else 19
            pygame.draw.circle(self.screen, (9, 7, 5), chamber_center, hole_radius)
            pygame.draw.circle(self.screen, (218, 157, 62), chamber_center, hole_radius, 2)
            pygame.draw.circle(self.screen, (32, 22, 14), chamber_center, max(7, hole_radius - 6))
            if is_active and reveal:
                pygame.draw.circle(self.screen, accent, chamber_center, hole_radius + 4, 2)
                if loaded:
                    pygame.draw.circle(self.screen, (235, 184, 88), chamber_center, 9)
                    pygame.draw.circle(self.screen, (126, 45, 31), chamber_center, 5)
                else:
                    pygame.draw.circle(self.screen, (246, 214, 136), chamber_center, 5, 2)
            else:
                pygame.draw.circle(self.screen, (246, 214, 136), (chamber_center[0] - 4, chamber_center[1] - 4), 2)

    def _draw_reputation_presentation(
        self,
        event: PresentationEvent,
        progress: float,
    ) -> None:
        border = self.colors["gold"] if event.emphasis != "danger" else (216, 60, 44)
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 34))
        self.screen.blit(dim, (0, 0))
        width = 470
        panel = pygame.Rect((SCREEN_WIDTH - width) // 2, 578, width, 128)
        lift = int(math.sin(min(1, progress) * math.pi) * 8)
        panel.y -= lift
        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 10, 9, 214), surface.get_rect(), border_radius=18)
        pygame.draw.rect(surface, (*border, 230), surface.get_rect(), 2, 18)
        self.screen.blit(surface, panel.topleft)
        self._blit_shadow_text(
            self.fonts["hud_title"],
            event.title.upper(),
            self.colors["text"],
            (panel.x + 28, panel.y + 22),
        )
        self._blit_shadow_text(
            self.fonts["hud_title"],
            event.subtitle,
            border,
            (panel.right - 28, panel.y + 22),
            anchor="topright",
        )
        self._draw_wrapped_text(
            [event.detail],
            pygame.Rect(panel.x + 28, panel.y + 70, panel.width - 56, 48),
            self.fonts["hud_small"],
            self.colors["cream"],
        )

    def _font_for_width(
        self,
        text: str,
        fonts: tuple[pygame.font.Font, ...],
        width: int,
    ) -> pygame.font.Font:
        for font in fonts:
            if font.size(text)[0] <= width:
                return font
        return fonts[-1]
