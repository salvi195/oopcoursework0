from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from src.models.card import ClaimRank


class ActionType(str, Enum):
    CLAIM = "claim"
    CHALLENGE = "challenge"


class PresentationStyle(str, Enum):
    NEUTRAL = "neutral"
    AGGRESSIVE = "aggressive"
    MIRRORED = "mirrored"
    COMPOSED = "composed"
    GHOST = "ghost"
    THEATRICAL = "theatrical"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class TurnAction:
    action_type: ActionType
    card_indices: tuple[int, ...] = ()
    claim_rank: ClaimRank | None = None
    presentation_style: PresentationStyle = PresentationStyle.NEUTRAL
    special_card_index: int | None = None
    blindfold_card_count: int | None = None
    ghost_mode: bool = False
    note: str = ""

    @classmethod
    def claim(
        cls,
        card_indices: list[int] | tuple[int, ...],
        claim_rank: ClaimRank,
        presentation_style: PresentationStyle = PresentationStyle.NEUTRAL,
        special_card_index: int | None = None,
        blindfold_card_count: int | None = None,
        ghost_mode: bool = False,
        note: str = "",
    ) -> "TurnAction":
        return cls(
            action_type=ActionType.CLAIM,
            card_indices=tuple(card_indices),
            claim_rank=claim_rank,
            presentation_style=presentation_style,
            special_card_index=special_card_index,
            blindfold_card_count=blindfold_card_count,
            ghost_mode=ghost_mode,
            note=note,
        )

    @classmethod
    def challenge(
        cls,
        presentation_style: PresentationStyle = PresentationStyle.NEUTRAL,
        special_card_index: int | None = None,
        ghost_mode: bool = False,
        note: str = "",
    ) -> "TurnAction":
        return cls(
            action_type=ActionType.CHALLENGE,
            presentation_style=presentation_style,
            special_card_index=special_card_index,
            ghost_mode=ghost_mode,
            note=note,
        )

    def with_special(
        self,
        special_card_index: int,
        blindfold_card_count: int | None = None,
    ) -> "TurnAction":
        return replace(
            self,
            special_card_index=special_card_index,
            blindfold_card_count=blindfold_card_count,
        )


@dataclass(slots=True)
class ActionResult:
    summary: str
    round_ended: bool = False
    match_ended: bool = False
    winner_name: str | None = None