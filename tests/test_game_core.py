from __future__ import annotations

import random
from pathlib import Path
import unittest

from constants import DEALER_EVENT_LINES, STARTING_HAND_SIZE
from src.actors.strategy import BunnyStrategy, StrategyFactory
from src.engine import GameEngine, GamePhase, GameState, NarrationEvent
from src.models.action import ActionType, TurnAction
from src.models.card import Card, Claim, ClaimRank, Deck, Rank, SpecialCardType, Suit
from src.models.evaluator import claim_is_truthful, evaluate_claim_rank
from src.models.player import ChamberResult, PlayerState, ReputationBand, Revolver
from src.persistence import MatchSnapshotStore


class EvaluatorTests(unittest.TestCase):
    def test_detects_pair(self) -> None:
        cards = [
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.ACE, suit=Suit.HEARTS),
        ]
        self.assertEqual(evaluate_claim_rank(cards), ClaimRank.PAIR)

    def test_detects_royal_flush(self) -> None:
        cards = [
            Card(rank=Rank.TEN, suit=Suit.HEARTS),
            Card(rank=Rank.JACK, suit=Suit.HEARTS),
            Card(rank=Rank.QUEEN, suit=Suit.HEARTS),
            Card(rank=Rank.KING, suit=Suit.HEARTS),
            Card(rank=Rank.ACE, suit=Suit.HEARTS),
        ]
        self.assertTrue(claim_is_truthful(cards, ClaimRank.STRAIGHT_FLUSH))
        self.assertEqual(evaluate_claim_rank(cards), ClaimRank.ROYAL_FLUSH)


class PlayerTests(unittest.TestCase):
    def test_reputation_band_thresholds(self) -> None:
        player = PlayerState(name="Tester", seat_index=0, reputation=75)
        self.assertEqual(player.reputation_band, ReputationBand.TRUSTED)
        player.reputation = 50
        self.assertEqual(player.reputation_band, ReputationBand.NEUTRAL)
        player.reputation = 35
        self.assertEqual(player.reputation_band, ReputationBand.SUSPECT)
        player.reputation = 10
        self.assertEqual(player.reputation_band, ReputationBand.NOTORIOUS)

    def test_shield_absorbs_bullet(self) -> None:
        player = PlayerState(name="Tester", seat_index=0)
        player.grant_shield()
        outcome = player.resolve_bullet()
        self.assertTrue(outcome.shield_used)
        self.assertFalse(outcome.eliminated)

    def test_loaded_chamber_eliminates_player(self) -> None:
        player = PlayerState(
            name="Tester",
            seat_index=0,
            revolver=Revolver(chambers=[ChamberResult.LOADED]),
        )
        outcome = player.resolve_bullet(random.Random(0))
        self.assertTrue(outcome.eliminated)
        self.assertTrue(player.eliminated)


