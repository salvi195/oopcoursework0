from __future__ import annotations

import random

from constants import SCREEN_HEIGHT, SCREEN_WIDTH, TARGET_FPS
from src.engine import GameEngine
from src.ui.assets import build_label
from src.ui.theme import DEFAULT_THEME

try:
    import pygame
except ImportError:  # pragma: no cover - depends on local environment
    pygame = None


class BluffingGameApp:
    def __init__(self, player_name: str = "Player") -> None:
        self.player_name = build_label(player_name, "Player")
        self.engine = GameEngine(random.Random())

    def run(self) -> None:
        state = self.engine.bootstrap_match(self.player_name)
        if pygame is None:
            self._run_console_fallback(state)
            return

        try:
            pygame.init()
            screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        except Exception:  # pragma: no cover - display setup depends on local machine
            self._run_console_fallback(state)
            return

        clock = pygame.time.Clock()
        title_font = pygame.font.Font(None, 64)
        body_font = pygame.font.Font(None, 30)
        running = True

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    running = False

            screen.fill(DEFAULT_THEME.background)
            pygame.draw.rect(
                screen,
                DEFAULT_THEME.felt,
                pygame.Rect(90, 120, SCREEN_WIDTH - 180, SCREEN_HEIGHT - 240),
                border_radius=28,
            )

            title = title_font.render("Bluffing Game", True, DEFAULT_THEME.accent)
            subtitle = body_font.render(
                "Core systems loaded. Press Enter or Esc to close.",
                True,
                DEFAULT_THEME.text_primary,
            )
            screen.blit(title, (100, 50))
            screen.blit(subtitle, (100, 120))

            for index, player in enumerate(state.players):
                player_line = body_font.render(
                    f"{player.name}: reputation {player.reputation}, cards {player.hand_size}",
                    True,
                    DEFAULT_THEME.text_primary if not player.eliminated else DEFAULT_THEME.text_muted,
                )
                screen.blit(player_line, (120, 200 + index * 44))

            pygame.display.flip()
            clock.tick(TARGET_FPS)

        pygame.quit()

    def _run_console_fallback(self, state) -> None:
        print("Bluffing Game bootstrap completed.")
        for player in state.players:
            print(f"- {player.name}: reputation {player.reputation}, cards {player.hand_size}")
