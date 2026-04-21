from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
import random

from src.models.action import ActionType, PresentationStyle, TurnAction
from src.models.card import Card, Claim, ClaimRank, SpecialCardType
from src.models.evaluator import evaluate_claim_rank
from src.models.player import PlayerState, ReputationBand, TurnRecord


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


class BaseAIStrategy(ABC):
    def init(self, owner_name: str, rng: random.Random | None = None) -> None:
        self.owner_name = owner_name
        self.rng = rng or random.Random()

    @abstractmethod
    def choose_action(self, context: AIContext) -> TurnAction:
        pass

    def on_round_started(self) -> None:
        return None

    def observe_turn(self, turn_record: TurnRecord) -> None:
        return None

    def _estimate_honest_rank(self, hand: list[Card]) -> ClaimRank:
        return evaluate_claim_rank(hand)

    def _lowest_claim(self, context: AIContext) -> ClaimRank:
        return context.available_claim_ranks[0]

    def _claim_from_jump(self, context: AIContext, jump: int) -> ClaimRank:
        return context.available_claim_ranks[
            min(max(jump - 1, 0), len(context.available_claim_ranks) - 1)
        ]

    def _truthful_options(self, context: AIContext) -> list[ClaimRank]:
        honest_rank = self._estimate_honest_rank(context.player.hand)
        return [rank for rank in context.available_claim_ranks if rank <= honest_rank]

    def _build_claim(
        self,
        context: AIContext,
        target_rank: ClaimRank,
        card_count: int,
        style: PresentationStyle,
        note: str,
        bluff: bool,
        ghost_mode: bool = False,
    ) -> TurnAction:
        card_indices = pick_cards_for_claim(
            context.player.hand,
            target_rank=target_rank,
            rng=self.rng,
            desired_count=min(card_count, len(context.player.hand)),
            bluff=bluff,
        )
        return TurnAction.claim(
            card_indices=card_indices,
            claim_rank=target_rank,
            presentation_style=style,
            ghost_mode=ghost_mode,
            note=note,
        )

    def _attach_special_if_helpful(
        self,
        context: AIContext,
        action: TurnAction,
        bluff: bool = False,
    ) -> TurnAction:
        truthful_options = self._truthful_options(context)

        for hand_index, card in context.player.special_cards():
            special = card.special
            if special is None:
                continue

            if (
                special == SpecialCardType.MEMORY_WIPE
                and len(context.public_memory_log) >= 3
                and self.rng.random() < 0.35
            ):
                return action.with_special(hand_index)
            if action.action_type == ActionType.CLAIM:
                if (
                    special == SpecialCardType.WILDCARD_HAND
                    and context.player.claimable_hand_size == 0
                ):
                    return action.with_special(hand_index)
                if (
                    special == SpecialCardType.WILDCARD_HAND
                    and not truthful_options
                    and self.rng.random() < 0.4
                ):
                    return action.with_special(hand_index)
                if (
                    special == SpecialCardType.BLINDFOLD
                    and bluff
                    and context.player.claimable_hand_size > 0
                    and self.rng.random() < 0.28
                ):
                    blindfold_count = min(3, context.player.claimable_hand_size)
                    return action.with_special(
                        hand_index,
                        blindfold_card_count=max(1, blindfold_count),
                    )
                if (
                    special == SpecialCardType.DOUBLE_DOWN
                    and not bluff
                    and action.claim_rank in truthful_options
                    and self.rng.random() < 0.38
                ):
                    return action.with_special(hand_index)
                if special == SpecialCardType.SHIELD and self.rng.random() < 0.18:
                    return action.with_special(hand_index)

            if action.action_type == ActionType.CHALLENGE:
                if (
                    special == SpecialCardType.MIRROR_DAMAGE
                    and self.rng.random() < 0.42
                ):
                    return action.with_special(hand_index)
                if special == SpecialCardType.SHIELD and self.rng.random() < 0.24:
                    return action.with_special(hand_index)

        return action

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _challenge_threshold(
        self,
        base: float,
        claimant: PlayerState | None,
    ) -> float:
        if claimant is None:
            return base
        offsets = {
            ReputationBand.TRUSTED: 1.4,
            ReputationBand.NEUTRAL: 0.0,
            ReputationBand.SUSPECT: -0.8,
            ReputationBand.NOTORIOUS: -1.7,
        }
        return base + offsets[claimant.reputation_band]

    def _challenge_probability(
        self,
        base: float,
        claimant: PlayerState | None,
    ) -> float:
        if claimant is None:
            return base
        offsets = {
            ReputationBand.TRUSTED: -0.1,
            ReputationBand.NEUTRAL: 0.0,
            ReputationBand.SUSPECT: 0.08,
            ReputationBand.NOTORIOUS: 0.18,
        }
        return self._clamp(base + offsets[claimant.reputation_band], 0.05, 0.95)

    def _suspicion_score(self, context: AIContext) -> float:
        if context.current_claim is None or context.current_claimant is None:
            return 0.0

        reputation_pressure = {
            ReputationBand.TRUSTED: -1.2,
            ReputationBand.NEUTRAL: 0.0,
            ReputationBand.SUSPECT: 1.1,
            ReputationBand.NOTORIOUS: 2.4,
        }[context.current_claimant.reputation_band]
        stack_pressure = max(
            0.0,
            context.current_claim.rank.value * 1.25
            - context.claim_stack_size * 0.45,
        )
        history_pressure = min(3.0, len(context.public_memory_log) * 0.1)
        return stack_pressure + history_pressure + reputation_pressure

    def _human_window(
        self,
        context: AIContext,
        limit: int = 6,
    ) -> list[TurnRecord]:
        window = [
            record
            for record in context.turn_history
            if record.actor_profile_key is None and record.actor_name != self.owner_name
        ]
        return window[-limit:]
    def _mode_value(
        self,
        values: list[int],
        fallback: int,
    ) -> int:
        if not values:
            return fallback
        counts = Counter(values)
        highest = max(counts.values())
        common_values = [value for value, count in counts.items() if count == highest]
        return min(common_values)

    def _recent_challenge_probability(
        self,
        context: AIContext,
        target: PlayerState | None,
    ) -> float:
        relevant_records = [
            record
            for record in context.turn_history[-10:]
            if record.actor_name != self.owner_name
        ]
        if relevant_records:
            challenge_rate = sum(
                record.action == ActionType.CHALLENGE.value
                for record in relevant_records
            ) / len(relevant_records)
        else:
            challenge_rate = 0.35

        if target is None:
            return self._clamp(challenge_rate, 0.1, 0.9)

        band_offsets = {
            ReputationBand.TRUSTED: -0.12,
            ReputationBand.NEUTRAL: 0.0,
            ReputationBand.SUSPECT: 0.1,
            ReputationBand.NOTORIOUS: 0.2,
        }
        return self._clamp(
            challenge_rate + band_offsets[target.reputation_band],
            0.08,
            0.95,
        )


