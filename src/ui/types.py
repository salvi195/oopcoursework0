from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.models.action import ActionType
from src.models.card import SpecialCardType


@dataclass(slots=True)
class UIButton:
    key: str
    label: str
    rect: pygame.Rect
    value: object | None = None
    enabled: bool = True


@dataclass(slots=True)
class PlayerVisualHold:
    reputation: int
    eliminated: bool
    spent_chambers: int


def allowed_specials_for_action(action_type: ActionType) -> set[SpecialCardType]:
    if action_type == ActionType.CLAIM:
        return {
            SpecialCardType.BLINDFOLD,
            SpecialCardType.DOUBLE_DOWN,
            SpecialCardType.MEMORY_WIPE,
            SpecialCardType.WILDCARD_HAND,
            SpecialCardType.SHIELD,
        }
    return {
        SpecialCardType.MEMORY_WIPE,
        SpecialCardType.MIRROR_DAMAGE,
        SpecialCardType.SHIELD,
    }
