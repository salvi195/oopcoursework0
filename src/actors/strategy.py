from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import random

from src.models.action import ActionType, PresentationStyle, TurnAction
from src.models.card import Card, Claim, ClaimRank, SpecialCardType
from src.models.evaluator import evaluate_claim_rank
from src.models.player import PlayerState, TurnRecord


@dataclass(frozen=True, slots=True)
class AIContext:
    player: PlayerState
    opponents: tuple[PlayerState, ...]
    current_claim: Claim | None
    current_claimant: PlayerState | None
    claim_stack_size: int
    round_number: int
    turn_history: tuple[TurnRecord, ...]
    public_memory_log: tuple[str, ...]
    available_claim_ranks: tuple[ClaimRank, ...]
    deck_has_regular_card: bool


class BaseAIStrategy:
    bluff_chance = 0.35
    challenge_chance = 0.25
    max_claim_cards = 2
    style = PresentationStyle.NEUTRAL
    note = "Makes a balanced table decision."

    def __init__(self, owner_name: str, rng: random.Random | None = None) -> None:
        self.owner_name = owner_name
        self.rng = rng or random.Random()

    def choose_action(self, context: AIContext) -> TurnAction:
        if context.current_claim is not None and not context.available_claim_ranks:
            return self._with_special(context, self._challenge_action())

        if context.player.claimable_hand_size == 0:
            wildcard_index = self._wildcard_index(context)
            if wildcard_index is not None and context.deck_has_regular_card:
                ranks = context.available_claim_ranks or tuple(ClaimRank)
                return TurnAction.claim(
                    card_indices=[],
                    claim_rank=ranks[min(2, len(ranks) - 1)],
                    presentation_style=self.style,
                    special_card_index=wildcard_index,
                    note="Uses Wildcard Hand to find claim cards.",
                )
            if context.current_claim is not None:
                return self._with_special(context, self._challenge_action())

        if self._should_challenge(context):
            return self._with_special(context, self._challenge_action())

        ranks = context.available_claim_ranks or tuple(ClaimRank)
        truthful = self._truthful_options(context, ranks)
        bluff = not truthful or self.rng.random() < self.bluff_chance
        target_rank = self._target_rank(ranks, truthful, bluff)
        card_count = min(self.max_claim_cards, max(1, context.player.claimable_hand_size))

        action = TurnAction.claim(
            card_indices=pick_cards_for_claim(
                context.player.hand,
                target_rank=target_rank,
                rng=self.rng,
                desired_count=card_count,
                bluff=bluff,
            ),
            claim_rank=target_rank,
            presentation_style=self.style,
            note=self.note,
        )
        return self._with_special(context, action, bluff=bluff)

    def _challenge_action(self) -> TurnAction:
        return TurnAction.challenge(
            presentation_style=self.style,
            note=self.note,
        )

    def on_round_started(self) -> None:
        return None

    def observe_turn(self, turn_record: TurnRecord) -> None:
        return None

    def _should_challenge(self, context: AIContext) -> bool:
        if context.current_claim is None:
            return False
        pressure = max(0, int(context.current_claim.rank) - context.claim_stack_size)
        chance = min(0.85, self.challenge_chance + pressure * 0.04)
        return self.rng.random() < chance

    def _truthful_options(
        self,
        context: AIContext,
        ranks: tuple[ClaimRank, ...],
    ) -> list[ClaimRank]:
        honest_rank = evaluate_claim_rank(context.player.hand)
        return [rank for rank in ranks if rank <= honest_rank]

    def _target_rank(
        self,
        ranks: tuple[ClaimRank, ...],
        truthful: list[ClaimRank],
        bluff: bool,
    ) -> ClaimRank:
        if truthful and not bluff:
            return max(truthful)
        return ranks[min(2, len(ranks) - 1)]

    def _with_special(
        self,
        context: AIContext,
        action: TurnAction,
        bluff: bool = False,
    ) -> TurnAction:
        for hand_index, card in context.player.special_cards():
            special = card.special
            if special is None:
                continue
            if action.action_type == ActionType.CHALLENGE:
                if special in (SpecialCardType.MIRROR_DAMAGE, SpecialCardType.SHIELD):
                    return action.with_special(hand_index)
            elif special == SpecialCardType.WILDCARD_HAND and (
                not action.card_indices or context.player.claimable_hand_size == 0
            ):
                return action.with_special(hand_index)
            elif special == SpecialCardType.BLINDFOLD and bluff and context.player.claimable_hand_size > 0:
                return action.with_special(hand_index)
            elif special in (SpecialCardType.DOUBLE_DOWN, SpecialCardType.SHIELD) and action.card_indices:
                return action.with_special(hand_index)
            elif special == SpecialCardType.MEMORY_WIPE and context.public_memory_log and action.card_indices:
                return action.with_special(hand_index)
        return action

    def _wildcard_index(self, context: AIContext) -> int | None:
        for hand_index, card in context.player.special_cards():
            if card.special == SpecialCardType.WILDCARD_HAND:
                return hand_index
        return None


class PigStrategy(BaseAIStrategy):
    bluff_chance = 0.70
    challenge_chance = 0.35
    max_claim_cards = 3
    style = PresentationStyle.AGGRESSIVE
    note = "Pushes the table with bold claims."


