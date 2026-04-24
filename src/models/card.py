from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
import random

from constants import SPECIAL_CARD_COPIES


class Suit(str, Enum):
    HEARTS = "hearts"
    DIAMONDS = "diamonds"
    CLUBS = "clubs"
    SPADES = "spades"

    @property
    def symbol(self) -> str:
        return {
            Suit.HEARTS: "H",
            Suit.DIAMONDS: "D",
            Suit.CLUBS: "C",
            Suit.SPADES: "S",
        }[self]


class Rank(IntEnum):
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def short_label(self) -> str:
        return {
            Rank.SEVEN: "7",
            Rank.EIGHT: "8",
            Rank.NINE: "9",
            Rank.TEN: "10",
            Rank.JACK: "J",
            Rank.QUEEN: "Q",
            Rank.KING: "K",
            Rank.ACE: "A",
        }[self]


class SpecialCardType(str, Enum):
    BLINDFOLD = "blindfold"
    MEMORY_WIPE = "memory_wipe"
    WILDCARD_HAND = "wildcard_hand"
    DOUBLE_DOWN = "double_down"
    MIRROR_DAMAGE = "mirror_damage"
    SHIELD = "shield"

    @property
    def display_name(self) -> str:
        return {
            SpecialCardType.BLINDFOLD: "Blindfold",
            SpecialCardType.MEMORY_WIPE: "Memory Wipe",
            SpecialCardType.WILDCARD_HAND: "Wildcard Hand",
            SpecialCardType.DOUBLE_DOWN: "Double Down",
            SpecialCardType.MIRROR_DAMAGE: "Mirror Damage",
            SpecialCardType.SHIELD: "Shield",
        }[self]


class ClaimRank(IntEnum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


@dataclass(frozen=True, slots=True)
class Claim:
    rank: ClaimRank
    declared_by: str
    card_count: int


@dataclass(frozen=True, slots=True)
class Card:
    rank: Rank | None = None
    suit: Suit | None = None
    special: SpecialCardType | None = None

    @property
    def is_special(self) -> bool:
        return self.special is not None

    @property
    def short_label(self) -> str:
        if self.special is not None:
            return self.special.display_name
        if self.rank is None or self.suit is None:
            return "Unknown"
        return f"{self.rank.short_label}{self.suit.symbol}"


@dataclass(slots=True)
class Deck:
    cards: list[Card] = field(default_factory=list)

    @classmethod
    def standard(cls, rng: random.Random | None = None) -> "Deck":
        cards = [
            Card(rank=rank, suit=suit)
            for suit in Suit
            for rank in Rank
        ]
        for special in SpecialCardType:
            for _ in range(SPECIAL_CARD_COPIES):
                cards.append(Card(special=special))

        rng = rng or random.Random()
        rng.shuffle(cards)
        return cls(cards=cards)

    def draw(self, count: int) -> list[Card]:
        if count <= 0 or not self.cards:
            return []
        actual_count = min(count, len(self.cards))
        drawn = self.cards[-actual_count:]
        del self.cards[-actual_count:]
        return drawn
