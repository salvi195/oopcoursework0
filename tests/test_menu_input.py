from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.engine import GameState
from src.ui.game_app import BluffingGameApp, UIButton


class MemorySnapshotStore:
    def __init__(self) -> None:
        self.summary: dict | None = None

    def save_state(self, state: GameState) -> None:
        self.summary = {
            "round_number": state.round_number,
            "players": [
                {
                    "name": player.name,
                    "seat_index": player.seat_index,
                    "profile_key": player.profile_key,
                    "eliminated": player.eliminated,
                }
                for player in state.players
            ],
        }

    def load_previous_summary(self) -> dict | None:
        return self.summary


class MenuInputTests(unittest.TestCase):
    def tearDown(self) -> None:
        pygame.quit()

    def build_app(self) -> BluffingGameApp:
        app = BluffingGameApp()
        app.snapshot_store = MemorySnapshotStore()
        app.saved_summary = None
        return app

    def test_enter_key_starts_new_match_from_menu(self) -> None:
        app = self.build_app()

        app._handle_menu_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)
        )

        self.assertEqual(app.mode, "table")
        self.assertIsNotNone(app.state)
        self.assertIn("Round 1 begins", app.last_result)

    def test_menu_button_activation_starts_new_match(self) -> None:
        app = self.build_app()
        app.buttons = [
            UIButton("menu_new", "ENTER THE BAR", pygame.Rect(82, 348, 318, 54))
        ]

        app._handle_menu_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(100, 360))
        )

        self.assertEqual(app.mode, "table")
        self.assertIsNotNone(app.state)

    def test_touch_tap_on_menu_button_starts_new_match(self) -> None:
        app = self.build_app()
        app.buttons = [
            UIButton("menu_new", "ENTER THE BAR", pygame.Rect(82, 348, 318, 54))
        ]

        app._handle_menu_event(
            pygame.event.Event(pygame.FINGERDOWN, x=100 / 1280, y=360 / 800)
        )

        self.assertEqual(app.mode, "table")
        self.assertIsNotNone(app.state)


if __name__ == "__main__":
    unittest.main()
