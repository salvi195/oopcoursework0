from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random

from constants import (
    DEALER_EVENT_LINES,
    PLAYER_COUNT,
    STARTING_HAND_SIZE,
)
from src.actors.ai_profiles import DEALER_PROFILE, get_opponent_profiles
from src.actors.strategy import StrategyFactory
from src.models.action import ActionResult, ActionType, TurnAction
from src.models.card import Card, Claim, ClaimRank, Deck, SpecialCardType
from src.models.evaluator import claim_is_truthful
from src.models.player import BulletOutcome, PlayerState, TurnRecord


class GamePhase(str, Enum):
    PLAYER_TURN = "player_turn"
    ROUND_OVER = "round_over"
    MATCH_OVER = "match_over"


@dataclass(frozen=True, slots=True)
class NarrationEvent:
    round_number: int
    speaker: str
    text: str


@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    dealer_index: int
    current_turn_index: int
    deck: Deck
    round_number: int = 1
    phase: GamePhase = GamePhase.PLAYER_TURN
    current_claim: Claim | None = None
    current_claimant_index: int | None = None
    claim_stack: list[Card] = field(default_factory=list)
    public_memory_log: list[str] = field(default_factory=list)
    turn_history: list[TurnRecord] = field(default_factory=list)
    narration_log: list[NarrationEvent] = field(default_factory=list)
    double_down_claimant_index: int | None = None