class WolfStrategy(BaseAIStrategy):
    bluff_chance = 0.40
    challenge_chance = 0.25
    style = PresentationStyle.MIRRORED
    note = "Keeps close to the table's pace."


class BullStrategy(BaseAIStrategy):
    bluff_chance = 0.15
    challenge_chance = 0.45
    style = PresentationStyle.COMPOSED
    note = "Prefers safer claims and careful challenges."


class BunnyStrategy(BaseAIStrategy):
    bluff_chance = 0.20
    challenge_chance = 0.18
    style = PresentationStyle.FLAT
    note = "Waits quietly before committing."

    def __init__(self, owner_name: str, rng: random.Random | None = None) -> None:
        super().__init__(owner_name, rng)
        self.pressure = 0

    def choose_action(self, context: AIContext) -> TurnAction:
        if self.pressure >= 3:
            self.pressure = 0
            if context.current_claim is not None:
                return TurnAction.challenge(
                    presentation_style=PresentationStyle.GHOST,
                    ghost_mode=True,
                    note="Ghost Mode calls the claim.",
                )
            if context.player.claimable_hand_size == 0:
                return super().choose_action(context)
            return TurnAction.claim(
                card_indices=pick_cards_for_claim(
                    context.player.hand,
                    target_rank=ClaimRank.ROYAL_FLUSH,
                    rng=self.rng,
                    desired_count=4,
                    bluff=True,
                ),
                claim_rank=ClaimRank.ROYAL_FLUSH,
                presentation_style=PresentationStyle.GHOST,
                ghost_mode=True,
                note="Ghost Mode reaches for the highest claim.",
            )
        return super().choose_action(context)

    def observe_turn(self, turn_record: TurnRecord) -> None:
        if turn_record.actor_name != self.owner_name:
            self.pressure = min(3, self.pressure + 1)


class StrategyFactory:
    _strategies = {
        "pig": PigStrategy,
        "wolf": WolfStrategy,
        "bull": BullStrategy,
        "bunny": BunnyStrategy,
    }

    @classmethod
    def create(
        cls,
        profile_key: str,
        owner_name: str,
        rng: random.Random | None = None,
    ) -> BaseAIStrategy:
        strategy_class = cls._strategies.get(profile_key)
        if strategy_class is None:
            raise ValueError(f"Unknown AI profile key: {profile_key}")
        return strategy_class(owner_name=owner_name, rng=rng)


def pick_cards_for_claim(
    hand: list[Card],
    target_rank: ClaimRank,
    rng: random.Random,
    desired_count: int,
    bluff: bool,
) -> list[int]:
    regular_indices = [
        index for index, card in enumerate(hand) if not card.is_special
    ]
    if not regular_indices:
        return []

    count = max(1, min(desired_count, 4, len(regular_indices)))
    if bluff:
        return sorted(rng.sample(regular_indices, count))

    candidates = _truthful_card_indices(hand, target_rank)
    if candidates:
        return sorted(candidates[:count])

    best_cards = sorted(
        regular_indices,
        key=lambda index: (int(hand[index].rank or 0), hand[index].short_label),
        reverse=True,
    )
    return sorted(best_cards[:count])


def _truthful_card_indices(hand: list[Card], target_rank: ClaimRank) -> list[int]:
    by_rank: dict[int, list[int]] = defaultdict(list)
    by_suit: dict[str, list[int]] = defaultdict(list)

    for index, card in enumerate(hand):
        if card.is_special:
            continue
        if card.rank is not None:
            by_rank[int(card.rank)].append(index)
        if card.suit is not None:
            by_suit[card.suit.value].append(index)

    if target_rank == ClaimRank.PAIR:
        return _matching_group(by_rank, 2)
    if target_rank == ClaimRank.TWO_PAIR:
        pairs = [indices[:2] for indices in by_rank.values() if len(indices) >= 2]
        return pairs[0] + pairs[1] if len(pairs) >= 2 else []
    if target_rank == ClaimRank.THREE_OF_A_KIND:
        return _matching_group(by_rank, 3)
    if target_rank == ClaimRank.FOUR_OF_A_KIND:
        return _matching_group(by_rank, 4)
    if target_rank == ClaimRank.FLUSH:
        return _matching_group(by_suit, 3)
    if target_rank in {
        ClaimRank.STRAIGHT,
        ClaimRank.STRAIGHT_FLUSH,
        ClaimRank.ROYAL_FLUSH,
    }:
        return _sequence_indices(hand)
    return []


def _matching_group(groups: dict[int | str, list[int]], size: int) -> list[int]:
    return next(
        (indices[:size] for indices in groups.values() if len(indices) >= size),
        [],
    )


def _sequence_indices(hand: list[Card]) -> list[int]:
    ranked = sorted(
        (int(card.rank), index)
        for index, card in enumerate(hand)
        if card.rank is not None and not card.is_special
    )
    run: list[int] = []
    previous_rank: int | None = None

    for rank, index in ranked:
        if previous_rank is None or rank == previous_rank + 1:
            run.append(index)
        elif rank != previous_rank:
            run = [index]
        previous_rank = rank
        if len(run) >= 5:
            return run
    return run if len(run) >= 3 else []