class DanteStrategy(BaseAIStrategy):
    def choose_action(self, context: AIContext) -> TurnAction:
        if (
            context.current_claim
            and self._suspicion_score(context)
            > self._challenge_threshold(7.2, context.current_claimant)
            and self.rng.random()
            < self._challenge_probability(0.32, context.current_claimant)
        ):
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=PresentationStyle.AGGRESSIVE,
                    note="Calls the table hard when the lie feels oversized.",
                ),
            )

        truthful_options = self._truthful_options(context)
        bluff = self.rng.random() < 0.68 or not truthful_options
        jump = self.rng.choice((2, 2, 3, 4)) if bluff else self.rng.choice((1, 1, 2))
        target_rank = self._claim_from_jump(context, jump)
        claim_sizes = (2, 3, 4) if bluff else (1, 2, 3)
        card_count = min(len(context.player.hand), self.rng.choice(claim_sizes))
        return self._attach_special_if_helpful(
            context,
            self._build_claim(
                context=context,
                target_rank=target_rank,
                card_count=card_count,
                style=PresentationStyle.AGGRESSIVE,
                note="Leans into pressure and overclaims by instinct.",
                bluff=bluff,
            ),
            bluff=bluff,
        )


class AshStrategy(BaseAIStrategy):
    def choose_action(self, context: AIContext) -> TurnAction:
        human_window = self._human_window(context, limit=7)
        if human_window:
            challenge_tendency = sum(
                record.action == ActionType.CHALLENGE.value
                for record in human_window
            ) / len(human_window)
        else:
            challenge_tendency = 0.0

        if (
            context.current_claim
            and challenge_tendency >= 0.45
            and self.rng.random()
            < self._challenge_probability(0.4, context.current_claimant)
        ):
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=PresentationStyle.MIRRORED,
                    note="Reflects the human's appetite for calling lies.",
                ),
            )
        claim_window = [
            record
            for record in human_window
            if record.action == ActionType.CLAIM.value
        ]
        truthful_options = self._truthful_options(context)
        mirrored_jump = self._mode_value(
            [
                record.claim_jump
                for record in claim_window
                if record.claim_jump is not None
            ],
            1,
        )
        mirrored_count = self._mode_value(
            [
                record.card_count
                for record in claim_window
                if record.card_count is not None
            ],
            2,
        )
        bluff_signals = [
            record.was_bluff
            for record in claim_window
            if record.was_bluff is not None
        ]
        bluff_rate = (
            sum(signal is True for signal in bluff_signals) / len(bluff_signals)
            if bluff_signals
            else 0.5
        )
        bluff = bluff_rate >= 0.5 or not truthful_options
        target_rank = self._claim_from_jump(context, mirrored_jump if bluff else 1)
        card_count = min(len(context.player.hand), max(1, min(4, mirrored_count)))
        return self._attach_special_if_helpful(
            context,
            self._build_claim(
                context=context,
                target_rank=target_rank,
                card_count=card_count,
                style=PresentationStyle.MIRRORED,
                note="Mirrors the player's dominant recent pattern.",
                bluff=bluff,
            ),
            bluff=bluff,
        )


