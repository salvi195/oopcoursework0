from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from src.models.card import Card, ClaimRank, Rank, Suit


def evaluate_claim_rank(cards: Iterable[Card]) -> ClaimRank:
    regular_cards = [card for card in cards if not card.is_special and card.rank and card.suit]
    if not regular_cards:
        return ClaimRank.HIGH_CARD

    rank_counts = Counter(card.rank for card in regular_cards)
    suit_counts = Counter(card.suit for card in regular_cards)

    if _has_royal_flush(regular_cards):
        return ClaimRank.ROYAL_FLUSH
    if _has_straight_flush(regular_cards):
        return ClaimRank.STRAIGHT_FLUSH
    if any(count >= 4 for count in rank_counts.values()):
        return ClaimRank.FOUR_OF_A_KIND
    if _has_full_house(rank_counts):
        return ClaimRank.FULL_HOUSE
    if any(count >= 5 for count in suit_counts.values()):
        return ClaimRank.FLUSH
    if _has_straight(rank_counts):
        return ClaimRank.STRAIGHT
    if any(count >= 3 for count in rank_counts.values()):
        return ClaimRank.THREE_OF_A_KIND
    if sum(1 for count in rank_counts.values() if count >= 2) >= 2:
        return ClaimRank.TWO_PAIR
    if any(count >= 2 for count in rank_counts.values()):
        return ClaimRank.PAIR
    return ClaimRank.HIGH_CARD


def claim_is_truthful(cards: Iterable[Card], claimed_rank: ClaimRank) -> bool:
    return evaluate_claim_rank(cards) >= claimed_rank


def _has_full_house(rank_counts: Counter[Rank]) -> bool:
    triples = [rank for rank, count in rank_counts.items() if count >= 3]
    pairs = [rank for rank, count in rank_counts.items() if count >= 2]
    return any(pair_rank != triple_rank for triple_rank in triples for pair_rank in pairs)


def _has_straight(rank_counts: Counter[Rank]) -> bool:
    ordered = sorted({int(rank) for rank in rank_counts})
    return _has_consecutive_run(ordered, needed_length=5)


def _has_straight_flush(cards: list[Card]) -> bool:
    by_suit: dict[Suit, set[int]] = {}
    for card in cards:
        by_suit.setdefault(card.suit, set()).add(int(card.rank))
    return any(_has_consecutive_run(sorted(ranks), needed_length=5) for ranks in by_suit.values())


def _has_royal_flush(cards: list[Card]) -> bool:
    target = {10, 11, 12, 13, 14}
    by_suit: dict[Suit, set[int]] = {}
    for card in cards:
        by_suit.setdefault(card.suit, set()).add(int(card.rank))
    return any(target.issubset(ranks) for ranks in by_suit.values())


def _has_consecutive_run(values: list[int], needed_length: int) -> bool:
    if len(values) < needed_length:
        return False

    run_length = 1
    previous = values[0]
    for value in values[1:]:
        if value == previous + 1:
            run_length += 1
            if run_length >= needed_length:
                return True
        elif value != previous:
            run_length = 1
        previous = value
    return False