class StrategyAndPersistenceTests(unittest.TestCase):
    def test_factory_builds_bunny_strategy(self) -> None:
        strategy = StrategyFactory.create(
            "bunny",
            owner_name="The Bunny",
            rng=random.Random(1),
        )
        self.assertIsInstance(strategy, BunnyStrategy)

    def test_snapshot_store_writes_and_reads_json(self) -> None:
        path = Path("tests/.latest_match_test.json")
        if path.exists():
            path.unlink()

        try:
            store = MatchSnapshotStore(path)
            state = GameState(
                players=[PlayerState(name="Player", seat_index=0)],
                dealer_index=0,
                current_turn_index=0,
                deck=Deck(cards=[]),
                round_number=2,
                phase=GamePhase.PLAYER_TURN,
                current_claim=Claim(
                    rank=ClaimRank.PAIR,
                    declared_by="Player",
                    card_count=2,
                ),
                public_memory_log=["Round 1 reveal"],
                narration_log=[
                    NarrationEvent(
                        round_number=2,
                        speaker="The Dealer",
                        text="A misfire. The table breathes.",
                    )
                ],
            )
            store.save_state(state)
            loaded = store.load_previous_summary()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["round_number"], 2)
            self.assertIn("turn_history", loaded)
            self.assertIn("narration_log", loaded)
        finally:
            if path.exists():
                path.unlink()

    def test_resume_match_restores_player_state(self) -> None:
        engine = GameEngine(random.Random(11))
        snapshot = {
            "round_number": 4,
            "phase": "player_turn",
            "dealer_index": 2,
            "current_turn_index": 0,
            "players": [
                {
                    "name": "Player",
                    "seat_index": 0,
                    "reputation": 72,
                    "shield_charges": 0,
                    "eliminated": False,
                    "profile_key": None,
                },
                {
                    "name": "The Wolf",
                    "seat_index": 1,
                    "reputation": 28,
                    "shield_charges": 0,
                    "eliminated": False,
                    "profile_key": "wolf",
                },
            ],
            "memory_log": ["Round 3 reveal"],
            "turn_history": [],
            "narration_log": [],
        }

        state = engine.resume_match(snapshot)

        self.assertEqual(state.round_number, 4)
        self.assertEqual(state.players[0].reputation_band, ReputationBand.TRUSTED)
        self.assertFalse(state.players[1].eliminated)
        self.assertIn(1, engine.ai_strategies)

    def test_engine_exposes_frontend_helpers(self) -> None:
        engine = GameEngine(random.Random(3))
        state = engine.bootstrap_match("Player")
        self.assertIs(engine.current_player(), state.players[0])
        self.assertFalse(engine.is_match_over())
        self.assertTrue(engine.player_can_make_claim(state.players[0]))
        self.assertIn(ClaimRank.HIGH_CARD, engine.legal_claim_ranks())
        self.assertIn("Round", engine.boot_summary())


class EngineSpecialCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = GameEngine(random.Random(7))
        self.state = self.engine.bootstrap_match("Player")
        self.player = self.state.players[0]
        self.opponent = self.state.players[1]

        for extra_player in self.state.players[2:]:
            extra_player.eliminated = True
            extra_player.receive_hand([])

        self.player.reputation = 50
        self.opponent.reputation = 50
        self.state.current_turn_index = self.player.seat_index
        self.state.current_claim = None
        self.state.current_claimant_index = None
        self.state.claim_stack.clear()
        self.state.public_memory_log.clear()
        self.state.turn_history.clear()
        self.state.double_down_claimant_index = None

    def test_blindfold_claim_commits_random_regular_cards(self) -> None:
        self.player.hand = [
            Card(special=SpecialCardType.BLINDFOLD),
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.KING, suit=Suit.HEARTS),
            Card(rank=Rank.QUEEN, suit=Suit.CLUBS),
        ]

        result = self.engine.process_action(
            self.player,
            TurnAction.claim(
                card_indices=[],
                claim_rank=ClaimRank.HIGH_CARD,
                special_card_index=0,
            ),
        )

        self.assertIn("Blindfold", result.summary)
        self.assertGreaterEqual(len(self.state.claim_stack), 1)
        self.assertLessEqual(len(self.state.claim_stack), 3)
        self.assertEqual(self.player.hand_size, 3 - len(self.state.claim_stack))

    def test_memory_wipe_clears_public_memory_before_claim(self) -> None:
        self.state.public_memory_log.extend(["Round 1 reveal", "Round 2 reveal"])
        self.player.hand = [
            Card(special=SpecialCardType.MEMORY_WIPE),
            Card(rank=Rank.ACE, suit=Suit.SPADES),
        ]

        result = self.engine.process_action(
            self.player,
            TurnAction.claim(
                card_indices=[1],
                claim_rank=ClaimRank.HIGH_CARD,
                special_card_index=0,
            ),
        )

        self.assertIn("wipes the table memory clean", result.summary)
        self.assertEqual(self.state.public_memory_log, [])

    def test_wildcard_hand_draws_new_cards_then_claims(self) -> None:
        self.player.hand = [
            Card(special=SpecialCardType.WILDCARD_HAND),
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.ACE, suit=Suit.HEARTS),
        ]
        self.state.deck = Deck(
            cards=[
                Card(rank=Rank.SEVEN, suit=Suit.CLUBS),
                Card(rank=Rank.EIGHT, suit=Suit.CLUBS),
                Card(rank=Rank.NINE, suit=Suit.CLUBS),
                Card(rank=Rank.TEN, suit=Suit.CLUBS),
                Card(rank=Rank.JACK, suit=Suit.CLUBS),
            ]
        )

        result = self.engine.process_action(
            self.player,
            TurnAction.claim(
                card_indices=[],
                claim_rank=ClaimRank.HIGH_CARD,
                special_card_index=0,
            ),
        )

        self.assertIn("draws new cards", result.summary)
        self.assertEqual(self.player.hand_size, 2)

    def test_ai_challenges_when_only_nonclaim_special_and_claim_active(self) -> None:
        self.player.hand = [Card(rank=Rank.ACE, suit=Suit.SPADES)]
        self.opponent.hand = [Card(special=SpecialCardType.MEMORY_WIPE)]

        self.engine.process_action(
            self.player,
            TurnAction.claim(card_indices=[0], claim_rank=ClaimRank.HIGH_CARD),
        )
        action = self.engine.choose_ai_action(self.opponent)

        self.assertEqual(action.action_type, ActionType.CHALLENGE)

    def test_ai_challenges_when_empty_hand_and_claim_active(self) -> None:
        self.player.hand = [Card(rank=Rank.ACE, suit=Suit.SPADES)]
        self.opponent.hand = []

        self.engine.process_action(
            self.player,
            TurnAction.claim(card_indices=[0], claim_rank=ClaimRank.HIGH_CARD),
        )
        action = self.engine.choose_ai_action(self.opponent)

        self.assertEqual(action.action_type, ActionType.CHALLENGE)

    def test_challenge_starts_new_dealt_round_with_loser_opening(self) -> None:
        self.player.hand = [Card(rank=Rank.ACE, suit=Suit.SPADES)]
        self.opponent.hand = [Card(rank=Rank.KING, suit=Suit.CLUBS)]
        self.opponent.revolver = Revolver(
            chambers=[ChamberResult.EMPTY] * 6,
        )
        round_number = self.state.round_number

        self.engine.process_action(
            self.player,
            TurnAction.claim(card_indices=[0], claim_rank=ClaimRank.HIGH_CARD),
        )
        self.engine.process_action(self.opponent, TurnAction.challenge())

        self.assertEqual(self.state.round_number, round_number + 1)
        self.assertIsNone(self.state.current_claim)
        self.assertEqual(self.state.current_turn_index, self.opponent.seat_index)
        self.assertEqual(self.player.hand_size, STARTING_HAND_SIZE)
        self.assertEqual(self.opponent.hand_size, STARTING_HAND_SIZE)
        for extra_player in self.state.players[2:]:
            self.assertEqual(extra_player.hand_size, 0)

    def test_special_only_opener_refreshes_before_ai_claim(self) -> None:
        self.opponent.hand = [Card(special=SpecialCardType.MEMORY_WIPE)]
        self.state.current_turn_index = self.opponent.seat_index
        self.state.deck = Deck(
            cards=[
                Card(special=SpecialCardType.SHIELD),
                Card(rank=Rank.ACE, suit=Suit.SPADES),
            ]
        )

        action = self.engine.choose_ai_action(self.opponent)

        self.assertEqual(action.action_type, ActionType.CLAIM)
        self.assertGreater(self.opponent.claimable_hand_size, 0)
        self.assertTrue(action.card_indices)

    def test_empty_opener_gets_new_deal_before_ai_claim(self) -> None:
        self.opponent.hand = []
        self.state.current_turn_index = self.opponent.seat_index
        round_number = self.state.round_number

        action = self.engine.choose_ai_action(self.opponent)

        self.assertEqual(self.state.round_number, round_number + 1)
        self.assertEqual(self.opponent.hand_size, STARTING_HAND_SIZE)
        self.assertEqual(action.action_type, ActionType.CLAIM)

    def test_engine_rejects_zero_card_special_claim(self) -> None:
        self.player.hand = [Card(special=SpecialCardType.SHIELD)]

        with self.assertRaises(ValueError):
            self.engine.process_action(
                self.player,
                TurnAction.claim(
                    card_indices=[],
                    claim_rank=ClaimRank.HIGH_CARD,
                    special_card_index=0,
                ),
            )

        self.assertEqual(self.player.hand_size, 1)

    def test_double_down_causes_two_bullet_spins_on_truthful_claim(self) -> None:
        self.player.hand = [
            Card(special=SpecialCardType.DOUBLE_DOWN),
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.ACE, suit=Suit.HEARTS),
        ]
        self.opponent.hand = [Card(rank=Rank.KING, suit=Suit.CLUBS)]
        self.opponent.revolver = Revolver(
            chambers=[ChamberResult.EMPTY, ChamberResult.EMPTY]
        )

        self.engine.process_action(
            self.player,
            TurnAction.claim(
                card_indices=[1, 2],
                claim_rank=ClaimRank.PAIR,
                special_card_index=0,
            ),
        )
        result = self.engine.process_action(self.opponent, TurnAction.challenge())

        self.assertIn("Double Down", result.summary)
        self.assertEqual(len(self.opponent.revolver.spent_indices), 2)

    def test_mirror_damage_redirects_truthful_challenge_penalty(self) -> None:
        self.player.hand = [
            Card(rank=Rank.ACE, suit=Suit.SPADES),
            Card(rank=Rank.ACE, suit=Suit.HEARTS),
        ]
        self.player.revolver = Revolver(chambers=[ChamberResult.EMPTY])
        self.opponent.hand = [Card(special=SpecialCardType.MIRROR_DAMAGE)]
        self.opponent.revolver = Revolver(chambers=[ChamberResult.LOADED])

        self.engine.process_action(
            self.player,
            TurnAction.claim(card_indices=[0, 1], claim_rank=ClaimRank.PAIR),
        )
        result = self.engine.process_action(
            self.opponent,
            TurnAction.challenge(special_card_index=0),
        )

        self.assertIn("Mirror Damage redirects", result.summary)
        self.assertEqual(len(self.player.revolver.spent_indices), 1)
        self.assertEqual(len(self.opponent.revolver.spent_indices), 0)

    def test_round_start_clears_unused_shields(self) -> None:
        self.player.shield_charges = 1
        self.opponent.shield_charges = 1
        self.engine.start_round()
        self.assertEqual(self.player.shield_charges, 0)
        self.assertEqual(self.opponent.shield_charges, 0)

    def test_notorious_claim_adds_contextual_narration(self) -> None:
        self.player.reputation = 15
        self.player.hand = [Card(rank=Rank.ACE, suit=Suit.SPADES)]
        narration_count = len(self.state.narration_log)

        self.engine.process_action(
            self.player,
            TurnAction.claim(card_indices=[0], claim_rank=ClaimRank.HIGH_CARD),
        )

        self.assertEqual(len(self.state.narration_log), narration_count + 1)
        self.assertIn(
            self.state.narration_log[-1].text,
            DEALER_EVENT_LINES["notorious_claim"],
        )

    def test_ghost_mode_claim_marks_turn_record_and_narration(self) -> None:
        self.player.hand = [Card(rank=Rank.ACE, suit=Suit.SPADES)]

        self.engine.process_action(
            self.player,
            TurnAction.claim(
                card_indices=[0],
                claim_rank=ClaimRank.HIGH_CARD,
                ghost_mode=True,
            ),
        )

        self.assertTrue(self.state.turn_history[-1].ghost_mode)
        self.assertIn(
            self.state.narration_log[-1].text,
            DEALER_EVENT_LINES["ghost_mode"],
        )


if __name__ == "__main__":
    unittest.main()
