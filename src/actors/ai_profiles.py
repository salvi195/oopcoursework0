from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True, slots=True)
class AIProfile:
    key: str
    display_name: str


OPPONENT_PROFILES: tuple[AIProfile, ...] = (
    AIProfile(
        key="dante",
        display_name="Dante",
    ),
    AIProfile(
        key="ash",
        display_name="Ash",
    ),
    AIProfile(
        key="mr_fold",
        display_name="Mr. Fold",
    ),
    AIProfile(
        key="vesper",
        display_name="Vesper",
    ),
    AIProfile(
        key="fox",
        display_name="The Fox",
    ),
)

DEALER_PROFILE = AIProfile(
    key="dealer",
    display_name="The Dealer",
)


def get_opponent_profiles(
    count: int = 4,
    rng: random.Random | None = None,
) -> list[AIProfile]:
    rng = rng or random.Random()
    if count >= len(OPPONENT_PROFILES):
        return list(OPPONENT_PROFILES)
    return rng.sample(list(OPPONENT_PROFILES), count)