class MrFoldStrategy(BaseAIStrategy):
    def _challenge_ev(self, context: AIContext) -> float:
        if context.current_claimant is None:
            return -1.0
        estimated_truth = self._clamp(
            0.75 - (self._suspicion_score(context) / 10),
            0.15,
            0.9,
        )
        reward = 5.0
        bullet_damage = 18.0 if context.player.shield_charges == 0 else 8.0
        return (1 - estimated_truth) * reward - estimated_truth * bullet_damage

    def _claim_evs(
        self,
        context: AIContext,
    ) -> tuple[float, float]:
        estimated_challenge = self._recent_challenge_probability(context, context.player)
        reputation_gain = 10.0
        bullet_damage = 18.0 if context.player.shield_charges == 0 else 8.0
        opportunity_cost = 4.0
        ev_bluff = (1 - estimated_challenge) * reputation_gain - estimated_challenge * bullet_damage
        ev_truth = estimated_challenge * reputation_gain - (1 - estimated_challenge) * opportunity_cost
        return ev_bluff, ev_truth

    def choose_action(self, context: AIContext) -> TurnAction:
        truthful_options = self._truthful_options(context)

        if (
            context.current_claim
            and self._challenge_ev(context) > 0
            and self.rng.random()
            < self._challenge_probability(0.58, context.current_claimant)
        ):
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=PresentationStyle.COMPOSED,
                    note="Challenges only when the table math tilts his way.",
                ),
            )
        ev_bluff, ev_truth = self._claim_evs(context)
        bluff = (ev_bluff > ev_truth and self.rng.random() < 0.8) or not truthful_options
        target_rank = (
            max(truthful_options)
            if truthful_options and not bluff
            else self._claim_from_jump(context, 2 if ev_bluff <= 6 else 3)
        )
        card_count = 2 if bluff else min(len(context.player.hand), 2 if len(context.player.hand) >= 2 else 1)
        return self._attach_special_if_helpful(
            context,
            self._build_claim(
                context=context,
                target_rank=target_rank,
                card_count=card_count,
                style=PresentationStyle.COMPOSED,
                note="Calculates risk through expected value before moving.",
                bluff=bluff,
            ),
            bluff=bluff,
        )