class GameEngine:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.state: GameState | None = None
        self.ai_strategies: dict[int, object] = {}

    def bootstrap_match(self, player_name: str) -> GameState:
        players = [PlayerState(name=player_name, seat_index=0, is_human=True)]
        self.ai_strategies = {}

        for seat_index, profile in enumerate(
            get_opponent_profiles(PLAYER_COUNT - 1, self.rng),
            start=1,
        ):
            players.append(
                PlayerState(
                    name=profile.display_name,
                    seat_index=seat_index,
                    profile_key=profile.key,
                )
            )
            self.ai_strategies[seat_index] = StrategyFactory.create(
                profile.key,
                owner_name=profile.display_name,
                rng=self.rng,
            )

        deck = Deck.standard(self.rng)
        for player in players:
            player.receive_hand(deck.draw(STARTING_HAND_SIZE))

        self.state = GameState(
            players=players,
            dealer_index=0,
            current_turn_index=0,
            deck=deck,
        )
        return self.state

    def resume_match(self, snapshot: dict) -> GameState:
        players: list[PlayerState] = []
        self.ai_strategies = {}

        for player_data in snapshot.get("players", []):
            player = PlayerState(
                name=player_data["name"],
                seat_index=player_data["seat_index"],
                is_human=player_data.get("profile_key") is None,
                profile_key=player_data.get("profile_key"),
                reputation=player_data.get("reputation", 50),
                shield_charges=player_data.get("shield_charges", 0),
                eliminated=player_data.get("eliminated", False),
            )
            players.append(player)
            if player.profile_key is not None:
                self.ai_strategies[player.seat_index] = StrategyFactory.create(
                    player.profile_key,
                    owner_name=player.name,
                    rng=self.rng,
                )

        self.state = GameState(
            players=players,
            dealer_index=snapshot.get("dealer_index", 0),
            current_turn_index=snapshot.get("current_turn_index", 0),
            deck=Deck(cards=[]),
            round_number=snapshot.get("round_number", 1),
            phase=GamePhase(snapshot.get("phase", GamePhase.PLAYER_TURN.value)),
            public_memory_log=list(snapshot.get("memory_log", [])),
            turn_history=[
                TurnRecord(**record) for record in snapshot.get("turn_history", [])
            ],
            narration_log=[
                NarrationEvent(**event) for event in snapshot.get("narration_log", [])
            ],
        )
        return self.state

    def start_round(self) -> None:
        state = self._require_state()
        state.round_number += 1
        state.phase = GamePhase.PLAYER_TURN
        state.current_claim = None
        state.current_claimant_index = None
        state.claim_stack.clear()
        state.double_down_claimant_index = None

        for player in state.players:
            player.shield_charges = 0
        for strategy in self.ai_strategies.values():
            strategy.on_round_started()

    def process_action(self, player: PlayerState, action: TurnAction) -> ActionResult:
        if action.action_type == ActionType.CLAIM:
            return self._process_claim(player, action)
        return self._process_challenge(player, action)

    def _process_claim(self, player: PlayerState, action: TurnAction) -> ActionResult:
        state = self._require_state()
        summary_parts: list[str] = []
        narration_key: str | None = None

        claim_cards: list[Card]
        special = self._peek_special(player, action.special_card_index)

        if special == SpecialCardType.BLINDFOLD:
            self._consume_special(player, action.special_card_index)
            blindfold_count = action.blindfold_card_count or 1
            claimable_indices = player.claimable_card_indices
            chosen_indices = self.rng.sample(
                claimable_indices,
                k=min(blindfold_count, len(claimable_indices)),
            )
            claim_cards = player.remove_cards_by_indices(chosen_indices)
            summary_parts.append(
                f"{player.name} uses Blindfold and commits "
                f"{len(claim_cards)} hidden cards."
            )
            narration_key = "blindfold_claim"
        elif special == SpecialCardType.MEMORY_WIPE:
            adjusted_indices = self._consume_special(
                player,
                action.special_card_index,
                list(action.card_indices),
            )
            state.public_memory_log.clear()
            claim_cards = player.remove_cards_by_indices(adjusted_indices)
            summary_parts.append(
                f"{player.name} wipes the table memory clean before claiming."
            )
            narration_key = "memory_wipe"
        elif special == SpecialCardType.WILDCARD_HAND:
            self._consume_special(player, action.special_card_index)
            player.receive_hand([])
            player.draw_from_deck(state.deck, 5)
            chosen_indices = player.claimable_card_indices[:3]
            claim_cards = player.remove_cards_by_indices(chosen_indices)
            summary_parts.append(
                f"{player.name} draws five new cards with Wildcard Hand."
            )
            narration_key = "wildcard_hand"
        else:
            adjusted_indices = list(action.card_indices)
            if special == SpecialCardType.DOUBLE_DOWN:
                adjusted_indices = self._consume_special(
                    player,
                    action.special_card_index,
                    adjusted_indices,
                )
                state.double_down_claimant_index = player.seat_index
                summary_parts.append(f"{player.name} commits with Double Down.")
            elif special == SpecialCardType.SHIELD:
                adjusted_indices = self._consume_special(
                    player,
                    action.special_card_index,
                    adjusted_indices,
                )
                player.grant_shield()
                summary_parts.append(f"{player.name} raises a Shield.")
                narration_key = "shield_turn"
            claim_cards = player.remove_cards_by_indices(adjusted_indices)

        state.claim_stack = claim_cards
        state.current_claim = Claim(
            rank=action.claim_rank or ClaimRank.HIGH_CARD,
            declared_by=player.name,
            card_count=len(claim_cards),
        )
        state.current_claimant_index = player.seat_index
        state.phase = GamePhase.PLAYER_TURN

        was_bluff = not claim_is_truthful(claim_cards, state.current_claim.rank)
        state.turn_history.append(
            TurnRecord(
                round_number=state.round_number,
                actor_name=player.name,
                action=ActionType.CLAIM.value,
                actor_profile_key=player.profile_key,
                claim_text=state.current_claim.rank.name,
                claim_jump=1,
                claim_rank_value=int(state.current_claim.rank),
                card_count=len(claim_cards),
                was_bluff=was_bluff,
                presentation_style=action.presentation_style.value,
                reputation_band=player.reputation_band.value,
                special_used=special.value if special is not None else None,
                ghost_mode=action.ghost_mode,
            )
        )

        if action.ghost_mode:
            narration_key = "ghost_mode"
        elif player.reputation_band.value == "notorious":
            narration_key = "notorious_claim"
        elif player.reputation_band.value == "trusted":
            narration_key = narration_key or "trusted_claim"

        if narration_key is not None:
            self._append_narration(narration_key)

        state.current_turn_index = self._next_active_seat(player.seat_index)
        claim_name = state.current_claim.rank.name.replace("_", " ").title()
        summary_parts.append(
            f"{player.name} claims {claim_name} with {len(claim_cards)} card(s)."
        )
        self._notify_ai(state.turn_history[-1])
        return ActionResult(summary=" ".join(summary_parts))

    def _process_challenge(
        self,
        player: PlayerState,
        action: TurnAction,
    ) -> ActionResult:
        state = self._require_state()
        if state.current_claim is None or state.current_claimant_index is None:
            return ActionResult(summary=f"{player.name} has nothing to challenge.")

        claimant = state.players[state.current_claimant_index]
        special = self._peek_special(player, action.special_card_index)
        if special is not None:
            self._consume_special(player, action.special_card_index)

        if special == SpecialCardType.SHIELD:
            player.grant_shield()

        truthful = claim_is_truthful(state.claim_stack, state.current_claim.rank)
        challenge_successful = not truthful
        bullet_target = player if truthful else claimant
        summary_parts = [f"{player.name} challenges {claimant.name}."]

        if truthful and special == SpecialCardType.MIRROR_DAMAGE:
            bullet_target = claimant
            summary_parts.append("Mirror Damage redirects the penalty.")

        bullet_spins = 1
        if truthful and state.double_down_claimant_index == claimant.seat_index:
            bullet_spins = 2
            summary_parts.append("Double Down forces two bullet spins.")

        outcomes: list[BulletOutcome] = []
        for _ in range(bullet_spins):
            outcome = bullet_target.resolve_bullet(self.rng)
            outcomes.append(outcome)
            if outcome.eliminated:
                break

        state.turn_history.append(
            TurnRecord(
                round_number=state.round_number,
                actor_name=player.name,
                action=ActionType.CHALLENGE.value,
                actor_profile_key=player.profile_key,
                presentation_style=action.presentation_style.value,
                reputation_band=player.reputation_band.value,
                special_used=special.value if special is not None else None,
                target_name=claimant.name,
                bullet_target_name=bullet_target.name,
                bullets_resolved=len(outcomes),
                challenge_successful=challenge_successful,
                ghost_mode=action.ghost_mode,
            )
        )

        if any(outcome.eliminated for outcome in outcomes):
            summary_parts.append(f"{bullet_target.name} is eliminated.")
            self._append_narration("elimination")
        elif any(outcome.result.value == "misfire" for outcome in outcomes):
            self._append_narration("misfire")
        elif challenge_successful:
            summary_parts.append(f"{claimant.name}'s bluff is exposed.")
            self._append_narration("challenge_catches_bluff")
        else:
            summary_parts.append(f"{claimant.name}'s claim holds.")
            self._append_narration("challenge_fails")

        state.current_claim = None
        state.current_claimant_index = None
        state.claim_stack.clear()
        state.double_down_claimant_index = None
        state.current_turn_index = self._next_active_seat(player.seat_index)

        match_winner = self._winner_name()
        if match_winner is not None:
            state.phase = GamePhase.MATCH_OVER

        self._notify_ai(state.turn_history[-1])
        return ActionResult(
            summary=" ".join(summary_parts),
            match_ended=match_winner is not None,
            winner_name=match_winner,
        )

    def _peek_special(
        self,
        player: PlayerState,
        special_card_index: int | None,
    ) -> SpecialCardType | None:
        if special_card_index is None:
            return None
        if not 0 <= special_card_index < len(player.hand):
            return None
        return player.hand[special_card_index].special

    def _consume_special(
        self,
        player: PlayerState,
        special_card_index: int | None,
        indexed_cards: list[int] | None = None,
    ) -> list[int]:
        if special_card_index is None:
            return indexed_cards or []
        player.remove_card_at_index(special_card_index)
        if indexed_cards is None:
            return []
        return [
            index - 1 if index > special_card_index else index
            for index in indexed_cards
            if index != special_card_index
        ]

    def _append_narration(self, event_key: str) -> None:
        state = self._require_state()
        lines = DEALER_EVENT_LINES.get(event_key)
        if not lines:
            return
        state.narration_log.append(
            NarrationEvent(
                round_number=state.round_number,
                speaker=DEALER_PROFILE.display_name,
                text=self.rng.choice(lines),
            )
        )

    def _notify_ai(self, turn_record: TurnRecord) -> None:
        for strategy in self.ai_strategies.values():
            strategy.observe_turn(turn_record)

    def _next_active_seat(self, current_seat: int) -> int:
        state = self._require_state()
        for offset in range(1, len(state.players) + 1):
            candidate = (current_seat + offset) % len(state.players)
            if not state.players[candidate].eliminated:
                return candidate
        return current_seat

    def _winner_name(self) -> str | None:
        state = self._require_state()
        remaining = [player.name for player in state.players if not player.eliminated]
        if len(remaining) == 1:
            return remaining[0]
        return None

    def _require_state(self) -> GameState:
        if self.state is None:
            raise RuntimeError("Game state has not been initialised.")
        return self.state
