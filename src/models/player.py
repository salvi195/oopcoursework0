from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random

from constants import (
    MAX_REPUTATION,
    MIN_REPUTATION,
    REVOLVER_CHAMBERS,
    STARTING_REPUTATION,
)
from src.models.card import Card, Deck


class ChamberResult(str, Enum):
    LOADED = "loaded"
    MISFIRE = "misfire"
    EMPTY = "empty"
    SPENT = "spent"


class ReputationBand(str, Enum):
    TRUSTED = "trusted"
    NEUTRAL = "neutral"
    SUSPECT = "suspect"
    NOTORIOUS = "notorious"


@dataclass(slots=True)
class BulletOutcome:
    result: ChamberResult
    chamber_index: int | None
    shield_used: bool
    eliminated: bool


@dataclass(slots=True)
class TurnRecord:
    round_number: int
    actor_name: str
    action: str
    actor_profile_key: str | None = None
    claim_text: str | None = None
    claim_jump: int | None = None
    claim_rank_value: int | None = None
    card_count: int | None = None
    was_bluff: bool | None = None
    presentation_style: str | None = None
    reputation_band: str | None = None
    special_used: str | None = None
    target_name: str | None = None
    bullet_target_name: str | None = None
    bullets_resolved: int = 0
    challenge_successful: bool | None = None
    bullet_results: list[str] = field(default_factory=list)
    bullet_chambers: list[int | None] = field(default_factory=list)
    bullet_shields: list[bool] = field(default_factory=list)
    bullet_eliminations: list[bool] = field(default_factory=list)
    bullet_chances: list[int] = field(default_factory=list)
    reputation_deltas: dict[str, int] = field(default_factory=dict)
    ghost_mode: bool = False


@dataclass(slots=True)
class Revolver:
    chambers: list[ChamberResult]
    spent_indices: set[int] = field(default_factory=set)

    @classmethod
    def randomised(cls, rng: random.Random | None = None) -> "Revolver":
        rng = rng or random.Random()
        chambers = [ChamberResult.EMPTY] * REVOLVER_CHAMBERS
        loaded_index, misfire_index = rng.sample(range(REVOLVER_CHAMBERS), 2)
        chambers[loaded_index] = ChamberResult.LOADED
        chambers[misfire_index] = ChamberResult.MISFIRE
        return cls(chambers=chambers)

    def available_indices(self) -> list[int]:
        return [
            index
            for index in range(len(self.chambers))
            if index not in self.spent_indices
        ]

    def fire(self, rng: random.Random | None = None) -> tuple[int, ChamberResult]:
        rng = rng or random.Random()
        choices = self.available_indices()
        if not choices:
            raise RuntimeError("No revolver chambers remain to spin.")
        chamber_index = rng.choice(choices)
        self.spent_indices.add(chamber_index)
        result = self.chambers[chamber_index]
        self.chambers[chamber_index] = ChamberResult.SPENT
        return chamber_index, result


@dataclass(slots=True)
class PlayerState:
    name: str
    seat_index: int
    is_human: bool = False
    profile_key: str | None = None
    reputation: int = STARTING_REPUTATION
    hand: list[Card] = field(default_factory=list)
    shield_charges: int = 0
    eliminated: bool = False
    revolver: Revolver = field(default_factory=Revolver.randomised)

    def receive_hand(self, cards: list[Card]) -> None:
        self.hand = list(cards)

    def draw_from_deck(self, deck: Deck, count: int) -> None:
        self.hand.extend(deck.draw(count))

    def remove_card_at_index(self, index: int) -> Card:
        return self.hand.pop(index)

    def remove_cards_by_indices(self, indices: list[int]) -> list[Card]:
        removed_cards: list[Card] = []
        for index in sorted(indices, reverse=True):
            removed_cards.append(self.hand.pop(index))
        removed_cards.reverse()
        return removed_cards

    def change_reputation(self, delta: int) -> None:
        self.reputation = max(
            MIN_REPUTATION,
            min(MAX_REPUTATION, self.reputation + delta),
        )

    @property
    def reputation_band(self) -> ReputationBand:
        if self.reputation >= 70:
            return ReputationBand.TRUSTED
        if self.reputation >= 45:
            return ReputationBand.NEUTRAL
        if self.reputation >= 25:
            return ReputationBand.SUSPECT
        return ReputationBand.NOTORIOUS

    def grant_shield(self, charges: int = 1) -> None:
        self.shield_charges += charges

    def resolve_bullet(self, rng: random.Random | None = None) -> BulletOutcome:
        if self.shield_charges > 0:
            self.shield_charges -= 1
            return BulletOutcome(
                result=ChamberResult.EMPTY,
                chamber_index=None,
                shield_used=True,
                eliminated=False,
            )

        chamber_index, result = self.revolver.fire(rng)
        eliminated = result == ChamberResult.LOADED
        self.eliminated = eliminated
        return BulletOutcome(
            result=result,
            chamber_index=chamber_index,
            shield_used=False,
            eliminated=eliminated,
        )

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    @property
    def claimable_card_indices(self) -> list[int]:
        return [index for index, card in enumerate(self.hand) if not card.is_special]

    @property
    def claimable_hand_size(self) -> int:
        return len(self.claimable_card_indices)

    def special_cards(self) -> list[tuple[int, Card]]:
        return [
            (index, card)
            for index, card in enumerate(self.hand)
            if card.is_special
        ]