class VesperStrategy(BaseAIStrategy):
    def init(self, owner_name: str, rng: random.Random | None = None) -> None:
        super().init(owner_name=owner_name, rng=rng)
        self.pressure = 0

    def choose_action(self, context: AIContext) -> TurnAction:
        ghost_mode = self.pressure >= 3
        suspicion = self._suspicion_score(context)

        if ghost_mode and context.current_claim and suspicion > 4.2:
            self.pressure = 0
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=PresentationStyle.GHOST,
                    ghost_mode=True,
                    note="Ghost Mode locks in and punishes the claim.",
                ),
            )

        truthful_options = self._truthful_options(context)
        if ghost_mode:
            self.pressure = 0
            return self._attach_special_if_helpful(
                context,
                self._build_claim(
                    context=context,
                    target_rank=context.available_claim_ranks[-1],
                    card_count=min(4, len(context.player.hand)),
                    style=PresentationStyle.GHOST,
                    note="Ghost Mode emerges and reaches for the ceiling.",
                    bluff=True,
                    ghost_mode=True,
                ),
                bluff=True,
            )

        if (
            context.current_claim
            and suspicion > self._challenge_threshold(7.6, context.current_claimant)
            and self.rng.random()
            < self._challenge_probability(0.18, context.current_claimant)
        ):
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=PresentationStyle.FLAT,
                    note="A cold, rare interruption.",
                ),
            )

        target_rank = truthful_options[0] if truthful_options else self._lowest_claim(context)
        bluff = not truthful_options
        return self._attach_special_if_helpful(
            context,
            self._build_claim(
                context=context,
                target_rank=target_rank,
                card_count=min(2, len(context.player.hand)),
                style=PresentationStyle.FLAT,
                note="Waits, listens, and keeps the mask still.",
                bluff=bluff,
            ),
            bluff=bluff,
        )

    def observe_turn(self, turn_record: TurnRecord) -> None:
        if turn_record.actor_name != self.owner_name and turn_record.action == ActionType.CLAIM.value:
            self.pressure = min(4, self.pressure + 1)
    class FoxStrategy(BaseAIStrategy):
     def choose_action(self, context: AIContext) -> TurnAction:
        current_band = context.player.reputation_band
        if current_band == ReputationBand.TRUSTED:
            style = PresentationStyle.THEATRICAL
        elif current_band == ReputationBand.NOTORIOUS:
            style = PresentationStyle.THEATRICAL
        elif current_band == ReputationBand.SUSPECT:
            style = PresentationStyle.FLAT
        else:
            style = (
                PresentationStyle.THEATRICAL
                if self.rng.random() < 0.55
                else PresentationStyle.FLAT
            )

        if (
            context.current_claim
            and self._suspicion_score(context)
            > self._challenge_threshold(5.8, context.current_claimant)
            and self.rng.random()
            < self._challenge_probability(0.38, context.current_claimant)
        ):
            return self._attach_special_if_helpful(
                context,
                TurnAction.challenge(
                    presentation_style=style,
                    note="Measures the room before deciding whether the call will play well.",
                ),
            )

        truthful_options = self._truthful_options(context)
        if current_band == ReputationBand.TRUSTED:
            bluff = not truthful_options
            style = PresentationStyle.THEATRICAL
        elif current_band == ReputationBand.NOTORIOUS:
            bluff = True
            style = PresentationStyle.THEATRICAL
        elif current_band == ReputationBand.SUSPECT:
            bluff = not truthful_options
            style = PresentationStyle.FLAT if truthful_options else PresentationStyle.THEATRICAL
        else:
            bluff = style == PresentationStyle.THEATRICAL and context.player.reputation < 60
            if not truthful_options and not bluff:
                bluff = True

        target_rank = (
            max(truthful_options)
            if truthful_options and not bluff
            else self._claim_from_jump(context, 2 if style == PresentationStyle.FLAT else 3)
        )
        card_count = min(
            len(context.player.hand),
            3 if style == PresentationStyle.THEATRICAL else 2,
        )
        return self._attach_special_if_helpful(
            context,
            self._build_claim(
                context=context,
                target_rank=target_rank,
                card_count=card_count,
                style=style,
                note="Manipulates how the room reads his reputation band.",
                bluff=bluff,
            ),
            bluff=bluff,
        )


