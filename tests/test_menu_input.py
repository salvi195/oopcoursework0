from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.engine import GameState
from src.models.card import Card, Claim, ClaimRank, Rank, SpecialCardType, Suit
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

        self.assertEqual(app.mode, "menu")
        self.assertEqual(app.menu_loading_action, "new")
        app._update_menu_loading(
            app.menu_loading_started_at + app.menu_loading_duration_ms
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

        self.assertEqual(app.menu_loading_action, "new")
        app._update_menu_loading(
            app.menu_loading_started_at + app.menu_loading_duration_ms
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

        self.assertEqual(app.menu_loading_action, "new")
        app._update_menu_loading(
            app.menu_loading_started_at + app.menu_loading_duration_ms
        )

        self.assertEqual(app.mode, "table")
        self.assertIsNotNone(app.state)

    def test_blindfold_controls_hidden_without_regular_cards(self) -> None:
        app = self.build_app()
        app._start_new_match()
        self.assertIsNotNone(app.state)
        player = app.state.players[0]
        player.hand = [Card(special=SpecialCardType.BLINDFOLD)]
        app.selected_special_index = 0
        app.selected_cards.clear()

        app._build_table_buttons(pygame.Rect(1000, 206, 244, 286), 224)

        button_keys = {button.key for button in app.buttons}
        self.assertNotIn("blindfold_minus", button_keys)
        self.assertNotIn("blindfold_plus", button_keys)
        confirm = next(button for button in app.buttons if button.key == "confirm_claim")
        self.assertFalse(confirm.enabled)

    def test_blindfold_controls_hidden_with_regular_cards(self) -> None:
        app = self.build_app()
        app._start_new_match()
        self.assertIsNotNone(app.state)
        player = app.state.players[0]
        player.hand = [
            Card(special=SpecialCardType.BLINDFOLD),
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.KING, suit=Suit.HEARTS),
        ]
        app.selected_special_index = 0

        app._build_table_buttons(pygame.Rect(1000, 206, 244, 286), 224)
        button_keys = {button.key for button in app.buttons}
        confirm = next(button for button in app.buttons if button.key == "confirm_claim")

        self.assertNotIn("blindfold_minus", button_keys)
        self.assertNotIn("blindfold_plus", button_keys)
        self.assertTrue(confirm.enabled)

    def test_empty_hand_only_offers_challenge_when_claim_active(self) -> None:
        app = self.build_app()
        app._start_new_match()
        self.assertIsNotNone(app.state)
        player = app.state.players[0]
        opponent = app.state.players[1]
        player.hand = []
        app.state.current_claim = Claim(
            rank=ClaimRank.PAIR,
            declared_by=opponent.name,
            card_count=1,
        )
        app.state.current_claimant_index = opponent.seat_index
        app.state.current_turn_index = player.seat_index
        app.buttons = []

        app._build_table_buttons(pygame.Rect(1000, 206, 244, 286), 224)

        button_keys = {button.key for button in app.buttons}
        self.assertEqual(button_keys, {"challenge"})
        self.assertTrue(app.buttons[0].enabled)
        self.assertTrue(any("Call Liar" in line for line in app._action_lines()))


if __name__ == "__main__":
    unittest.main()