class StrategyFactory:
    _mapping = {
        "dante": DanteStrategy,
        "ash": AshStrategy,
        "mr_fold": MrFoldStrategy,
        "vesper": VesperStrategy,
        "fox": FoxStrategy,
    }

    @classmethod
    def create(
        cls,
        profile_key: str,
        owner_name: str,
        rng: random.Random | None = None,
    ) -> BaseAIStrategy:
        strategy_cls = cls._mapping.get(profile_key)
        if strategy_cls is None:
            raise ValueError(f"Unknown AI profile key: {profile_key}")
        return strategy_cls(owner_name=owner_name, rng=rng)


def pick_cards_for_claim(
    hand: list[Card],
    target_rank: ClaimRank,
    rng: random.Random,
    desired_count: int,
    bluff: bool,
) -> list[int]:
    regular_indices = [index for index, card in enumerate(hand) if not card.is_special]
    if not regular_indices:
        return []

    desired_count = max(1, min(4, desired_count, len(regular_indices)))
    if bluff:
        return sorted(rng.sample(regular_indices, desired_count))

    grouped_by_rank: dict[int, list[int]] = defaultdict(list)
    grouped_by_suit: dict[str, list[int]] = defaultdict(list)
    for index, card in enumerate(hand):
        if card.is_special:
            continue
        if card.rank is not None:
            grouped_by_rank[int(card.rank)].append(index)
        if card.suit is not None:
            grouped_by_suit[card.suit.value].append(index)
    if target_rank == ClaimRank.PAIR:
        pair = next(
            (indices[:2] for indices in grouped_by_rank.values() if len(indices) >= 2),
            None,
        )
        if pair:
            return sorted(pair)
    elif target_rank == ClaimRank.TWO_PAIR:
        pairs = [indices[:2] for indices in grouped_by_rank.values() if len(indices) >= 2]
        if len(pairs) >= 2:
            return sorted((pairs[0] + pairs[1])[:desired_count])
    elif target_rank == ClaimRank.THREE_OF_A_KIND:
        trip = next(
            (indices[:3] for indices in grouped_by_rank.values() if len(indices) >= 3),
            None,
        )
        if trip:
            return sorted(trip[:desired_count])
    elif target_rank == ClaimRank.FLUSH:
        suited = next(
            (indices for indices in grouped_by_suit.values() if len(indices) >= 3),
            None,
        )
        if suited:
            return sorted(suited[:desired_count])
    elif target_rank in (ClaimRank.STRAIGHT, ClaimRank.STRAIGHT_FLUSH, ClaimRank.ROYAL_FLUSH):
        sequence = _pick_sequence_indices(hand, desired_count=desired_count)
        if sequence:
            return sorted(sequence)
    elif target_rank == ClaimRank.FOUR_OF_A_KIND:
        quad = next(
            (indices[:4] for indices in grouped_by_rank.values() if len(indices) >= 4),
            None,
        )
        if quad:
            return sorted(quad[:desired_count])

    ranked_indices = sorted(
        regular_indices,
        key=lambda index: (int(hand[index].rank or 0), hand[index].short_label),
        reverse=True,
    )
    return sorted(ranked_indices[:desired_count])


def _pick_sequence_indices(hand: list[Card], desired_count: int) -> list[int]:
    candidates = [
        (index, int(card.rank or 0))
        for index, card in enumerate(hand)
        if card.rank is not None and not card.is_special
    ]
    candidates.sort(key=lambda item: item[1])

    best_run: list[int] = []
    current_run: list[int] = []
    previous_rank: int | None = None
    for index, rank_value in candidates:
        if previous_rank is None or rank_value == previous_rank + 1:
            current_run.append(index)
        elif rank_value != previous_rank:
            current_run = [index]
        previous_rank = rank_value
        if len(current_run) > len(best_run):
            best_run = current_run.copy()

    return best_run[:desired_count]