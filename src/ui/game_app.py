from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import pygame

from constants import SCREEN_HEIGHT, SCREEN_WIDTH, TARGET_FPS, WINDOW_TITLE
from src.actors.ai_profiles import OPPONENT_PROFILES
from src.engine import GameEngine, GameState
from src.models.action import ActionType, TurnAction
from src.models.card import Card, ClaimRank, Rank, SpecialCardType, Suit
from src.models.player import PlayerState, ReputationBand, TurnRecord
from src.persistence import MatchSnapshotStore
from src.ui.assets import AssetLibrary
from src.ui.theme import build_theme


@dataclass(slots=True)
class UIButton:
    key: str
    label: str
    rect: pygame.Rect
    value: object | None = None
    enabled: bool = True


@dataclass(slots=True)
class PresentationEvent:
    kind: str
    title: str
    subtitle: str = ""
    detail: str = ""
    actor_name: str | None = None
    target_name: str | None = None
    duration_ms: int = 2600
    allow_input: bool = False
    emphasis: str = "neutral"
    chance_percent: int | None = None
    chamber_index: int | None = None


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


class BluffingGameApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.engine = GameEngine()
        self.snapshot_store = MatchSnapshotStore(Path("saves/latest_match.json"))
        self.saved_summary = self.snapshot_store.load_previous_summary()
        self.state: GameState | None = None
        self.mode = "menu"
        self.running = True
        self.buttons: list[UIButton] = []
        self.hand_targets: list[tuple[pygame.Rect, int, pygame.mask.Mask]] = []
        self.selected_cards: set[int] = set()
        self.selected_special_index: int | None = None
        self.selected_claim_rank: ClaimRank | None = None
        self.keyboard_card_index = 0
        self.blindfold_count = 2
        self.status_message = ""
        self.last_result = ""
        self.menu_loading_action: str | None = None
        self.menu_loading_started_at = 0
        self.menu_loading_duration_ms = 850
        self.ai_due_at = 0
        self.turn_marker: tuple[int, int, int] | None = None
        self.presentation_queue: list[PresentationEvent] = []
        self.presentation_event: PresentationEvent | None = None
        self.presentation_started_at = 0
        self.presentation_until = 0
        self.profile_lookup = {profile.key: profile for profile in OPPONENT_PROFILES}
        asset_dir = Path("assets")
        self.theme = build_theme(asset_dir)
        self.colors = self.theme.colors
        self.fonts = self.theme.fonts
        self.profile_colors = self.theme.profile_colors
        self.assets = AssetLibrary(
            asset_dir,
            self.colors,
            self.profile_colors,
            self.profile_lookup,
        )

    def run(self) -> None:
        while self.running:
            now = pygame.time.get_ticks()
            self._update_presentation(now)
            self._sync_turn_state()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if self.mode == "menu":
                    self._handle_menu_event(event)
                else:
                    self._handle_table_event(event)
            if self.mode == "table":
                self._update_table(now)
            elif self.mode == "menu":
                self._update_menu_loading(now)
            self._draw(now)
            pygame.display.flip()
            self.clock.tick(TARGET_FPS)
        pygame.quit()

    def _start_new_match(self) -> None:
        self.state = self.engine.bootstrap_match(player_name="Player")
        self.mode = "table"
        self.last_result = self.engine.boot_summary()
        self.status_message = ""
        self.ai_due_at = 0
        self.turn_marker = None
        self._clear_presentation()
        self._queue_presentation(
            PresentationEvent(
                kind="round",
                title="Round 1 Begins",
                subtitle="Read the table before you move.",
                detail="Your turn opens the night.",
                duration_ms=2400,
            )
        )
        self._reset_human_selection()
        self._save_snapshot()

    def _resume_match(self) -> None:
        if self.saved_summary is None:
            return
        self.state = self.engine.resume_match(self.saved_summary)
        self.mode = "table"
        self.last_result = self.engine.boot_summary()
        self.status_message = "Resumed from the latest checkpoint."
        self.ai_due_at = 0
        self.turn_marker = None
        self._clear_presentation()
        self._queue_presentation(
            PresentationEvent(
                kind="round",
                title="Match Resumed",
                subtitle=f"Round {self.state.round_number}",
                detail="The table remembers where it left off.",
                duration_ms=2200,
            )
        )
        self._reset_human_selection()
        self._save_snapshot()

    def _save_snapshot(self) -> None:
        if self.state is None:
            return
        self.snapshot_store.save_state(self.state)
        self.saved_summary = self.snapshot_store.load_previous_summary()

    def _reset_human_selection(self) -> None:
        self.selected_cards.clear()
        self.selected_special_index = None
        self.selected_claim_rank = None
        self.keyboard_card_index = 0
        self.blindfold_count = 2

    def _clear_presentation(self) -> None:
        self.presentation_queue.clear()
        self.presentation_event = None
        self.presentation_started_at = 0
        self.presentation_until = 0

    def _queue_presentation(self, event: PresentationEvent) -> None:
        self.presentation_queue.append(event)
        if self.presentation_event is None:
            self._start_next_presentation(pygame.time.get_ticks())

    def _start_next_presentation(self, now: int) -> None:
        if not self.presentation_queue:
            self.presentation_event = None
            self.presentation_started_at = 0
            self.presentation_until = 0
            return
        self.presentation_event = self.presentation_queue.pop(0)
        self.presentation_started_at = now
        self.presentation_until = now + self.presentation_event.duration_ms

    def _update_presentation(self, now: int) -> None:
        if self.presentation_event is not None and now >= self.presentation_until:
            self._start_next_presentation(now)
        elif self.presentation_event is None and self.presentation_queue:
            self._start_next_presentation(now)

    def _presentation_blocks_input(self) -> bool:
        return self.presentation_event is not None and not self.presentation_event.allow_input

    def _presentation_active(self) -> bool:
        return self.presentation_event is not None or bool(self.presentation_queue)

    def _sync_turn_state(self) -> None:
        if self.mode != "table" or self.state is None or self.engine.is_match_over():
            return
        current_claim_value = (
            self.state.current_claim.rank.value if self.state.current_claim else 0
        )
        marker = (
            self.state.round_number,
            self.state.current_turn_index,
            current_claim_value,
        )
        if marker == self.turn_marker:
            return
        self.turn_marker = marker
        self.status_message = ""
        current_player = self.engine.current_player()
        if current_player.is_human:
            self._reset_human_selection()
            legal_claims = self.engine.legal_claim_ranks()
            if legal_claims:
                self.selected_claim_rank = legal_claims[0]
            self.blindfold_count = max(1, min(2, current_player.claimable_hand_size or 1))
            self.ai_due_at = 0
        else:
            self.ai_due_at = pygame.time.get_ticks() + 900

    def _handle_menu_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if self.menu_loading_action is not None:
                return
            if event.key in {pygame.K_RETURN, pygame.K_SPACE}:
                self._begin_menu_loading("new")
            elif event.key == pygame.K_ESCAPE:
                self.running = False
            return

        if self.menu_loading_action is not None:
            return

        if event.type == pygame.FINGERDOWN:
            pos = (int(event.x * SCREEN_WIDTH), int(event.y * SCREEN_HEIGHT))
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
        else:
            return

        for button in self.buttons:
            if button.rect.collidepoint(pos) and button.enabled:
                self._activate_menu_button(button)
                return

    def _activate_menu_button(self, button: UIButton) -> None:
        if button.key == "menu_new":
            self._begin_menu_loading("new")
        elif button.key == "menu_resume":
            self._begin_menu_loading("resume")
        elif button.key == "menu_quit":
            self.running = False

    def _begin_menu_loading(self, action: str) -> None:
        if action == "resume" and self.saved_summary is None:
            return
        self.menu_loading_action = action
        self.menu_loading_started_at = pygame.time.get_ticks()

    def _update_menu_loading(self, now: int) -> None:
        if self.menu_loading_action is None:
            return
        if now - self.menu_loading_started_at < self.menu_loading_duration_ms:
            return
        action = self.menu_loading_action
        self.menu_loading_action = None
        if action == "new":
            self._start_new_match()
        elif action == "resume":
            self._resume_match()

    def _handle_table_event(self, event: pygame.event.Event) -> None:
        if self.state is None:
            return
        if self._presentation_blocks_input():
            return
        if self._human_death_screen_active():
            if event.type == pygame.KEYDOWN and event.key in {pygame.K_RETURN, pygame.K_SPACE}:
                self._start_new_match()
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for button in self.buttons:
                    if button.rect.collidepoint(event.pos) and button.enabled:
                        if button.key == "death_retry":
                            self._start_new_match()
                        elif button.key == "death_menu":
                            self.mode = "menu"
                            self._clear_presentation()
                        return
            return
        if event.type == pygame.KEYDOWN:
            self._handle_table_keydown(event)
            return
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.engine.is_match_over():
            for button in self.buttons:
                if button.rect.collidepoint(event.pos) and button.enabled:
                    if button.key == "end_new_match":
                        self._start_new_match()
                    elif button.key == "end_menu":
                        self.mode = "menu"
                    return
            return
        if self._human_can_interrupt_with_challenge():
            for button in self.buttons:
                if (
                    button.key == "challenge"
                    and button.rect.collidepoint(event.pos)
                    and button.enabled
                ):
                    self._apply_human_challenge()
                    return
        player = self.engine.current_player()
        if not player.is_human:
            return
        for button in self.buttons:
            if button.rect.collidepoint(event.pos) and button.enabled:
                self._handle_button_press(button)
                return
        card_index = self._hand_index_at(event.pos)
        if card_index is not None:
            self._handle_card_press(card_index)
            return

    def _handle_table_keydown(self, event: pygame.event.Event) -> None:
        if self.state is None or self.engine.is_match_over():
            return
        if self._human_can_interrupt_with_challenge() and event.key == pygame.K_x:
            self._apply_human_challenge()
            return
        player = self.engine.current_player()
        if not player.is_human:
            return
        if event.key == pygame.K_q:
            self._handle_button_press(UIButton("claim_prev", "", pygame.Rect(0, 0, 0, 0)))
            return
        if event.key == pygame.K_e:
            self._handle_button_press(UIButton("claim_next", "", pygame.Rect(0, 0, 0, 0)))
            return
        if event.key == pygame.K_r:
            self._handle_button_press(UIButton("reset_selection", "", pygame.Rect(0, 0, 0, 0)))
            return
        if event.key == pygame.K_x:
            self._handle_button_press(UIButton("challenge", "", pygame.Rect(0, 0, 0, 0)))
            return
        if event.key == pygame.K_c:
            self._handle_button_press(UIButton("confirm_claim", "", pygame.Rect(0, 0, 0, 0)))
            return
        if event.key == pygame.K_SPACE and player.hand_size:
            index = self.keyboard_card_index % player.hand_size
            self._handle_card_press(index)
            self.keyboard_card_index = (index + 1) % max(1, player.hand_size)

    def _handle_button_press(self, button: UIButton) -> None:
        if self.state is None:
            return
        player = self.engine.current_player()
        if button.key == "claim_prev":
            self.status_message = ""
            legal_claims = self.engine.legal_claim_ranks()
            if legal_claims:
                if self.selected_claim_rank not in legal_claims:
                    self.selected_claim_rank = legal_claims[0]
                else:
                    index = legal_claims.index(self.selected_claim_rank)
                    self.selected_claim_rank = legal_claims[(index - 1) % len(legal_claims)]
            return
        if button.key == "claim_next":
            self.status_message = ""
            legal_claims = self.engine.legal_claim_ranks()
            if legal_claims:
                if self.selected_claim_rank not in legal_claims:
                    self.selected_claim_rank = legal_claims[0]
                else:
                    index = legal_claims.index(self.selected_claim_rank)
                    self.selected_claim_rank = legal_claims[(index + 1) % len(legal_claims)]
            return
        if button.key == "claim_rank":
            self.selected_claim_rank = button.value
            return
        if button.key == "blindfold_minus":
            self.status_message = ""
            self.blindfold_count = max(1, self.blindfold_count - 1)
            return
        if button.key == "blindfold_plus":
            self.status_message = ""
            self.blindfold_count = min(
                max(1, player.claimable_hand_size),
                self.blindfold_count + 1,
            )
            return
        if button.key == "reset_selection":
            self.status_message = ""
            self._reset_human_selection()
            legal_claims = self.engine.legal_claim_ranks()
            self.selected_claim_rank = legal_claims[0] if legal_claims else None
            return
        if button.key == "challenge":
            challenger = player
            if not player.is_human and self._human_can_interrupt_with_challenge():
                challenger = self.state.players[0]
            special_index = self._selected_special_for_player(
                challenger,
                ActionType.CHALLENGE,
            )
            action = TurnAction.challenge(
                special_card_index=special_index,
                note="Human challenge.",
            )
            self._apply_action(challenger, action)
            return
        if button.key == "confirm_claim":
            action = self._build_human_claim_action(player)
            if action is not None:
                self._apply_action(player, action)

    def _selected_special_for(self, action_type: ActionType) -> int | None:
        if self.state is None or self.selected_special_index is None:
            return None
        player = self.engine.current_player()
        return self._selected_special_for_player(player, action_type)

    def _selected_special_for_player(
        self,
        player: PlayerState,
        action_type: ActionType,
    ) -> int | None:
        if self.selected_special_index is None:
            return None
        if self.selected_special_index >= player.hand_size:
            return None
        special = player.hand[self.selected_special_index].special
        if special in allowed_specials_for_action(action_type):
            return self.selected_special_index
        return None

    def _human_can_interrupt_with_challenge(self) -> bool:
        if self.state is None or self.presentation_event is None:
            return False
        if not self.presentation_event.allow_input or self.state.current_claim is None:
            return False
        human = self.state.players[0]
        if human.eliminated:
            return False
        return self.state.current_claim.declared_by != human.name

    def _apply_human_challenge(self) -> None:
        if self.state is None or not self._human_can_interrupt_with_challenge():
            return
        human = self.state.players[0]
        special_index = self._selected_special_for_player(human, ActionType.CHALLENGE)
        action = TurnAction.challenge(
            special_card_index=special_index,
            note="Human challenge.",
        )
        self._apply_action(human, action)

    def _human_eliminated(self) -> bool:
        return self.state is not None and self.state.players[0].eliminated

    def _human_death_screen_active(self) -> bool:
        return self._human_eliminated() and not self._presentation_active()

    def _build_human_claim_action(self, player: PlayerState) -> TurnAction | None:
        legal_claims = self.engine.legal_claim_ranks()
        if not legal_claims or self.selected_claim_rank not in legal_claims:
            self.status_message = "Choose a legal claim first."
            return None
        special_index = self._selected_special_for(ActionType.CLAIM)
        special_type = (
            player.hand[special_index].special if special_index is not None else None
        )
        blindfold_count: int | None = None
        if special_type == SpecialCardType.BLINDFOLD:
            if player.claimable_hand_size == 0:
                self.status_message = "Blindfold needs at least one regular card left."
                return None
            blindfold_count = max(
                1,
                min(self.blindfold_count, player.claimable_hand_size, 4),
            )
            indices: list[int] = []
        elif special_type == SpecialCardType.WILDCARD_HAND:
            indices = []
        else:
            indices = sorted(self.selected_cards)
            if not indices:
                self.status_message = "Select 1 to 4 regular cards for the claim."
                return None
        return TurnAction.claim(
            card_indices=indices,
            claim_rank=self.selected_claim_rank,
            special_card_index=special_index,
            blindfold_card_count=blindfold_count,
            note="Human claim.",
        )

    def _handle_card_press(self, index: int) -> None:
        if self.state is None:
            return
        player = self.engine.current_player()
        if index >= player.hand_size:
            return
        self.status_message = ""
        card = player.hand[index]
        if card.is_special:
            if self.selected_special_index == index:
                self.selected_special_index = None
            else:
                self.selected_special_index = index
                if card.special in {SpecialCardType.BLINDFOLD, SpecialCardType.WILDCARD_HAND}:
                    self.selected_cards.clear()
                if card.special == SpecialCardType.BLINDFOLD:
                    self.blindfold_count = max(
                        1,
                        min(self.blindfold_count, player.claimable_hand_size or 1),
                    )
            return
        selected_special = self._selected_special_for(ActionType.CLAIM)
        if selected_special is not None:
            special = player.hand[selected_special].special
            if special in {SpecialCardType.BLINDFOLD, SpecialCardType.WILDCARD_HAND}:
                self.status_message = f"{special.value} decides the cards for you."
                return
        if index in self.selected_cards:
            self.selected_cards.remove(index)
        elif len(self.selected_cards) < 4:
            self.selected_cards.add(index)
        else:
            self.status_message = "You can only commit up to four cards."

    def _hand_index_at(self, pos: tuple[int, int]) -> int | None:
        rect_hits: list[tuple[pygame.Rect, int]] = []
        for rect, index, mask in reversed(self.hand_targets):
            if not rect.collidepoint(pos):
                continue
            local = (pos[0] - rect.x, pos[1] - rect.y)
            if mask.get_at(local):
                return index
            rect_hits.append((rect, index))
        if not rect_hits:
            return None
        x, y = pos
        _, index = min(
            rect_hits,
            key=lambda item: (
                (item[0].centerx - x) ** 2 + (item[0].centery - y) ** 2,
                -item[1],
            ),
        )
        return index

    def _apply_action(self, player: PlayerState, action: TurnAction) -> None:
        if self.state is None:
            return
        if action.action_type == ActionType.CHALLENGE:
            self._clear_presentation()
        reputation_before = {
            participant.name: participant.reputation
            for participant in self.state.players
        }
        try:
            result = self.engine.process_action(player, action)
        except Exception as error:
            self.status_message = str(error)
            return
        self.last_result = result.summary
        self.status_message = ""
        if self.state.turn_history:
            self._queue_action_presentations(
                self.state.turn_history[-1],
                result.summary,
                reputation_before,
            )
        self._save_snapshot()
        self.turn_marker = None
        self._reset_human_selection()

    def _update_table(self, now: int) -> None:
        if self.state is None or self.engine.is_match_over():
            return
        if self._human_eliminated():
            self.ai_due_at = 0
            return
        if self._presentation_active():
            self.ai_due_at = 0
            return
        current_player = self.engine.current_player()
        if current_player.is_human:
            return
        if self.ai_due_at == 0:
            self.ai_due_at = now + 1800
            return
        if now < self.ai_due_at:
            return
        action = self.engine.choose_ai_action(current_player)
        self._apply_action(current_player, action)
        self.ai_due_at = 0

    def _queue_action_presentations(
        self,
        record: TurnRecord,
        summary: str,
        reputation_before: dict[str, int],
    ) -> None:
        if record.action == ActionType.CLAIM.value:
            self._queue_claim_presentation(record, summary)
        elif record.action == ActionType.CHALLENGE.value:
            self._queue_challenge_presentations(record, summary, reputation_before)

    def _queue_claim_presentation(self, record: TurnRecord, summary: str) -> None:
        rank_label = self._claim_label(record.claim_rank_value, record.claim_text)
        allow_input = (
            self.state is not None
            and self.state.current_claim is not None
            and not self.state.players[0].eliminated
            and record.actor_name != self.state.players[0].name
        )
        detail = f"{record.card_count or 0}x {rank_label.upper()}"
        if record.special_used:
            detail = f"{detail} / {record.special_used.replace('_', ' ').title()}"
        self._queue_presentation(
            PresentationEvent(
                kind="claim",
                title=record.actor_name,
                subtitle="CLAIMS",
                detail=detail,
                actor_name=record.actor_name,
                duration_ms=6000 if allow_input else 2500,
                allow_input=allow_input,
                emphasis="gold",
            )
        )

    def _queue_challenge_presentations(
        self,
        record: TurnRecord,
        summary: str,
        reputation_before: dict[str, int],
    ) -> None:
        target = record.target_name or "the claim"
        rank_label = self._claim_label(record.claim_rank_value, record.claim_text)
        self._queue_presentation(
            PresentationEvent(
                kind="challenge",
                title="Call Liar!",
                subtitle=f"{target} claimed {rank_label}",
                detail=f"{record.actor_name} calls liar.",
                actor_name=record.actor_name,
                target_name=target,
                duration_ms=2600,
                emphasis="danger",
            )
        )
        if record.challenge_successful is True:
            verdict_title = "Bluff Exposed"
            verdict_detail = f"{target}'s {rank_label} was false. {target} risks the chamber."
        else:
            verdict_title = "Claim Holds"
            verdict_detail = f"{target}'s {rank_label} was true. {record.actor_name} risks the chamber."
        self._queue_presentation(
            PresentationEvent(
                kind="verdict",
                title=verdict_title,
                subtitle=rank_label,
                detail=verdict_detail,
                actor_name=record.actor_name,
                target_name=record.bullet_target_name,
                duration_ms=3200,
                emphasis="danger" if record.challenge_successful else "gold",
            )
        )
        for index, result in enumerate(record.bullet_results):
            shielded = index < len(record.bullet_shields) and record.bullet_shields[index]
            eliminated = index < len(record.bullet_eliminations) and record.bullet_eliminations[index]
            chance = record.bullet_chances[index] if index < len(record.bullet_chances) else None
            chamber = record.bullet_chambers[index] if index < len(record.bullet_chambers) else None
            spin_label = ""
            if len(record.bullet_results) > 1:
                spin_label = f"Spin {index + 1} of {len(record.bullet_results)}"
            title = "Shield Absorbs It" if shielded else self._bullet_title(result, eliminated)
            detail = self._bullet_detail(
                result,
                shielded,
                eliminated,
                chance,
                chamber,
                record.bullet_target_name,
            )
            self._queue_presentation(
                PresentationEvent(
                    kind="bullet",
                    title=title,
                    subtitle=spin_label or (record.bullet_target_name or "Revolver spin"),
                    detail=detail,
                    target_name=record.bullet_target_name,
                    duration_ms=6500 if eliminated else 5600,
                    emphasis="danger" if eliminated or result == "loaded" else "gold",
                    chance_percent=chance,
                    chamber_index=chamber,
                )
            )
        human_name = self.state.players[0].name if self.state is not None else None
        human_died = (
            record.bullet_target_name == human_name
            and any(record.bullet_eliminations)
        )
        if human_died:
            return
        for name, delta in record.reputation_deltas.items():
            before = reputation_before.get(name)
            after = before + delta if before is not None else None
            direction = "+" if delta > 0 else ""
            self._queue_presentation(
                PresentationEvent(
                    kind="reputation",
                    title="Reputation",
                    subtitle=f"{direction}{delta}",
                    detail=self._reputation_detail(record, name, delta, before, after, summary),
                    target_name=name,
                    duration_ms=2200,
                    emphasis="gold" if delta > 0 else "danger",
                )
            )

    def _claim_label(self, rank_value: int | None, fallback: str | None) -> str:
        if rank_value is not None:
            try:
                return ClaimRank(rank_value).label
            except ValueError:
                pass
        return (fallback or "Claim").replace("_", " ").title()

    def _bullet_title(self, result: str, eliminated: bool) -> str:
        if eliminated or result == "loaded":
            return "Bang! Loaded Chamber"
        if result == "misfire":
            return "Misfire!"
        return "Click. Empty Chamber"

    def _bullet_detail(
        self,
        result: str,
        shielded: bool,
        eliminated: bool,
        chance: int | None,
        chamber: int | None,
        target_name: str | None,
    ) -> str:
        target = target_name or "The target"
        if shielded:
            return f"Shielded. {target} survives."
        chamber_text = f"Chamber {chamber + 1}" if chamber is not None else "The chamber"
        if eliminated:
            return f"{chamber_text} was loaded. {target} is eliminated."
        if result == "misfire":
            return f"{chamber_text} misfired. {target} survives."
        return f"{chamber_text} was empty. {target} survives."

    def _reputation_detail(
        self,
        record: TurnRecord,
        name: str,
        delta: int,
        before: int | None,
        after: int | None,
        fallback: str,
    ) -> str:
        if record.challenge_successful is True:
            reason = (
                "Correct call."
                if name == record.actor_name
                else "Bluff exposed."
            )
        elif record.challenge_successful is False:
            reason = (
                "Wrong call."
                if name == record.actor_name
                else "Claim defended."
            )
        else:
            reason = fallback
        if before is None or after is None:
            return reason
        direction = "+" if delta > 0 else ""
        return f"{reason} {before}->{after} ({direction}{delta})."

    def _draw(self, now: int) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self.buttons = []
        self.hand_targets = []
        self._draw_background(now)
        if self.mode == "menu":
            self._draw_menu(mouse_pos, now)
        else:
            self._draw_table(mouse_pos, now)

    def _layout(self) -> dict[str, object]:
        claim_hud = pygame.Rect(28, 24, 430, 58)
        move_hud = pygame.Rect(1054, 24, 202, 132)
        control_rect = pygame.Rect(1000, 206, 244, 286)
        table_rect = pygame.Rect(42, 420, 1196, 370)
        hand_rect = pygame.Rect(250, 560, 780, 220)
        claim_buttons_top = control_rect.y + 18
        seat_positions = {
            0: (table_rect.centerx, 690),
            1: (190, 360),
            2: (490, 238),
            3: (790, 210),
            4: (1090, 360),
        }
        return {
            "claim_hud": claim_hud,
            "move_hud": move_hud,
            "control_rect": control_rect,
            "table_rect": table_rect,
            "hand_rect": hand_rect,
            "seat_positions": seat_positions,
            "claim_buttons_top": claim_buttons_top,
        }

    def _draw_background(self, now: int) -> None:
        self.screen.fill(self.colors["bg"])
        if self.mode == "menu":
            background = (
                self.assets.cover_image("menu_showdown", (SCREEN_WIDTH, SCREEN_HEIGHT))
                or self.assets.cover_image("menu_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
                or self.assets.cover_image("bar_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
                or self.assets.background("menu_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
            )
            if background is not None:
                self.screen.blit(background, (0, 0))
            return
        else:
            background = (
                self.assets.cover_image("table_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
                or self.assets.cover_image("bar_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
            )
            if background is not None:
                self.screen.blit(background, (0, 0))
            else:
                self._draw_table_room_background(now)
        vignette = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(vignette, (8, 8, 10, 62), vignette.get_rect(), 0, 0)
        pygame.draw.rect(
            vignette,
            (0, 0, 0, 0),
            pygame.Rect(120, 56, SCREEN_WIDTH - 240, SCREEN_HEIGHT - 112),
            border_radius=170,
        )
        self.screen.blit(vignette, (0, 0))

    def _draw_table_room_background(self, now: int) -> None:
        wall_height = 458
        for y in range(wall_height):
            blend = y / wall_height
            color = (
                int(90 - 24 * blend),
                int(44 - 12 * blend),
                int(38 - 10 * blend),
            )
            pygame.draw.line(self.screen, color, (0, y), (SCREEN_WIDTH, y))
        for y in range(wall_height, SCREEN_HEIGHT):
            blend = (y - wall_height) / max(1, SCREEN_HEIGHT - wall_height)
            color = (
                int(80 - 16 * blend),
                int(50 - 12 * blend),
                int(34 - 8 * blend),
            )
            pygame.draw.line(self.screen, color, (0, y), (SCREEN_WIDTH, y))
        pygame.draw.rect(self.screen, (48, 31, 25), pygame.Rect(0, 360, SCREEN_WIDTH, 120))
        for x in range(40, SCREEN_WIDTH, 118):
            pygame.draw.rect(self.screen, (41, 27, 22), pygame.Rect(x, 364, 70, 104), 2, 8)
        wall_depth = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(wall_depth, (0, 0, 0, 70), pygame.Rect(248, 132, 756, 240))
        pygame.draw.ellipse(wall_depth, (255, 170, 98, 20), pygame.Rect(422, 96, 428, 198))
        pygame.draw.rect(wall_depth, (0, 0, 0, 64), pygame.Rect(0, 0, 184, SCREEN_HEIGHT))
        pygame.draw.rect(wall_depth, (0, 0, 0, 64), pygame.Rect(SCREEN_WIDTH - 184, 0, 184, SCREEN_HEIGHT))
        self.screen.blit(wall_depth, (0, 0))
        left_sideboard = pygame.Rect(168, 246, 120, 128)
        center_drawer = pygame.Rect(448, 182, 126, 170)
        right_chair = pygame.Rect(850, 172, 162, 188)
        right_table = pygame.Rect(1026, 256, 112, 106)
        furniture_shadow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.ellipse(furniture_shadow, (0, 0, 0, 34), pygame.Rect(138, 300, 170, 58))
        pygame.draw.ellipse(furniture_shadow, (0, 0, 0, 30), pygame.Rect(428, 318, 170, 52))
        pygame.draw.ellipse(furniture_shadow, (0, 0, 0, 38), pygame.Rect(820, 320, 240, 68))
        pygame.draw.ellipse(furniture_shadow, (0, 0, 0, 28), pygame.Rect(1010, 330, 138, 46))
        self.screen.blit(furniture_shadow, (0, 0))
        pygame.draw.rect(self.screen, (61, 39, 30), left_sideboard, border_radius=8)
        pygame.draw.rect(self.screen, (50, 32, 24), center_drawer, border_radius=8)
        pygame.draw.rect(self.screen, (58, 38, 30), right_chair, border_radius=22)
        pygame.draw.rect(self.screen, (61, 39, 29), right_table, border_radius=10)
        for drawer in range(3):
            rect = pygame.Rect(center_drawer.x + 18, center_drawer.y + 22 + drawer * 44, 90, 26)
            pygame.draw.rect(self.screen, (72, 48, 35), rect, border_radius=6)
            pygame.draw.circle(self.screen, (171, 136, 94), (rect.centerx, rect.centery), 3)
        chair_back = pygame.Rect(right_chair.x + 26, right_chair.y + 10, 110, 122)
        pygame.draw.rect(self.screen, (66, 43, 34), chair_back, border_radius=30)
        barrel = pygame.Rect(1114, 286, 78, 108)
        pygame.draw.ellipse(self.screen, (76, 49, 33), barrel)
        pygame.draw.rect(self.screen, (74, 47, 32), barrel.inflate(-8, -22), border_radius=20)
        for band in range(3):
            y = barrel.y + 20 + band * 28
            pygame.draw.line(self.screen, (37, 26, 19), (barrel.x + 8, y), (barrel.right - 8, y), 3)
        bottle = pygame.Rect(182, 118, 20, 36)
        bottle2 = pygame.Rect(1036, 90, 20, 38)
        for rect in (bottle, bottle2):
            pygame.draw.rect(self.screen, (92, 82, 58), pygame.Rect(rect.x + 4, rect.y - 4, rect.width - 8, 6), border_radius=2)
            pygame.draw.rect(self.screen, (84, 118, 86), rect, border_radius=4)
            pygame.draw.rect(self.screen, (176, 160, 116), rect, 2, 4)
        lamp_glow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.circle(lamp_glow, (255, 177, 92, 18), (626, 154), 240)
        pygame.draw.circle(lamp_glow, (255, 194, 120, 10), (214, 164), 170)
        pygame.draw.circle(lamp_glow, (255, 180, 116, 10), (1078, 188), 190)
        self.screen.blit(lamp_glow, (0, 0))
        floor_glow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        horizon_y = 458
        for x in range(-120, SCREEN_WIDTH + 160, 86):
            pygame.draw.line(
                floor_glow,
                (33, 18, 14, 72),
                (SCREEN_WIDTH // 2, horizon_y),
                (x, SCREEN_HEIGHT),
                2,
            )
        pygame.draw.ellipse(floor_glow, (255, 208, 132, 10), pygame.Rect(242, 390, 800, 268))
        self.screen.blit(floor_glow, (0, 0))
        shadow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (0, 0, 0, 42), pygame.Rect(0, 430, SCREEN_WIDTH, 80))
        pygame.draw.ellipse(shadow, (0, 0, 0, 56), pygame.Rect(264, 168, 740, 180))
        self.screen.blit(shadow, (0, 0))

    def _draw_menu(self, mouse_pos: tuple[int, int], now: int) -> None:
        title_font = pygame.font.SysFont("agency fb", 92, bold=False)
        title_x = 86
        title_y = 286
        for line in ("SHOW", "DOWN"):
            self._blit_led_text(title_font, line, (title_x, title_y))
            title_y += 92

        button_specs = [
            ("menu_new", "ENTER THE BAR", True),
            ("menu_resume", "RESUME", self.saved_summary is not None),
            ("menu_quit", "EXIT", True),
        ]
        top = 540
        for key, label, enabled in button_specs:
            rect = pygame.Rect(86, top, 318, 54)
            button = UIButton(key=key, label=label, rect=rect, enabled=enabled)
            self.buttons.append(button)
            loading_this_button = (
                (self.menu_loading_action == "new" and key == "menu_new")
                or (self.menu_loading_action == "resume" and key == "menu_resume")
            )
            self._draw_menu_option(
                button,
                mouse_pos,
                primary=key == "menu_new" or loading_this_button,
                loading=loading_this_button,
                now=now,
            )
            top += 66

    def _saved_alive_players(self) -> list[str]:
        if self.saved_summary is None:
            return []
        alive_players = self.saved_summary.get("alive_players")
        if isinstance(alive_players, list):
            return [str(name) for name in alive_players]
        players = self.saved_summary.get("players", [])
        if not isinstance(players, list):
            return []
        return [
            str(player["name"])
            for player in players
            if isinstance(player, dict)
            and not player.get("eliminated", False)
            and "name" in player
        ]

    def _draw_menu_gallery(self) -> None:
        portrait_size = (78, 96)
        top = 218
        spacing = 16
        total_width = len(OPPONENT_PROFILES) * portrait_size[0] + (len(OPPONENT_PROFILES) - 1) * spacing
        start_x = SCREEN_WIDTH // 2 - total_width // 2
        for index, profile in enumerate(OPPONENT_PROFILES):
            x = start_x + index * (portrait_size[0] + spacing)
            frame = pygame.Rect(x, top, portrait_size[0], portrait_size[1])
            shadow = pygame.Surface((frame.width + 14, frame.height + 14), pygame.SRCALPHA)
            pygame.draw.rect(shadow, (0, 0, 0, 44), shadow.get_rect(), border_radius=18)
            self.screen.blit(shadow, (frame.x - 7, frame.y + 6))
            image = self.assets.portrait(profile.key, portrait_size)
            self.screen.blit(image, frame.topleft)
            label = self.fonts["tiny"].render(profile.display_name, True, self.colors["muted"])
            self.screen.blit(label, label.get_rect(center=(frame.centerx, frame.bottom + 16)))

    def _draw_table(self, mouse_pos: tuple[int, int], now: int) -> None:
        if self.state is None:
            return
        layout = self._layout()
        self._draw_seats(layout["seat_positions"], now)
        self._draw_table_surface(layout["table_rect"], now)
        self._draw_table_props(layout["table_rect"])
        self._draw_center_claim(layout["table_rect"], now)
        self._draw_reputation_plates(layout["seat_positions"], now)
        self._draw_human_hand(layout["hand_rect"], mouse_pos)
        self._draw_claim_hud(layout["claim_hud"])
        self._draw_action_hud(layout["move_hud"])
        self._draw_human_revolver_status()
        self._build_table_buttons(layout["control_rect"], layout["claim_buttons_top"])
        for button in self.buttons:
            self._draw_button(button, mouse_pos)
        self._draw_status_toast()
        self._draw_presentation_overlay(now)
        if self._human_death_screen_active():
            self._draw_death_overlay(mouse_pos)
        elif self.engine.is_match_over() and not self._presentation_active():
            self._draw_end_overlay(mouse_pos)

    def _draw_neon_title(
        self,
        lines: tuple[str, ...],
        pos: tuple[int, int],
    ) -> None:
        x, y = pos
        for line in lines:
            self._blit_neon_text(self.fonts["neon"], line, (x, y))
            y += self.fonts["neon"].get_linesize() - 18

    def _blit_neon_text(
        self,
        font: pygame.font.Font,
        text: str,
        pos: tuple[int, int],
    ) -> pygame.Rect:
        glow_color = (255, 42, 31)
        for radius, alpha in ((12, 28), (7, 48), (3, 92)):
            glow = font.render(text, True, glow_color)
            glow.set_alpha(alpha)
            half = max(1, radius // 2)
            for dx, dy in (
                (-radius, 0),
                (radius, 0),
                (0, -radius),
                (0, radius),
                (-half, -half),
                (half, -half),
                (-half, half),
                (half, half),
            ):
                self.screen.blit(glow, (pos[0] + dx, pos[1] + dy))

        shadow = font.render(text, True, (84, 5, 5))
        self.screen.blit(shadow, (pos[0] + 3, pos[1] + 4))
        surface = font.render(text, True, (255, 72, 55))
        rect = surface.get_rect(topleft=pos)
        self.screen.blit(surface, rect)
        hot_core = font.render(text, True, (255, 193, 146))
        hot_core.set_alpha(92)
        self.screen.blit(hot_core, (pos[0] + 1, pos[1] - 1))
        return rect

    def _blit_led_text(
        self,
        font: pygame.font.Font,
        text: str,
        pos: tuple[int, int],
    ) -> pygame.Rect:
        glow_color = (255, 38, 28)
        for radius, alpha in ((8, 30), (4, 64), (2, 105)):
            glow = font.render(text, True, glow_color)
            glow.set_alpha(alpha)
            self.screen.blit(glow, (pos[0] - radius, pos[1]))
            self.screen.blit(glow, (pos[0] + radius, pos[1]))
            self.screen.blit(glow, (pos[0], pos[1] - radius))
            self.screen.blit(glow, (pos[0], pos[1] + radius))
        base = font.render(text, True, (255, 64, 48))
        rect = base.get_rect(topleft=pos)
        self.screen.blit(base, rect)
        core = font.render(text, True, (255, 220, 180))
        core.set_alpha(96)
        self.screen.blit(core, pos)
        return rect

    def _draw_menu_option(
        self,
        button: UIButton,
        mouse_pos: tuple[int, int],
        *,
        primary: bool = False,
        loading: bool = False,
        now: int = 0,
    ) -> None:
        hovered = button.enabled and button.rect.collidepoint(mouse_pos)
        highlighted = button.enabled and (primary or hovered)
        font = self.fonts["menu"]
        if highlighted:
            color = self.colors["cream"]
        elif button.enabled:
            color = (183, 177, 168)
        else:
            color = (103, 99, 96)

        label = font.render(button.label, True, color)
        label_rect = label.get_rect(midleft=(button.rect.x, button.rect.centery))
        if highlighted:
            glow = font.render(button.label, True, (255, 60, 42))
            glow.set_alpha(62 if loading else 34)
            for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                self.screen.blit(glow, label_rect.move(dx, dy))
        self.screen.blit(label, label_rect)
        if loading:
            self._draw_menu_loading_dots(label_rect, now)

    def _draw_menu_loading_dots(self, label_rect: pygame.Rect, now: int) -> None:
        start_x = label_rect.right + 22
        center_y = label_rect.centery + 3
        for index in range(3):
            phase = (now // 150 + index) % 3
            radius = 4 + (1 if phase == 0 else 0)
            alpha = 230 if phase == 0 else 130
            color = (255, 208, 112, alpha)
            dot = pygame.Surface((18, 18), pygame.SRCALPHA)
            pygame.draw.circle(dot, color, (9, 9), radius)
            pygame.draw.circle(dot, (255, 77, 46, max(50, alpha // 3)), (9, 9), radius + 4, 1)
            self.screen.blit(dot, dot.get_rect(center=(start_x + index * 18, center_y)))

    def _draw_presentation_overlay(self, now: int) -> None:
        event = self.presentation_event
        if event is None:
            return
        remaining_ms = max(0, self.presentation_until - now)
        progress = 1 - remaining_ms / max(1, event.duration_ms)

        if event.kind == "bullet":
            self._draw_revolver_presentation(event, progress)
            return
        if event.kind == "reputation":
            self._draw_reputation_presentation(event, progress)
            return
        self._draw_minimal_presentation(event, progress, remaining_ms)

    def _draw_minimal_presentation(
        self,
        event: PresentationEvent,
        progress: float,
        remaining_ms: int,
    ) -> None:
        color = (232, 78, 55) if event.emphasis == "danger" else (222, 176, 86)
        center = self._presentation_text_center(event)
        title = event.title.upper()
        subtitle = event.subtitle.upper() if event.subtitle else ""
        detail = event.detail.upper() if event.detail else ""

        if event.kind == "claim":
            title_font = self._font_for_width(
                title,
                (self.fonts["hud_title"], self.fonts["hud_body"], self.fonts["hud_small"]),
                360,
            )
            self._blit_hud_text(title_font, title, center, anchor="center")
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (center[0], center[1] + 34),
                anchor="center",
                color=(255, 236, 179),
            )
            self._blit_hud_text(
                self.fonts["hud_body"],
                detail,
                (center[0], center[1] + 68),
                anchor="center",
                color=(255, 248, 220),
            )
            if event.allow_input and remaining_ms > 0:
                self._draw_call_liar_prompt(
                    (center[0], center[1] + 108),
                    remaining_ms,
                    progress,
                )
            return

        self._blit_hud_text(
            self.fonts["hud_title"],
            title,
            center,
            anchor="center",
            color=(255, 241, 199) if event.emphasis != "danger" else (255, 168, 132),
        )
        if subtitle:
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (center[0], center[1] + 46),
                anchor="center",
                color=color,
            )
        if detail:
            self._draw_centered_hud_lines(
                detail,
                pygame.Rect(center[0] - 330, center[1] + 78, 660, 58),
                self.fonts["hud_small"],
                (255, 235, 190),
            )
        self._draw_minimal_progress(
            pygame.Rect(center[0] - 170, center[1] + 144, 340, 4),
            color,
            progress,
        )

    def _presentation_text_center(self, event: PresentationEvent) -> tuple[int, int]:
        if event.kind == "reputation":
            return (SCREEN_WIDTH // 2, 592)
        return (SCREEN_WIDTH // 2, 350)

    def _draw_call_liar_prompt(
        self,
        center: tuple[int, int],
        remaining_ms: int,
        progress: float,
    ) -> None:
        font = self.fonts["hud_body"]
        label = font.render("CALL LIAR", True, (255, 241, 199))
        key_rect = pygame.Rect(0, 0, 32, 26)
        timer_text = str(math.ceil(remaining_ms / 1000))
        timer = font.render(timer_text, True, (255, 241, 199))
        gap = 10
        total_width = label.get_width() + gap + key_rect.width + gap + timer.get_width()
        left = center[0] - total_width // 2
        label_rect = self._blit_hud_text(
            font,
            "CALL LIAR",
            (left, center[1]),
            anchor="midleft",
            color=(255, 241, 199),
        )
        key_rect.midleft = (label_rect.right + gap, center[1])
        pygame.draw.rect(self.screen, (68, 38, 18), key_rect, border_radius=4)
        pygame.draw.rect(self.screen, (224, 172, 78), key_rect, 1, 4)
        key = font.render("X", True, (255, 241, 199))
        self.screen.blit(key, key.get_rect(center=key_rect.center))
        self._blit_hud_text(
            font,
            timer_text,
            (key_rect.right + gap, center[1]),
            anchor="midleft",
            color=(255, 241, 199),
        )
        self._draw_minimal_progress(
            pygame.Rect(center[0] - 92, center[1] + 20, 184, 4),
            (224, 172, 78),
            progress,
        )

    def _draw_minimal_progress(
        self,
        rect: pygame.Rect,
        color: tuple[int, int, int],
        progress: float,
    ) -> None:
        pygame.draw.rect(self.screen, (68, 38, 18), rect, border_radius=2)
        pygame.draw.rect(
            self.screen,
            color,
            pygame.Rect(rect.x, rect.y, max(2, int(rect.width * progress)), rect.height),
            border_radius=2,
        )

    def _presentation_panel_rect(self) -> pygame.Rect:
        return pygame.Rect(204, 150, 872, 300)

    def _draw_presentation_frame(
        self,
        panel: pygame.Rect,
        border: tuple[int, int, int],
        *,
        split_x: int | None = None,
    ) -> None:
        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        for y in range(panel.height):
            distance = abs((y / max(1, panel.height - 1)) - 0.5) * 2
            alpha = int(178 * (0.78 - distance * 0.28))
            pygame.draw.line(surface, (8, 7, 6, max(76, alpha)), (0, y), (panel.width, y))
        self.screen.blit(surface, panel.topleft)

        line_inset = 34
        pygame.draw.line(
            self.screen,
            (*border, 184),
            (panel.x + line_inset, panel.y + 14),
            (panel.right - line_inset, panel.y + 14),
            1,
        )
        pygame.draw.line(
            self.screen,
            (*border, 138),
            (panel.x + line_inset, panel.bottom - 18),
            (panel.right - line_inset, panel.bottom - 18),
            2,
        )
        if split_x is not None:
            pygame.draw.line(
                self.screen,
                (*border, 126),
                (panel.x + split_x, panel.y + 34),
                (panel.x + split_x, panel.bottom - 42),
                1,
            )

    def _draw_presentation_progress(
        self,
        panel: pygame.Rect,
        border: tuple[int, int, int],
        progress: float,
    ) -> None:
        bar_width = panel.width - 80
        bar_rect = pygame.Rect(panel.x + 40, panel.bottom - 20, bar_width, 4)
        pygame.draw.rect(self.screen, (60, 41, 28), bar_rect, border_radius=2)
        pygame.draw.rect(
            self.screen,
            border,
            pygame.Rect(bar_rect.x, bar_rect.y, int(bar_width * progress), bar_rect.height),
            border_radius=2,
        )

    def _draw_revolver_presentation(
        self,
        event: PresentationEvent,
        progress: float,
    ) -> None:
        reveal_at = 0.62
        reveal = progress >= reveal_at
        detail_lower = event.detail.lower()
        eliminated = "eliminated" in detail_lower
        loaded = "loaded" in detail_lower or event.emphasis == "danger"
        danger_result = reveal and (loaded or eliminated)
        accent = (232, 78, 55) if danger_result else (222, 176, 86)
        if reveal and eliminated:
            dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 34))
            self.screen.blit(dim, (0, 0))

        wheel_center = (SCREEN_WIDTH // 2, 226)
        spin_amount = min(progress / reveal_at, 1.0)
        spin_chamber = int(spin_amount * 28) % 6
        locked = reveal and event.chamber_index is not None
        active_chamber = event.chamber_index if locked else spin_chamber
        chamber_angle = (
            -math.tau * active_chamber / 6
            if locked
            else spin_amount * math.tau * 3.2
        )

        self._draw_revolver_chamber_wheel(
            wheel_center,
            active_chamber,
            chamber_angle,
            reveal=reveal,
            loaded=loaded,
            accent=accent,
        )
        pygame.draw.polygon(
            self.screen,
            accent,
            [
                (wheel_center[0], wheel_center[1] - 104),
                (wheel_center[0] - 9, wheel_center[1] - 86),
                (wheel_center[0] + 9, wheel_center[1] - 86),
            ],
        )

        title = (
            "ELIMINATED"
            if reveal and eliminated
            else "LOADED"
            if reveal and loaded
            else "SURVIVED"
            if reveal
            else "TRYING CHAMBER"
        )
        detail = event.detail.upper() if reveal else "THE CHAMBER TURNS"
        subtitle = event.subtitle.upper() if event.subtitle else ""
        title_color = (255, 160, 116) if danger_result else (255, 241, 199)
        self._blit_hud_text(
            self.fonts["hud_body"],
            "REVOLVER",
            (SCREEN_WIDTH // 2, wheel_center[1] + 110),
            anchor="center",
            color=(222, 176, 86),
        )
        self._blit_hud_text(
            self.fonts["hud_title"],
            title,
            (SCREEN_WIDTH // 2, wheel_center[1] + 150),
            anchor="center",
            color=title_color,
        )
        if subtitle:
            self._blit_hud_text(
                self.fonts["hud_body"],
                subtitle,
                (SCREEN_WIDTH // 2, wheel_center[1] + 190),
                anchor="center",
                color=accent,
            )
        self._draw_centered_hud_lines(
            detail,
            pygame.Rect(SCREEN_WIDTH // 2 - 330, wheel_center[1] + 220, 660, 58),
            self.fonts["hud_small"],
            (255, 235, 190),
        )
        target = self._player_by_name(event.target_name)
        if target is not None:
            self._draw_revolver_status_chip(
                target,
                pygame.Rect(SCREEN_WIDTH // 2 - 54, wheel_center[1] + 286, 108, 26),
            )
        elif event.chance_percent is not None:
            self._blit_hud_text(
                self.fonts["hud_body"],
                f"{event.chance_percent}% LOADED",
                (SCREEN_WIDTH // 2, wheel_center[1] + 292),
                anchor="center",
                color=(222, 176, 86),
            )
        self._draw_minimal_progress(
            pygame.Rect(SCREEN_WIDTH // 2 - 210, wheel_center[1] + 324, 420, 5),
            accent,
            progress,
        )

    def _draw_revolver_chamber_wheel(
        self,
        center: tuple[int, int],
        active_chamber: int,
        chamber_angle: float,
        *,
        reveal: bool,
        loaded: bool,
        accent: tuple[int, int, int],
    ) -> None:
        shadow = pygame.Surface((190, 176), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 98), shadow.get_rect())
        self.screen.blit(shadow, shadow.get_rect(center=(center[0] + 7, center[1] + 12)))

        pygame.draw.circle(self.screen, (18, 11, 7), center, 82)
        pygame.draw.circle(self.screen, (92, 55, 27), center, 78)
        pygame.draw.circle(self.screen, (37, 26, 18), center, 66)
        pygame.draw.circle(self.screen, (226, 170, 73), center, 80, 2)
        pygame.draw.circle(self.screen, (139, 90, 38), center, 66, 3)
        pygame.draw.circle(self.screen, (12, 9, 7), center, 27)
        pygame.draw.circle(self.screen, (226, 170, 73), center, 27, 2)

        for index in range(6):
            theta = -math.pi / 2 + math.tau * index / 6 + chamber_angle
            chamber_center = (
                int(center[0] + math.cos(theta) * 43),
                int(center[1] + math.sin(theta) * 43),
            )
            is_active = index == active_chamber
            hole_radius = 16 if not is_active else 19
            pygame.draw.circle(self.screen, (9, 7, 5), chamber_center, hole_radius)
            pygame.draw.circle(self.screen, (218, 157, 62), chamber_center, hole_radius, 2)
            pygame.draw.circle(self.screen, (32, 22, 14), chamber_center, max(7, hole_radius - 6))
            if is_active and reveal:
                pygame.draw.circle(self.screen, accent, chamber_center, hole_radius + 4, 2)
                if loaded:
                    pygame.draw.circle(self.screen, (235, 184, 88), chamber_center, 9)
                    pygame.draw.circle(self.screen, (126, 45, 31), chamber_center, 5)
                else:
                    pygame.draw.circle(self.screen, (246, 214, 136), chamber_center, 5, 2)
            else:
                pygame.draw.circle(self.screen, (246, 214, 136), (chamber_center[0] - 4, chamber_center[1] - 4), 2)

    def _draw_reputation_presentation(
        self,
        event: PresentationEvent,
        progress: float,
    ) -> None:
        border = self.colors["gold"] if event.emphasis != "danger" else (216, 60, 44)
        dim = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 34))
        self.screen.blit(dim, (0, 0))
        width = 470
        panel = pygame.Rect((SCREEN_WIDTH - width) // 2, 578, width, 128)
        lift = int(math.sin(min(1, progress) * math.pi) * 8)
        panel.y -= lift
        surface = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (10, 10, 9, 214), surface.get_rect(), border_radius=18)
        pygame.draw.rect(surface, (*border, 230), surface.get_rect(), 2, 18)
        self.screen.blit(surface, panel.topleft)
        self._blit_shadow_text(
            self.fonts["hud_title"],
            event.title.upper(),
            self.colors["text"],
            (panel.x + 28, panel.y + 22),
        )
        self._blit_shadow_text(
            self.fonts["hud_title"],
            event.subtitle,
            border,
            (panel.right - 28, panel.y + 22),
            anchor="topright",
        )
        self._draw_wrapped_text(
            [event.detail],
            pygame.Rect(panel.x + 28, panel.y + 70, panel.width - 56, 48),
            self.fonts["hud_small"],
            self.colors["cream"],
        )

    def _draw_presentation_button(self, button: UIButton, *, danger: bool = False) -> None:
        fill = (98, 29, 25, 238) if danger else (28, 52, 51, 232)
        border = (255, 213, 124) if danger else self.colors["gold"]
        shadow = button.rect.move(3, 4)
        pygame.draw.rect(self.screen, (0, 0, 0, 120), shadow, border_radius=12)
        pygame.draw.rect(self.screen, fill, button.rect, border_radius=12)
        pygame.draw.rect(self.screen, border, button.rect, 2, 12)
        font = self._font_for_width(
            button.label,
            (self.fonts["hud_body"], self.fonts["hud_small"], self.fonts["tiny"]),
            button.rect.width - 18,
        )
        label = font.render(button.label, True, self.colors["cream"])
        self.screen.blit(label, label.get_rect(center=button.rect.center))

    def _draw_centered_text_block(
        self,
        text: str,
        rect: pygame.Rect,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> None:
        lines = self._wrap_line(text, font, rect.width)
        if not lines:
            return
        line_height = font.get_linesize()
        total_height = line_height * len(lines)
        y = rect.y + max(0, (rect.height - total_height) // 2)
        for line in lines:
            surface = font.render(line, True, color)
            self.screen.blit(
                surface,
                surface.get_rect(center=(rect.centerx, y + surface.get_height() // 2)),
            )
            y += line_height

    def _font_for_width(
        self,
        text: str,
        fonts: tuple[pygame.font.Font, ...],
        width: int,
    ) -> pygame.font.Font:
        for font in fonts:
            if font.size(text)[0] <= width:
                return font
        return fonts[-1]

    def _draw_bullet_chambers(self, panel: pygame.Rect, event: PresentationEvent) -> None:
        center_y = panel.y + 176
        start_x = panel.centerx - 78
        for index in range(6):
            center = (start_x + index * 31, center_y)
            color = (43, 39, 36)
            border = self.colors["gold"]
            if event.chamber_index == index:
                color = (111, 42, 34) if event.emphasis == "danger" else (96, 77, 44)
                border = (244, 115, 92) if event.emphasis == "danger" else self.colors["cream"]
            pygame.draw.circle(self.screen, color, center, 12)
            pygame.draw.circle(self.screen, border, center, 12, 2)
        if event.chance_percent is not None:
            chance = self.fonts["hud_small"].render(
                f"{event.chance_percent}% LOADED ODDS",
                True,
                self.colors["muted"],
            )
            self.screen.blit(chance, chance.get_rect(center=(panel.centerx, center_y + 34)))

    def _blit_shadow_text(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        pos: tuple[int, int],
        *,
        anchor: str = "topleft",
        shadow_color: tuple[int, int, int] = (25, 15, 12),
    ) -> pygame.Rect:
        shadow = font.render(text, True, shadow_color)
        shadow_rect = shadow.get_rect(**{anchor: (pos[0] + 2, pos[1] + 2)})
        self.screen.blit(shadow, shadow_rect)
        surface = font.render(text, True, color)
        rect = surface.get_rect(**{anchor: pos})
        self.screen.blit(surface, rect)
        return rect

    def _blit_hud_text(
        self,
        font: pygame.font.Font,
        text: str,
        pos: tuple[int, int],
        *,
        anchor: str = "topleft",
        color: tuple[int, int, int] = (255, 252, 236),
    ) -> pygame.Rect:
        shadow = font.render(text, True, (0, 0, 0))
        shadow.set_alpha(225)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (2, 2)):
            self.screen.blit(shadow, shadow.get_rect(**{anchor: (pos[0] + dx, pos[1] + dy)}))
        surface = font.render(text, True, color)
        rect = surface.get_rect(**{anchor: pos})
        self.screen.blit(surface, rect)
        return rect

    def _draw_centered_hud_lines(
        self,
        text: str,
        rect: pygame.Rect,
        font: pygame.font.Font,
        color: tuple[int, int, int],
    ) -> None:
        lines = self._wrap_line(text, font, rect.width)
        if not lines:
            return
        line_height = font.get_linesize()
        total_height = line_height * len(lines)
        y = rect.y + max(0, (rect.height - total_height) // 2)
        for line in lines:
            self._blit_hud_text(
                font,
                line,
                (rect.centerx, y + line_height // 2),
                anchor="center",
                color=color,
            )
            y += line_height

    def _draw_keycap(
        self,
        key: str,
        pos: tuple[int, int],
        *,
        anchor: str = "topright",
    ) -> pygame.Rect:
        font = self.fonts["hud_small"]
        pad_x = 7
        pad_y = 3
        text = font.render(key, True, self.colors["text"])
        rect = pygame.Rect(0, 0, text.get_width() + pad_x * 2, text.get_height() + pad_y * 2)
        setattr(rect, anchor, pos)
        shadow = rect.move(2, 2)
        pygame.draw.rect(self.screen, (0, 0, 0, 118), shadow, border_radius=7)
        pygame.draw.rect(self.screen, (13, 12, 10, 206), rect, border_radius=7)
        pygame.draw.rect(self.screen, (205, 169, 88), rect, 1, 7)
        self.screen.blit(text, text.get_rect(center=rect.center))
        return rect

    def _draw_saloon_panel(
        self,
        rect: pygame.Rect,
        *,
        active: bool = False,
        danger: bool = False,
        alpha: int = 232,
    ) -> None:
        shadow = rect.move(4, 5)
        shadow_surface = pygame.Surface(shadow.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow_surface, (0, 0, 0, 110), shadow_surface.get_rect(), border_radius=10)
        self.screen.blit(shadow_surface, shadow.topleft)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        base = (28, 15, 10, alpha)
        wood = (61, 34, 20, min(210, alpha))
        inner = rect.inflate(-8, -8)
        inner.move_ip(-rect.x, -rect.y)
        pygame.draw.rect(panel, base, panel.get_rect(), border_radius=10)
        pygame.draw.rect(panel, wood, inner, border_radius=7)
        pygame.draw.line(panel, (154, 91, 42, 150), (12, 8), (rect.width - 12, 8), 1)
        pygame.draw.line(panel, (11, 8, 6, 150), (12, rect.height - 9), (rect.width - 12, rect.height - 9), 1)
        border = (236, 182, 78) if active else (153, 106, 55)
        if danger:
            border = (208, 82, 61)
        pygame.draw.rect(panel, border, panel.get_rect(), 2, border_radius=10)
        pygame.draw.rect(panel, (44, 25, 15, 185), inner, 1, border_radius=7)
        if active:
            glow = (255, 52, 36, 82) if danger else (255, 200, 92, 76)
            pygame.draw.line(panel, glow, (16, rect.height - 4), (rect.width - 16, rect.height - 4), 2)
        self.screen.blit(panel, rect.topleft)

    def _blit_soft_ellipse(
        self,
        rect: pygame.Rect,
        color: tuple[int, int, int, int],
    ) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(surface, color, surface.get_rect())
        self.screen.blit(surface, rect.topleft)

    def _draw_hud_box(
        self,
        rect: pygame.Rect,
        eyebrow: str,
        title: str,
        lines: list[str],
    ) -> None:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, self.colors["panel_soft"], panel.get_rect(), border_radius=22)
        pygame.draw.rect(panel, (*self.colors["border"], 210), panel.get_rect(), 2, 22)
        self.screen.blit(panel, rect.topleft)
        eyebrow_surface = self.fonts["tiny"].render(eyebrow, True, self.colors["gold"])
        self.screen.blit(eyebrow_surface, (rect.x + 16, rect.y + 14))
        title_surface = self.fonts["body_bold"].render(title, True, self.colors["text"])
        self.screen.blit(title_surface, (rect.x + 16, rect.y + 34))
        self._draw_wrapped_text(
            lines,
            pygame.Rect(rect.x + 16, rect.y + 60, rect.width - 32, rect.height - 74),
            self.fonts["small"],
            self.colors["muted"],
        )

    def _draw_claim_hud(self, rect: pygame.Rect) -> None:
        if self.state is None:
            return
        center_y = rect.y + 30
        if self.state.current_claim is None:
            current = self.engine.current_player()
            if current.is_human and self.selected_claim_rank is not None:
                self._draw_inline_claim_status(
                    rect,
                    "SELECTED",
                    self.selected_claim_rank.label.upper(),
                    f"R{self.state.round_number}",
                    center_y,
                )
                return
            self._draw_inline_claim_status(
                rect,
                "CLAIM",
                "NO CLAIM",
                f"R{self.state.round_number}",
                center_y,
            )
            return
        claimant = self.state.players[self.state.current_claimant_index]
        claim_label = self.state.current_claim.display_text.upper()
        self._draw_inline_claim_status(
            rect,
            "CLAIM",
            f"{claimant.name.upper()} | {claim_label}",
            f"{self.state.current_claim.card_count} CARD",
            center_y,
        )

    def _draw_inline_claim_status(
        self,
        rect: pygame.Rect,
        label: str,
        main_text: str,
        trailing_text: str,
        center_y: int,
    ) -> None:
        body_font = self.fonts["hud_body"]
        small_font = self.fonts["hud_small"]
        self._blit_shadow_text(
            small_font,
            label,
            self.colors["muted"],
            (rect.x, center_y),
            anchor="midleft",
        )
        label_width = small_font.size(label)[0]
        trailing_width = small_font.size(trailing_text)[0]
        main_font = self._font_for_width(
            main_text,
            (body_font, small_font, self.fonts["tiny"]),
            rect.width - label_width - trailing_width - 42,
        )
        main_rect = self._blit_shadow_text(
            main_font,
            main_text,
            self.colors["text"],
            (rect.x + label_width + 12, center_y),
            anchor="midleft",
        )
        self._blit_shadow_text(
            small_font,
            trailing_text,
            self.colors["gold"],
            (main_rect.right + 16, center_y),
            anchor="midleft",
        )
        pygame.draw.line(
            self.screen,
            (203, 171, 98),
            (rect.x, rect.y + 52),
            (min(rect.right, main_rect.right + 16 + trailing_width), rect.y + 52),
            1,
        )

    def _draw_action_hud(self, rect: pygame.Rect) -> None:
        if self.state is None:
            return
        player = self.engine.current_player()
        if self.engine.is_match_over():
            lines = [("Continue", "ENTER")]
            title = "DONE"
        elif self._human_can_interrupt_with_challenge():
            title = "CALL"
            lines = [
                ("LIAR", "X"),
            ]
        elif not player.is_human:
            title = "WAIT"
            lines = [("Watch", "")]
        else:
            if self.state.current_claim is not None:
                title = "CALL"
                lines = [
                    ("LIAR", "X"),
                    ("Card", "SPACE"),
                    ("Raise", "C"),
                    ("Rank", "Q/E"),
                ]
            else:
                title = "TURN"
                lines = [
                    ("Card", "SPACE"),
                    ("Throw", "C"),
                    ("Rank", "Q/E"),
                ]
        panel_rect = pygame.Rect(rect.right - rect.width, rect.y, rect.width, 52 + len(lines) * 32)
        self._blit_shadow_text(
            self.fonts["hud_body"],
            title,
            self.colors["text"],
            (panel_rect.right, panel_rect.y + 6),
            anchor="topright",
        )
        pygame.draw.line(
            self.screen,
            (203, 171, 98),
            (panel_rect.right - 144, panel_rect.y + 38),
            (panel_rect.right, panel_rect.y + 38),
            1,
        )
        row_y = panel_rect.y + 62
        for label, key in lines:
            if key:
                key_rect = self._draw_keycap(key, (panel_rect.right, row_y), anchor="midright")
                label_right = key_rect.x - 16
            else:
                label_right = panel_rect.right
            label_font = self._font_for_width(
                label,
                (self.fonts["hud_body"], self.fonts["hud_small"], self.fonts["tiny"]),
                max(40, label_right - panel_rect.x - 12),
            )
            self._blit_shadow_text(
                label_font,
                label,
                self.colors["text"],
                (label_right, row_y),
                anchor="midright",
            )
            row_y += 31

    def _draw_status_toast(self) -> None:
        if (
            self.state is None
            or not self.status_message
            or self.engine.is_match_over()
            or self._presentation_active()
        ):
            return
        text = self.status_message.upper()
        font = self.fonts["hud_body"]
        max_width = 590
        lines = self._wrap_line(text, font, max_width - 44)
        line_height = font.get_linesize()
        height = max(58, 28 + line_height * len(lines))
        rect = pygame.Rect(0, 0, max_width, height)
        rect.center = (SCREEN_WIDTH // 2, 512)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (18, 13, 10, 218), panel.get_rect(), border_radius=12)
        self.screen.blit(panel, rect.topleft)
        pygame.draw.line(
            self.screen,
            (222, 164, 84),
            (rect.x + 26, rect.y + 9),
            (rect.right - 26, rect.y + 9),
            1,
        )
        pygame.draw.line(
            self.screen,
            (154, 110, 58),
            (rect.x + 26, rect.bottom - 9),
            (rect.right - 26, rect.bottom - 9),
            1,
        )
        y = rect.y + 15
        for line in lines:
            surface = font.render(line, True, self.colors["cream"])
            self.screen.blit(surface, surface.get_rect(center=(rect.centerx, y + surface.get_height() // 2)))
            y += line_height

    def _draw_table_surface(self, table_rect: pygame.Rect, now: int) -> None:
        table_image = self.assets.transparent_image(
            "table",
            (table_rect.width + 110, table_rect.height + 80),
        )
        if table_image is not None:
            table_pos = table_image.get_rect(center=table_rect.center)
            self.screen.blit(table_image, table_pos)
            center_ring = pygame.Rect(table_rect.centerx - 190, table_rect.centery - 86, 380, 172)
            pygame.draw.ellipse(self.screen, (176, 210, 172), center_ring, 4)
            inner_glow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pulse = 14 + int(8 * (1 + pygame.math.Vector2(0, 1).rotate(now * 0.03).y))
            pygame.draw.ellipse(
                inner_glow,
                (181, 220, 176, 14),
                center_ring.inflate(pulse * 2, pulse),
            )
            self.screen.blit(inner_glow, (0, 0))
            return

        shadow = table_rect.move(0, 26)
        pygame.draw.ellipse(self.screen, (13, 9, 8, 108), shadow)
        outer = table_rect.inflate(26, 26)
        pygame.draw.ellipse(self.screen, (56, 31, 25), outer)
        pygame.draw.ellipse(self.screen, (148, 110, 74), outer.inflate(-22, -22), 6)
        pygame.draw.ellipse(self.screen, (99, 52, 42), table_rect)
        pygame.draw.ellipse(self.screen, (129, 84, 62), table_rect.inflate(-32, -34), 4)
        rx = table_rect.width / 2 - 22
        ry = table_rect.height / 2 - 22
        for offset in range(-220, 250, 62):
            ratio = 1 - (offset / ry) ** 2
            if ratio <= 0:
                continue
            width = int(rx * math.sqrt(ratio))
            y = int(table_rect.centery + offset)
            pygame.draw.line(
                self.screen,
                (76, 42, 34),
                (table_rect.centerx - width, y),
                (table_rect.centerx + width, y),
                3,
            )
        center_ring = pygame.Rect(table_rect.centerx - 190, table_rect.centery - 86, 380, 172)
        pygame.draw.ellipse(self.screen, (176, 210, 172), center_ring, 5)
        inner_glow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        pulse = 14 + int(8 * (1 + pygame.math.Vector2(0, 1).rotate(now * 0.03).y))
        pygame.draw.ellipse(
            inner_glow,
            (181, 220, 176, 16),
            center_ring.inflate(pulse * 2, pulse),
            0,
        )
        pygame.draw.ellipse(
            inner_glow,
            (214, 160, 108, 10),
            pygame.Rect(table_rect.centerx - 260, table_rect.bottom - 142, 520, 110),
            0,
        )
        pygame.draw.ellipse(
            inner_glow,
            (255, 248, 232, 8),
            pygame.Rect(table_rect.centerx - 320, table_rect.y + 16, 520, 82),
            0,
        )
        pygame.draw.ellipse(
            inner_glow,
            (0, 0, 0, 36),
            pygame.Rect(table_rect.x + 148, table_rect.y + 32, 640, 256),
            0,
        )
        self.screen.blit(inner_glow, (0, 0))

    def _draw_dealer_banner(self, rect: pygame.Rect) -> None:
        if self.state is None:
            return
        text = self.state.narration_log[-1].text if self.state.narration_log else "Silence."
        quote_font = self.fonts["dealer"] if self.fonts["dealer"].size(text)[0] <= rect.width else self.fonts["tiny"]
        self._blit_shadow_text(
            quote_font,
            text,
            self.colors["text"],
            rect.center,
            anchor="center",
        )

    def _draw_center_claim(self, table_rect: pygame.Rect, now: int) -> None:
        if self.state is None:
            return
        center_x = table_rect.centerx
        center_y = table_rect.centery + 6
        stack_size = max(1, len(self.state.claim_stack))
        for index in range(min(stack_size, 4)):
            rect = pygame.Rect(
                center_x - 54 + index * 6,
                center_y - 36 - index * 4,
                88,
                124,
            )
            self._draw_card_back(
                rect,
                highlighted=index == min(stack_size, 4) - 1,
                angle=-8 + index * 4,
            )

    def _draw_seats(self, positions: dict[int, tuple[int, int]], now: int) -> None:
        if self.state is None:
            return
        for player in self.state.players:
            x, y = positions.get(player.seat_index, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            if not player.is_human:
                self._draw_opponent_presence(player, x, y, now)

    def _draw_reputation_plates(
        self,
        positions: dict[int, tuple[int, int]],
        now: int,
    ) -> None:
        if self.state is None:
            return
        del now
        for player in self.state.players:
            if player.is_human or player.eliminated:
                continue
            center = self._reputation_plate_center(player, positions)
            self._draw_reputation_plate(player, center)

    def _reputation_plate_center(
        self,
        player: PlayerState,
        positions: dict[int, tuple[int, int]],
    ) -> tuple[int, int]:
        layout = self._character_image_layout(player.seat_index)
        if layout is not None:
            size, midbottom, _ = layout
            if player.profile_key == "fox":
                midbottom = (midbottom[0], midbottom[1] - 60)
            top = midbottom[1] - size[1]
            if player.seat_index == 4:
                return (midbottom[0], max(58, top - 20))
            return (midbottom[0], max(58, top - 24))
        x, y = positions.get(player.seat_index, (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        return (x, y - 126)

    def _draw_reputation_plate(
        self,
        player: PlayerState,
        center: tuple[int, int],
    ) -> None:
        if self.state is None:
            return
        active = self.state.current_turn_index == player.seat_index
        claimant = self.state.current_claimant_index == player.seat_index
        highlighted = self._presentation_targets_player(player)
        width = 176
        height = 66
        rect = pygame.Rect(0, 0, width, height)
        rect.center = center
        if active or claimant or highlighted:
            pygame.draw.line(
                self.screen,
                (235, 181, 80),
                (rect.x + 8, rect.y + 2),
                (rect.right - 8, rect.y + 2),
                2,
            )
        self._blit_hud_text(
            self.fonts["hud_small"],
            "REPUTATION",
            (rect.x + 8, rect.y + 17),
            anchor="midleft",
            color=(255, 236, 190),
        )
        self._blit_hud_text(
            self.fonts["hud_small"],
            str(player.reputation),
            (rect.right - 8, rect.y + 17),
            anchor="midright",
            color=(255, 236, 190),
        )
        rep_rect = pygame.Rect(rect.x + 8, rect.y + 30, rect.width - 16, 6)
        fill_width = max(3, int(rep_rect.width * (player.reputation / 100)))
        pygame.draw.rect(
            self.screen,
            (70, 42, 20),
            rep_rect,
            border_radius=3,
        )
        pygame.draw.rect(self.screen, (128, 86, 39), rep_rect, 1, border_radius=3)
        pygame.draw.rect(
            self.screen,
            (230, 178, 78),
            pygame.Rect(rep_rect.x + 1, rep_rect.y + 1, max(2, fill_width - 2), rep_rect.height - 2),
            border_radius=2,
        )
        self._draw_revolver_counter(player, (rect.x + 8, rect.y + 52), color=(255, 236, 190))

    def _presentation_targets_player(self, player: PlayerState) -> bool:
        event = self.presentation_event
        return event is not None and event.target_name == player.name

    def _player_by_name(self, name: str | None) -> PlayerState | None:
        if self.state is None or name is None:
            return None
        for player in self.state.players:
            if player.name == name:
                return player
        return None

    def _revolver_status_text(self, player: PlayerState) -> str:
        spent = len(player.revolver.spent_indices)
        total = max(1, len(player.revolver.chambers))
        return f"{spent}/{total}"

    def _draw_revolver_counter(
        self,
        player: PlayerState,
        pos: tuple[int, int],
        *,
        color: tuple[int, int, int] | None = None,
    ) -> pygame.Rect:
        x, y = pos
        text_color = color or (255, 236, 190)
        icon_center = (x + 10, y)
        self._draw_chamber_status_icon(icon_center)
        status_rect = self._blit_hud_text(
            self.fonts["hud_small"],
            self._revolver_status_text(player),
            (x + 25, y + 1),
            anchor="midleft",
            color=text_color,
        )
        return pygame.Rect(x, y - 10, 25 + status_rect.width, 20)

    def _draw_chamber_status_icon(self, center: tuple[int, int]) -> None:
        pygame.draw.circle(self.screen, (68, 38, 18), center, 10)
        pygame.draw.circle(self.screen, (226, 170, 73), center, 10, 2)
        pygame.draw.circle(self.screen, (255, 224, 150), center, 6, 1)
        for index in range(6):
            theta = -math.pi / 2 + math.tau * index / 6
            dot = (
                int(center[0] + math.cos(theta) * 5),
                int(center[1] + math.sin(theta) * 5),
            )
            pygame.draw.circle(self.screen, (255, 224, 150), dot, 2)

    def _draw_revolver_status_chip(self, player: PlayerState, rect: pygame.Rect) -> None:
        self._draw_revolver_counter(player, (rect.x + 12, rect.centery), color=(255, 236, 190))

    def _draw_human_revolver_status(self) -> None:
        if self.state is None:
            return
        human = self.state.players[0]
        if human.eliminated:
            return
        rect = pygame.Rect(28, 86, 138, 30)
        self._draw_revolver_status_chip(human, rect)

    def _draw_human_hand(self, panel_rect: pygame.Rect, mouse_pos: tuple[int, int]) -> None:
        if self.state is None:
            return
        player = self.state.players[0]
        self._draw_hand_tray(panel_rect)
        self.hand_targets = []
        if player.hand_size == 0:
            empty = self.fonts["body"].render("No cards left in hand.", True, self.colors["muted"])
            self.screen.blit(empty, empty.get_rect(center=(panel_rect.centerx, panel_rect.y + 70)))
            return
        fan_center_x = 640
        fan_center_y = 648
        spacing = 82
        card_width = 116
        card_height = 174
        mid_index = (player.hand_size - 1) / 2
        card_layouts: list[tuple[int, Card, pygame.Rect, float, bool]] = []
        for index, card in enumerate(player.hand):
            is_selected = index in self.selected_cards or index == self.selected_special_index
            angle = (index - mid_index) * -5
            base_x = fan_center_x + int((index - mid_index) * spacing)
            base_y = fan_center_y + int(abs(index - mid_index) * 6) - (18 if is_selected else 0)
            rect = pygame.Rect(
                base_x - card_width // 2,
                base_y - card_height // 2,
                card_width,
                card_height,
            )
            card_layouts.append((index, card, rect, angle, is_selected))
        hover_index = self._closest_card_index(
            mouse_pos,
            [(rect, index) for index, _, rect, _, _ in card_layouts],
        )
        focus_index = self.selected_special_index if self.selected_special_index is not None else hover_index
        if focus_index is not None and 0 <= focus_index < player.hand_size:
            focus_card = player.hand[focus_index]
            if focus_card.is_special:
                self._draw_special_focus_plaque(panel_rect, focus_card)
        draw_order = sorted(
            card_layouts,
            key=lambda item: (item[4] or item[0] == hover_index, item[0]),
        )
        for index, card, rect, angle, is_selected in draw_order:
            final_rect, final_mask = self._draw_player_card(
                card,
                rect,
                is_selected,
                index == hover_index,
                angle=angle,
            )
            self.hand_targets.append((final_rect, index, final_mask))

    def _draw_hand_tray(self, panel_rect: pygame.Rect) -> None:
        tray_rect = pygame.Rect(0, 0, 620, 164)
        tray_rect.midtop = (panel_rect.centerx, panel_rect.y + 38)
        shadow = pygame.Surface(tray_rect.size, pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 72), shadow.get_rect())
        self.screen.blit(shadow, tray_rect.topleft)
        rail = pygame.Rect(tray_rect.x + 38, tray_rect.bottom - 38, tray_rect.width - 76, 24)
        rail_surface = pygame.Surface(rail.size, pygame.SRCALPHA)
        pygame.draw.rect(rail_surface, (49, 24, 13, 154), rail_surface.get_rect(), border_radius=12)
        pygame.draw.rect(rail_surface, (151, 91, 39, 150), rail_surface.get_rect(), 1, 12)
        self.screen.blit(rail_surface, rail.topleft)

    def _draw_special_focus_plaque(self, panel_rect: pygame.Rect, card: Card) -> None:
        if card.special is None:
            return
        rect = pygame.Rect(0, 0, 380, 54)
        rect.midbottom = (panel_rect.centerx, panel_rect.y - 16)
        self._draw_saloon_panel(rect, active=True, alpha=226)
        name = card.special.display_name.upper()
        detail = self._special_card_detail(card.special).upper()
        name_font = self._font_for_width(
            name,
            (self.fonts["hud_body"], self.fonts["hud_small"], self.fonts["tiny"]),
            rect.width - 34,
        )
        self._blit_shadow_text(
            name_font,
            name,
            self.colors["cream"],
            (rect.x + 16, rect.y + 8),
            anchor="topleft",
            shadow_color=(14, 7, 5),
        )
        detail_font = self._font_for_width(
            detail,
            (self.fonts["hud_small"], self.fonts["tiny"]),
            rect.width - 34,
        )
        self._blit_shadow_text(
            detail_font,
            detail,
            self.colors["gold"],
            (rect.x + 16, rect.y + 30),
            anchor="topleft",
            shadow_color=(14, 7, 5),
        )

    def _closest_card_index(
        self,
        pos: tuple[int, int],
        targets: list[tuple[pygame.Rect, int]],
    ) -> int | None:
        candidates = [
            (rect, index)
            for rect, index in targets
            if rect.inflate(8, 8).collidepoint(pos)
        ]
        if not candidates:
            return None
        x, y = pos
        _, index = min(
            candidates,
            key=lambda item: (
                (item[0].centerx - x) ** 2 + (item[0].centery - y) ** 2,
                -item[1],
            ),
        )
        return index

    def _draw_player_status(self, player: PlayerState, x: int, y: int, now: int) -> None:
        if self.state is None:
            return
        active = self.state.current_turn_index == player.seat_index
        outer = pygame.Rect(x - 86, y - 24, 172, 46)
        panel = pygame.Surface(outer.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, self.colors["panel"], panel.get_rect(), border_radius=18)
        pygame.draw.rect(panel, self.colors["gold"] if active else (*self.colors["border"], 185), panel.get_rect(), 2, 18)
        self.screen.blit(panel, outer.topleft)
        title_surface = self.fonts["body_bold"].render(player.name, True, self.colors["text"])
        self.screen.blit(title_surface, (outer.x + 18, outer.y + 8))
        rep_width = 76
        pygame.draw.rect(self.screen, (34, 36, 40), (outer.x + 18, outer.y + 28, rep_width, 8), border_radius=4)
        fill = int(rep_width * (player.reputation / 100))
        pygame.draw.rect(
            self.screen,
            self._reputation_color(player.reputation_band),
            (outer.x + 18, outer.y + 28, fill, 8),
            border_radius=4,
        )
        if active:
            self._draw_tag("TURN", (outer.x + 98, outer.y - 14), self.colors["gold"])

    def _draw_opponent_presence(self, player: PlayerState, x: int, y: int, now: int) -> None:
        if self.state is None:
            return
        active = self.state.current_turn_index == player.seat_index
        claimant = self.state.current_claimant_index == player.seat_index
        if self._draw_character_image(player, active, claimant):
            return

        profile_key = player.profile_key or ""
        if profile_key == "mr_fold" or player.seat_index == 3:
            self._draw_bull_character(x, y, active, claimant, player.hand_size)
        elif profile_key in {"ash", "vesper"} or player.seat_index in {2, 4}:
            self._draw_wolf_character(x, y, active, claimant, player.hand_size)
        elif profile_key == "dante" or player.seat_index == 1:
            self._draw_pig_character(x, y, active, claimant, player.hand_size)
        else:
            self._draw_fox_character(x, y, active, claimant, player.hand_size)

    def _draw_character_image(
        self,
        player: PlayerState,
        active: bool,
        claimant: bool,
    ) -> bool:
        layout = self._character_image_layout(player.seat_index)
        if layout is None:
            return False
        size, midbottom, flip = layout
        image = self.assets.character(player.profile_key, size)
        if image is None:
            return False

        if player.profile_key == "fox":
            midbottom = (midbottom[0], midbottom[1] - 60)
        if flip:
            image = pygame.transform.flip(image, True, False)
        if player.eliminated:
            image = image.copy()
            image.set_alpha(82)
        targeted = self._presentation_targets_player(player)

        rect = image.get_rect(midbottom=midbottom)
        shadow = pygame.Surface((rect.width, 64), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 52), shadow.get_rect())
        self.screen.blit(shadow, shadow.get_rect(midbottom=(rect.centerx, rect.bottom + 12)))
        self._draw_halo(
            (rect.centerx, rect.y + rect.height // 3),
            rect.width // 3,
            active or claimant or targeted,
        )
        if targeted:
            glow = pygame.Surface((rect.width + 34, rect.height + 34), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (232, 78, 55, 34), glow.get_rect())
            self.screen.blit(glow, glow.get_rect(center=rect.center))
        self.screen.blit(image, rect.topleft)
        return True

    def _character_image_layout(
        self,
        seat_index: int,
    ) -> tuple[tuple[int, int], tuple[int, int], bool] | None:
        layouts = {
            1: ((330, 420), (190, 625), True),
            2: ((260, 332), (486, 538), False),
            3: ((350, 430), (790, 520), False),
            4: ((266, 354), (1060, 622), False),
        }
        return layouts.get(seat_index)

    def _draw_pig_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (39, 21, 18)
        fur = (206, 143, 116)
        fur_light = (232, 184, 154)
        fur_shadow = (122, 70, 58)
        shirt = (214, 208, 196)
        shirt_shadow = (176, 166, 152)
        shadow = pygame.Surface((300, 300), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 34), shadow.get_rect())
        self.screen.blit(shadow, (x - 150, y + 10))
        body = pygame.Rect(x - 124, y + 88, 176, 132)
        shoulders = [
            (x - 112, y + 198),
            (x - 102, y + 120),
            (x - 60, y + 90),
            (x - 8, y + 88),
            (x + 30, y + 106),
            (x + 46, y + 198),
        ]
        self._draw_halo((x + 8, y + 18), 52, active)
        pygame.draw.ellipse(self.screen, fur, body)
        pygame.draw.polygon(self.screen, fur, shoulders)
        tank = [(x - 104, y + 192), (x - 78, y + 104), (x - 22, y + 96), (x + 38, y + 196)]
        pygame.draw.polygon(self.screen, shirt, tank)
        pygame.draw.polygon(
            self.screen,
            shirt_shadow,
            [(x - 36, y + 132), (x - 14, y + 100), (x + 6, y + 104), (x - 14, y + 154)],
        )
        self._blit_soft_ellipse(pygame.Rect(body.x + 18, body.y + 12, 72, 50), (255, 230, 206, 34))
        self._blit_soft_ellipse(pygame.Rect(body.x + 48, body.y + 70, 88, 42), (94, 52, 44, 24))
        neck = [(x - 18, y + 88), (x + 18, y + 88), (x + 28, y + 112), (x - 28, y + 112)]
        pygame.draw.polygon(self.screen, fur, neck)
        pygame.draw.arc(self.screen, outline, body, 0.34, math.pi - 0.34, 3)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 3)
        pygame.draw.lines(
            self.screen,
            outline,
            False,
            [shoulders[3], shoulders[4], shoulders[5], shoulders[0]],
            3,
        )
        pygame.draw.polygon(self.screen, outline, tank, 3)
        head = pygame.Rect(x - 30, y + 12, 94, 88)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 12, head.y + 10, 48, 24), (255, 224, 196, 30))
        self._blit_soft_ellipse(pygame.Rect(head.x + 20, head.y + 36, 58, 36), (118, 70, 58, 28))
        self._blit_soft_ellipse(pygame.Rect(head.x + 14, head.y + 56, 62, 18), (246, 214, 190, 20))
        ear_left = [(x - 16, y + 26), (x + 2, y - 6), (x + 16, y + 30)]
        ear_right = [(x + 14, y + 24), (x + 34, y - 2), (x + 48, y + 32)]
        pygame.draw.polygon(self.screen, fur, ear_left)
        pygame.draw.polygon(self.screen, fur, ear_right)
        pygame.draw.polygon(self.screen, fur_light, [(x - 8, y + 72), (x + 20, y + 62), (x + 46, y + 72), (x + 24, y + 84)])
        snout = pygame.Rect(x + 2, y + 48, 44, 26)
        pygame.draw.ellipse(self.screen, (236, 183, 160), snout)
        pygame.draw.circle(self.screen, (154, 86, 79), (x + 18, y + 60), 3)
        pygame.draw.circle(self.screen, (154, 86, 79), (x + 30, y + 60), 3)
        pygame.draw.ellipse(self.screen, (242, 241, 236), pygame.Rect(x - 6, y + 36, 13, 10))
        pygame.draw.ellipse(self.screen, (242, 241, 236), pygame.Rect(x + 19, y + 36, 13, 10))
        pygame.draw.circle(self.screen, outline, (x + 1, y + 41), 3)
        pygame.draw.circle(self.screen, outline, (x + 26, y + 41), 3)
        pygame.draw.arc(self.screen, outline, pygame.Rect(x + 14, y + 68, 14, 8), 0.3, 2.85, 2)
        pygame.draw.arc(self.screen, fur_shadow, pygame.Rect(x - 2, y + 32, 18, 12), 3.6, 5.8, 2)
        pygame.draw.arc(self.screen, fur_shadow, pygame.Rect(x + 20, y + 32, 18, 12), 3.6, 5.8, 2)
        arm = [(x - 10, y + 136), (x + 56, y + 146), (x + 138, y + 154), (x + 132, y + 184), (x + 46, y + 176), (x - 14, y + 160)]
        pygame.draw.polygon(self.screen, fur, arm)
        hand = pygame.Rect(x + 126, y + 148, 32, 22)
        pygame.draw.ellipse(self.screen, fur, hand)
        self._draw_card_fan((x + 164, y + 148), min(hand_size, 4), 18, 50, False, claimant)
        pygame.draw.ellipse(self.screen, outline, head, 3)
        pygame.draw.polygon(self.screen, outline, ear_left, 3)
        pygame.draw.polygon(self.screen, outline, ear_right, 3)
        pygame.draw.ellipse(self.screen, outline, snout, 2)

    def _draw_wolf_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (26, 29, 31)
        fur = (122, 128, 136)
        fur_dark = (76, 82, 92)
        shirt = (214, 214, 210)
        suit = (76, 92, 78)
        self._draw_halo((x - 10, y - 54), 58, active)
        body = pygame.Rect(x - 88, y + 34, 176, 132)
        shoulders = [
            (x - 82, y + 142),
            (x - 66, y + 68),
            (x - 28, y + 38),
            (x + 28, y + 38),
            (x + 68, y + 70),
            (x + 84, y + 142),
        ]
        pygame.draw.ellipse(self.screen, suit, body)
        pygame.draw.polygon(self.screen, suit, shoulders)
        self._blit_soft_ellipse(pygame.Rect(body.x + 20, body.y + 10, 70, 42), (214, 224, 218, 20))
        self._blit_soft_ellipse(pygame.Rect(body.x + 36, body.y + 56, 112, 58), (18, 20, 24, 30))
        chest = [(x - 34, y + 126), (x - 18, y + 42), (x + 18, y + 42), (x + 34, y + 126)]
        pygame.draw.polygon(self.screen, shirt, chest)
        tie = [(x - 6, y + 46), (x + 6, y + 46), (x + 12, y + 100), (x - 12, y + 100)]
        pygame.draw.polygon(self.screen, (129, 34, 34), tie)
        head = pygame.Rect(x - 50, y - 74, 100, 112)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 14, head.y + 8, 54, 42), (236, 242, 245, 34))
        self._blit_soft_ellipse(pygame.Rect(head.x + 26, head.y + 46, 52, 40), (32, 36, 42, 34))
        ear_left = [(x - 34, y - 56), (x - 18, y - 96), (x + 2, y - 44)]
        ear_right = [(x + 18, y - 44), (x + 34, y - 96), (x + 52, y - 56)]
        pygame.draw.polygon(self.screen, fur_dark, ear_left)
        pygame.draw.polygon(self.screen, fur_dark, ear_right)
        muzzle = [(x - 20, y - 6), (x + 22, y - 2), (x + 12, y + 28), (x - 10, y + 26)]
        pygame.draw.polygon(self.screen, (198, 203, 208), muzzle)
        pygame.draw.circle(self.screen, (240, 240, 236), (x - 16, y - 18), 8)
        pygame.draw.circle(self.screen, (240, 240, 236), (x + 18, y - 18), 8)
        pygame.draw.circle(self.screen, outline, (x - 14, y - 18), 4)
        pygame.draw.circle(self.screen, outline, (x + 16, y - 18), 4)
        pygame.draw.polygon(self.screen, outline, [(x + 4, y + 2), (x + 16, y + 8), (x + 8, y + 18)])
        arm = [(x + 18, y + 96), (x + 72, y + 118), (x + 92, y + 144), (x + 68, y + 152), (x + 6, y + 118)]
        pygame.draw.polygon(self.screen, fur, arm)
        self._draw_card_fan((x + 98, y + 132), min(hand_size, 3), 18, 18, False, claimant)
        pygame.draw.ellipse(self.screen, outline, body, 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[3], shoulders[4], shoulders[5], shoulders[0]], 4)
        pygame.draw.polygon(self.screen, outline, chest, 3)
        pygame.draw.ellipse(self.screen, outline, head, 4)
        pygame.draw.polygon(self.screen, outline, ear_left, 4)
        pygame.draw.polygon(self.screen, outline, ear_right, 4)
        pygame.draw.polygon(self.screen, outline, muzzle, 3)

    def _draw_bull_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (38, 22, 16)
        fur = (151, 99, 61)
        muzzle = (194, 150, 113)
        shirt = (73, 76, 82)
        horn = (228, 210, 188)
        self._draw_halo((x, y - 56), 92, active or claimant)
        body = pygame.Rect(x - 128, y + 30, 256, 160)
        shoulders = [
            (x - 122, y + 148),
            (x - 92, y + 66),
            (x - 42, y + 28),
            (x + 42, y + 28),
            (x + 92, y + 66),
            (x + 124, y + 148),
        ]
        pygame.draw.ellipse(self.screen, shirt, body)
        pygame.draw.polygon(self.screen, shirt, shoulders)
        self._blit_soft_ellipse(pygame.Rect(body.x + 36, body.y + 10, 96, 48), (214, 220, 228, 18))
        self._blit_soft_ellipse(pygame.Rect(body.x + 70, body.y + 72, 142, 60), (18, 20, 24, 34))
        head = pygame.Rect(x - 86, y - 104, 172, 164)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 28, head.y + 14, 78, 48), (255, 230, 198, 30))
        self._blit_soft_ellipse(pygame.Rect(head.x + 60, head.y + 66, 84, 52), (82, 50, 36, 32))
        pygame.draw.polygon(self.screen, horn, [(x - 66, y - 62), (x - 118, y - 102), (x - 82, y - 54)])
        pygame.draw.polygon(self.screen, horn, [(x + 66, y - 62), (x + 118, y - 102), (x + 82, y - 54)])
        muzzle_rect = pygame.Rect(x - 44, y - 6, 88, 56)
        pygame.draw.ellipse(self.screen, muzzle, muzzle_rect)
        pygame.draw.circle(self.screen, (86, 56, 42), (x - 16, y + 20), 7)
        pygame.draw.circle(self.screen, (86, 56, 42), (x + 16, y + 20), 7)
        pygame.draw.circle(self.screen, (244, 244, 240), (x - 34, y - 18), 11)
        pygame.draw.circle(self.screen, (244, 244, 240), (x + 34, y - 18), 11)
        pygame.draw.circle(self.screen, outline, (x - 32, y - 18), 5)
        pygame.draw.circle(self.screen, outline, (x + 32, y - 18), 5)
        pygame.draw.arc(self.screen, (204, 183, 120), pygame.Rect(x - 16, y + 20, 32, 24), 0.15, 3.0, 4)
        arm_left = [(x - 70, y + 108), (x - 126, y + 152), (x - 138, y + 198), (x - 108, y + 198), (x - 58, y + 148)]
        arm_right = [(x + 70, y + 108), (x + 126, y + 150), (x + 148, y + 194), (x + 118, y + 198), (x + 58, y + 148)]
        pygame.draw.polygon(self.screen, fur, arm_left)
        pygame.draw.polygon(self.screen, fur, arm_right)
        pygame.draw.ellipse(self.screen, fur, pygame.Rect(x - 142, y + 188, 36, 24))
        pygame.draw.ellipse(self.screen, fur, pygame.Rect(x + 118, y + 184, 36, 26))
        self._draw_card_fan((x + 170, y + 172), min(hand_size, 4), 16, -16, True, claimant)
        pygame.draw.ellipse(self.screen, outline, body, 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 4)
        pygame.draw.lines(self.screen, outline, False, [shoulders[3], shoulders[4], shoulders[5], shoulders[0]], 4)
        pygame.draw.ellipse(self.screen, outline, head, 4)
        pygame.draw.polygon(self.screen, outline, arm_left, 4)
        pygame.draw.polygon(self.screen, outline, arm_right, 4)
        pygame.draw.ellipse(self.screen, outline, muzzle_rect, 3)

    def _draw_fox_character(
        self,
        x: int,
        y: int,
        active: bool,
        claimant: bool,
        hand_size: int,
    ) -> None:
        outline = (43, 22, 18)
        fur = (196, 116, 72)
        fur_dark = (118, 62, 46)
        fur_light = (234, 196, 162)
        top = (62, 27, 31)
        self._draw_halo((x - 18, y + 10), 56, active)
        body = pygame.Rect(x - 94, y + 88, 174, 128)
        shoulders = [
            (x - 90, y + 194),
            (x - 76, y + 120),
            (x - 36, y + 90),
            (x + 12, y + 88),
            (x + 54, y + 104),
            (x + 74, y + 194),
        ]
        pygame.draw.ellipse(self.screen, fur, body)
        pygame.draw.polygon(self.screen, fur, shoulders)
        blouse = [(x - 44, y + 192), (x - 8, y + 100), (x + 42, y + 94), (x + 76, y + 194)]
        pygame.draw.polygon(self.screen, top, blouse)
        self._blit_soft_ellipse(pygame.Rect(body.x + 18, body.y + 12, 68, 38), (248, 214, 182, 24))
        self._blit_soft_ellipse(pygame.Rect(body.x + 44, body.y + 64, 86, 46), (74, 34, 30, 32))
        neck = [(x - 18, y + 88), (x + 18, y + 88), (x + 30, y + 110), (x - 26, y + 112)]
        pygame.draw.polygon(self.screen, fur, neck)
        pygame.draw.arc(self.screen, outline, body, 0.32, math.pi - 0.32, 3)
        pygame.draw.lines(self.screen, outline, False, [shoulders[0], shoulders[1], shoulders[2]], 3)
        pygame.draw.lines(
            self.screen,
            outline,
            False,
            [shoulders[3], shoulders[4], shoulders[5], shoulders[0]],
            3,
        )
        pygame.draw.polygon(self.screen, outline, blouse, 3)
        head = pygame.Rect(x - 36, y + 22, 88, 80)
        pygame.draw.ellipse(self.screen, fur, head)
        self._blit_soft_ellipse(pygame.Rect(head.x + 10, head.y + 8, 42, 18), (255, 230, 194, 26))
        self._blit_soft_ellipse(pygame.Rect(head.x + 22, head.y + 32, 42, 26), (108, 58, 44, 26))
        ear_left = [(x - 24, y + 32), (x - 8, y - 2), (x + 8, y + 34)]
        ear_right = [(x + 4, y + 34), (x + 24, y + 2), (x + 38, y + 38)]
        pygame.draw.polygon(self.screen, fur, ear_left)
        pygame.draw.polygon(self.screen, fur, ear_right)
        cheek = [(x - 18, y + 70), (x - 8, y + 50), (x + 8, y + 46), (x + 26, y + 52), (x + 28, y + 70), (x + 4, y + 82)]
        pygame.draw.polygon(self.screen, fur_light, cheek)
        muzzle = [(x - 8, y + 56), (x + 14, y + 54), (x + 22, y + 64), (x + 2, y + 74), (x - 10, y + 66)]
        pygame.draw.polygon(self.screen, fur_light, muzzle)
        pygame.draw.ellipse(self.screen, (244, 243, 238), pygame.Rect(x - 22, y + 40, 14, 8))
        pygame.draw.ellipse(self.screen, (244, 243, 238), pygame.Rect(x + 2, y + 40, 14, 8))
        pygame.draw.circle(self.screen, outline, (x - 14, y + 44), 3)
        pygame.draw.circle(self.screen, outline, (x + 10, y + 44), 3)
        pygame.draw.arc(self.screen, fur_dark, pygame.Rect(x - 24, y + 34, 20, 12), 3.7, 5.8, 2)
        pygame.draw.arc(self.screen, fur_dark, pygame.Rect(x, y + 34, 20, 12), 3.7, 5.8, 2)
        pygame.draw.polygon(self.screen, fur_dark, [(x + 2, y + 58), (x + 8, y + 64), (x + 2, y + 70)])
        pygame.draw.arc(self.screen, outline, pygame.Rect(x - 4, y + 68, 14, 7), 0.25, 2.85, 2)
        arm = [(x - 14, y + 136), (x - 84, y + 146), (x - 148, y + 142), (x - 144, y + 170), (x - 58, y + 168), (x - 6, y + 154)]
        pygame.draw.polygon(self.screen, fur, arm)
        hand = pygame.Rect(x - 148, y + 144, 30, 20)
        pygame.draw.ellipse(self.screen, fur_light, hand)
        necklace_y = y + 104
        pygame.draw.line(self.screen, (214, 193, 150), (x - 14, necklace_y), (x + 34, necklace_y), 2)
        pygame.draw.circle(self.screen, (214, 193, 150), (x + 10, necklace_y + 7), 4)
        self._draw_card_fan((x - 162, y + 144), min(hand_size, 4), 16, -50, True, claimant)
        pygame.draw.ellipse(self.screen, outline, head, 3)
        pygame.draw.polygon(self.screen, outline, ear_left, 3)
        pygame.draw.polygon(self.screen, outline, ear_right, 3)
        pygame.draw.polygon(self.screen, outline, cheek, 2)
        pygame.draw.polygon(self.screen, outline, muzzle, 2)

    def _draw_card_fan(
        self,
        center: tuple[int, int],
        count: int,
        spread: int,
        base_angle: int,
        mirrored: bool,
        highlighted: bool,
    ) -> None:
        for index in range(count):
            offset = index - (count - 1) / 2
            rect = pygame.Rect(
                int(center[0] + offset * (spread // 1.5)),
                int(center[1] - abs(offset) * 4),
                56,
                78,
            )
            angle = base_angle + int(offset * spread)
            if mirrored:
                angle *= -1
            self._draw_card_back(rect, highlighted=highlighted and index == count - 1, angle=angle)

    def _draw_halo(self, center: tuple[int, int], radius: int, enabled: bool) -> None:
        if not enabled:
            return
        halo = pygame.Surface((radius * 3, radius * 3), pygame.SRCALPHA)
        pygame.draw.circle(halo, (241, 202, 129, 32), (halo.get_width() // 2, halo.get_height() // 2), radius)
        self.screen.blit(halo, halo.get_rect(center=center))

    def _draw_tag(self, label: str, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
        text = self.fonts["tiny"].render(label, True, (18, 20, 24))
        rect = text.get_rect()
        rect.topleft = pos
        badge = pygame.Rect(rect.x - 8, rect.y - 4, rect.width + 16, rect.height + 8)
        pygame.draw.rect(self.screen, color, badge, border_radius=10)
        self.screen.blit(text, rect)

    def _build_table_buttons(self, panel_rect: pygame.Rect, claim_buttons_top: int) -> None:
        if self.state is None or self.engine.is_match_over():
            return
        if self._human_eliminated():
            return
        player = self.engine.current_player()
        if not player.is_human:
            return
        legal_claims = self.engine.legal_claim_ranks()
        can_claim = self.engine.player_can_make_claim(player)
        if legal_claims and self.selected_claim_rank not in legal_claims:
            self.selected_claim_rank = legal_claims[0]
        self.buttons.extend(
            [
                UIButton(
                    key="claim_prev",
                    label="<",
                    rect=pygame.Rect(panel_rect.x, panel_rect.y + 6, 36, 32),
                    enabled=len(legal_claims) > 1,
                ),
                UIButton(
                    key="claim_next",
                    label=">",
                    rect=pygame.Rect(panel_rect.right - 36, panel_rect.y + 6, 36, 32),
                    enabled=len(legal_claims) > 1,
                ),
            ]
        )
        selected_special = self._selected_special_for(ActionType.CLAIM)
        claim_enabled = can_claim and self.selected_claim_rank in legal_claims
        selected_special_type = (
            player.hand[selected_special].special if selected_special is not None else None
        )
        if selected_special_type == SpecialCardType.MIRROR_DAMAGE:
            claim_enabled = False
        elif selected_special_type not in {SpecialCardType.BLINDFOLD, SpecialCardType.WILDCARD_HAND}:
            claim_enabled = claim_enabled and len(self.selected_cards) > 0
        challenge_enabled = self.state.current_claim is not None
        challenge_special = self._selected_special_for(ActionType.CHALLENGE)
        self.buttons.extend(
            [
                UIButton(
                    key="confirm_claim",
                    label="Throw Cards",
                    rect=pygame.Rect(panel_rect.x + 16, panel_rect.y + 58, panel_rect.width - 32, 34),
                    enabled=claim_enabled,
                ),
                UIButton(
                    key="challenge",
                    label="Call Liar",
                    rect=pygame.Rect(panel_rect.x + 16, panel_rect.y + 92, panel_rect.width - 32, 34),
                    enabled=challenge_enabled and (
                        self.selected_special_index is None or challenge_special is not None
                    ),
                ),
                UIButton(
                    key="reset_selection",
                    label="Clear",
                    rect=pygame.Rect(panel_rect.x + 16, panel_rect.y + 126, panel_rect.width - 32, 34),
                    enabled=True,
                ),
            ]
        )
        if selected_special_type == SpecialCardType.BLINDFOLD:
            self.buttons.extend(
                [
                    UIButton(
                        key="blindfold_minus",
                        label="-",
                        rect=pygame.Rect(panel_rect.x + 56, panel_rect.y + 156, 34, 30),
                    ),
                    UIButton(
                        key="blindfold_plus",
                        label="+",
                        rect=pygame.Rect(panel_rect.right - 90, panel_rect.y + 156, 34, 30),
                    ),
                ]
            )

    def _draw_death_overlay(self, mouse_pos: tuple[int, int]) -> None:
        self.buttons = [
            UIButton("death_retry", "Retry", pygame.Rect(524, 456, 232, 48)),
            UIButton("death_menu", "Menu", pygame.Rect(552, 520, 176, 42)),
        ]
        self.screen.fill((0, 0, 0))
        center_x = SCREEN_WIDTH // 2
        title = self.fonts["hud_title"].render("THE CHAMBER WAS LOADED", True, (224, 218, 204))
        self.screen.blit(title, title.get_rect(center=(center_x, 300)))
        detail = self.fonts["body"].render("You are out of the game.", True, (144, 136, 126))
        self.screen.blit(detail, detail.get_rect(center=(center_x, 352)))
        for button in self.buttons:
            hovered = button.rect.collidepoint(mouse_pos)
            fill = (88, 18, 18) if button.key == "death_retry" else (14, 14, 14)
            if hovered:
                fill = (118, 28, 24) if button.key == "death_retry" else (34, 32, 30)
            border = (221, 177, 86)
            pygame.draw.rect(self.screen, fill, button.rect, border_radius=10)
            pygame.draw.rect(self.screen, border, button.rect, 2, 10)
            font = self.fonts["hud_body"] if button.key == "death_retry" else self.fonts["hud_small"]
            label = font.render(button.label.upper(), True, (238, 231, 218))
            self.screen.blit(label, label.get_rect(center=button.rect.center))

    def _draw_end_overlay(self, mouse_pos: tuple[int, int]) -> None:
        if self.state is None:
            return
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 10, 12, 170))
        self.screen.blit(overlay, (0, 0))
        rect = pygame.Rect(430, 265, 580, 250)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (16, 18, 22, 232), panel.get_rect(), border_radius=30)
        pygame.draw.rect(panel, (214, 184, 123, 216), panel.get_rect(), 2, 30)
        self.screen.blit(panel, rect.topleft)
        winner = self.engine.winner()
        title = self.fonts["title"].render("Table Decided", True, self.colors["text"])
        self.screen.blit(title, title.get_rect(center=(rect.centerx, rect.y + 64)))
        if winner is not None:
            portrait = self.assets.portrait(winner.profile_key, (86, 108))
            self.screen.blit(portrait, (rect.x + 62, rect.y + 86))
            win_text = self.fonts["subtitle"].render(f"{winner.name} remains.", True, self.colors["gold"])
            self.screen.blit(win_text, win_text.get_rect(center=(rect.centerx + 54, rect.y + 120)))
        if self.state.narration_log:
            self._draw_wrapped_text(
                [self.state.narration_log[-1].text],
                pygame.Rect(rect.x + 170, rect.y + 146, 360, 40),
                self.fonts["body"],
                self.colors["muted"],
            )
        end_buttons = [
            UIButton("end_new_match", "New Match", pygame.Rect(rect.x + 88, rect.y + 192, 170, 42)),
            UIButton("end_menu", "Menu", pygame.Rect(rect.x + 322, rect.y + 192, 170, 42)),
        ]
        self.buttons.extend(end_buttons)
        for button in end_buttons:
            self._draw_button(button, mouse_pos)

    def _draw_side_panel(
        self,
        rect: pygame.Rect,
        title: str,
        lines: list[str],
    ) -> None:
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, self.colors["panel_soft"], panel.get_rect(), border_radius=24)
        pygame.draw.rect(panel, (*self.colors["border"], 205), panel.get_rect(), 2, 24)
        self.screen.blit(panel, rect.topleft)
        title_surface = self.fonts["subtitle"].render(title, True, self.colors["text"])
        self.screen.blit(title_surface, (rect.x + 20, rect.y + 18))
        self._draw_wrapped_text(
            lines,
            pygame.Rect(rect.x + 20, rect.y + 58, rect.width - 40, rect.height - 78),
            self.fonts["small"],
            self.colors["muted"],
        )

    def _ledger_lines(self) -> list[str]:
        if self.state is None:
            return []
        lines = []
        current = self.engine.current_player()
        if self.last_result:
            lines.append("Last exchange")
            lines.append(self.last_result)
            lines.append("")
        lines.append(f"Round {self.state.round_number}")
        lines.append(f"Current actor: {current.name}")
        lines.append(
            f"Current claim: {self.state.current_claim.display_text if self.state.current_claim else 'None'}"
        )
        lines.append("")
        lines.append("Recent memory")
        recent_memory = self.state.public_memory_log[-4:] or ["Nothing public yet."]
        lines.extend(recent_memory)
        return lines

    def _action_lines(self) -> list[str]:
        if self.state is None:
            return []
        player = self.engine.current_player()
        if self.engine.is_match_over():
            return ["The match is over.", "Choose what to do next."]
        if not player.is_human:
            return [f"{player.name} is reading the table.", "Wait for the move to land."]
        lines = []
        if self.status_message:
            lines.extend(["Status", self.status_message, ""])
        legal = self.engine.legal_claim_ranks()
        if self.state.current_claim is None:
            lines.extend(["You open the round.", "Any claim rank is legal."])
        else:
            lines.extend(
                [
                    f"You must beat {self.state.current_claim.display_text}.",
                    "Challenge is always available while a claim is active.",
                ]
            )
        lines.append("")
        lines.append(f"Selected cards: {len(self.selected_cards)}")
        lines.append(
            f"Selected claim: {self.selected_claim_rank.label if self.selected_claim_rank else 'None'}"
        )
        special = self._active_special_label(player)
        if special:
            lines.append(special)
        if self._selected_special_for(ActionType.CLAIM) is not None:
            selected = player.hand[self._selected_special_for(ActionType.CLAIM)].special
            if selected == SpecialCardType.BLINDFOLD:
                lines.append(f"Blindfold count: {self.blindfold_count}")
        if not legal:
            lines.append("No stronger claim exists. Challenge the stack.")
        return lines

    def _active_special_label(self, player: PlayerState) -> str:
        if self.selected_special_index is None or self.selected_special_index >= player.hand_size:
            return ""
        special = player.hand[self.selected_special_index].special
        if special is None:
            return ""
        return f"Special armed: {special.display_name}"

    def _special_card_tag(self, special: SpecialCardType) -> str:
        return {
            SpecialCardType.BLINDFOLD: "CLAIM",
            SpecialCardType.MEMORY_WIPE: "CLAIM/CALL",
            SpecialCardType.WILDCARD_HAND: "CLAIM",
            SpecialCardType.DOUBLE_DOWN: "CLAIM",
            SpecialCardType.MIRROR_DAMAGE: "CALL",
            SpecialCardType.SHIELD: "CLAIM/CALL",
        }[special]

    def _special_card_detail(self, special: SpecialCardType) -> str:
        return {
            SpecialCardType.BLINDFOLD: "Auto-picks cards",
            SpecialCardType.MEMORY_WIPE: "Clears memory",
            SpecialCardType.WILDCARD_HAND: "Draws new hand",
            SpecialCardType.DOUBLE_DOWN: "Doubles risk",
            SpecialCardType.MIRROR_DAMAGE: "Redirects risk",
            SpecialCardType.SHIELD: "Blocks a hit",
        }[special]

    def _special_card_short_detail(self, special: SpecialCardType) -> str:
        return {
            SpecialCardType.BLINDFOLD: "AUTO PICK",
            SpecialCardType.MEMORY_WIPE: "CLEAR MEMORY",
            SpecialCardType.WILDCARD_HAND: "NEW HAND",
            SpecialCardType.DOUBLE_DOWN: "2X RISK",
            SpecialCardType.MIRROR_DAMAGE: "REDIRECT",
            SpecialCardType.SHIELD: "BLOCK HIT",
        }[special]

    def _draw_button(self, button: UIButton, mouse_pos: tuple[int, int]) -> None:
        hovered = button.rect.collidepoint(mouse_pos)
        text_button = button.key in {
            "confirm_claim",
            "challenge",
            "reset_selection",
            "claim_prev",
            "claim_next",
        }
        if text_button:
            return
        if button.enabled:
            fill = (25, 29, 35, 210) if not hovered else (42, 49, 58, 220)
            border = (225, 212, 192) if hovered else self.colors["gold"]
            text_color = self.colors["text"]
        else:
            fill = (20, 22, 26, 168)
            border = (91, 84, 76)
            text_color = (111, 108, 104)
        surface = pygame.Surface(button.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, fill, surface.get_rect(), border_radius=14)
        pygame.draw.rect(surface, border, surface.get_rect(), 2, 14)
        self.screen.blit(surface, button.rect.topleft)
        font = self.fonts["small"]
        if font.size(button.label)[0] > button.rect.width - 14:
            font = self.fonts["tiny"]
        label = font.render(button.label, True, text_color)
        self.screen.blit(label, label.get_rect(center=button.rect.center))
        if button.key == "claim_rank" and button.value == self.selected_claim_rank:
            inner = button.rect.inflate(-12, -12)
            pygame.draw.rect(self.screen, (219, 196, 133), inner, 2, 10)

    def _draw_player_card(
        self,
        card: Card,
        rect: pygame.Rect,
        selected: bool,
        hovered: bool,
        angle: float = 0,
    ) -> tuple[pygame.Rect, pygame.mask.Mask]:
        card_rect = rect.move(0, -4) if hovered else rect
        surface = pygame.Surface(card_rect.size, pygame.SRCALPHA)
        if selected:
            glow = pygame.Surface((card_rect.width + 26, card_rect.height + 26), pygame.SRCALPHA)
            pygame.draw.rect(glow, (215, 186, 120, 46), glow.get_rect(), border_radius=24)
            glow_rect = glow.get_rect(center=card_rect.center)
            self.screen.blit(glow, glow_rect)
        if card.is_special:
            self._draw_special_card_face(surface, card, selected)
        else:
            self._draw_regular_card_face(surface, card, selected)
        if angle:
            rotated = pygame.transform.rotate(surface, angle)
            final_rect = rotated.get_rect(center=card_rect.center)
            shadow = pygame.Surface((rotated.get_width() + 18, rotated.get_height() + 18), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 38), shadow.get_rect())
            self.screen.blit(shadow, shadow.get_rect(center=(final_rect.centerx + 6, final_rect.centery + 10)))
            self.screen.blit(rotated, final_rect.topleft)
            return final_rect, pygame.mask.from_surface(rotated)
        self.screen.blit(surface, card_rect.topleft)
        return card_rect, pygame.mask.from_surface(surface)

    def _draw_regular_card_face(
        self,
        surface: pygame.Surface,
        card: Card,
        selected: bool,
    ) -> None:
        rect = surface.get_rect()
        if card.rank is not None and card.suit is not None:
            asset_face = self.assets.card_face(card.rank.short_label, card.suit.value, rect.size)
            if asset_face is not None:
                surface.blit(asset_face, rect.topleft)
                if selected:
                    pygame.draw.rect(surface, (222, 181, 92), rect, 3, 14)
                return

        suit_color = self._card_suit_color(card.suit)
        border = (34, 34, 34) if selected else (138, 137, 132)
        pygame.draw.rect(surface, (253, 253, 251), rect, border_radius=14)
        pygame.draw.rect(surface, border, rect, 2 if selected else 1, 14)
        pygame.draw.rect(surface, (224, 224, 220), rect.inflate(-8, -8), 1, 10)
        self._draw_card_index(surface, card, top_left=True)
        self._draw_card_index(surface, card, top_left=False)
        if card.rank in {Rank.JACK, Rank.QUEEN, Rank.KING}:
            self._draw_face_card_art(surface, card, suit_color)
        elif card.rank == Rank.ACE:
            self._draw_suit_mark(
                surface,
                card.suit,
                (rect.centerx, rect.centery + 4),
                26,
                suit_color,
            )
        else:
            self._draw_number_card(surface, card, suit_color)

    def _draw_card_index(
        self,
        surface: pygame.Surface,
        card: Card,
        *,
        top_left: bool,
    ) -> None:
        if card.rank is None:
            return
        suit_color = self._card_suit_color(card.suit)
        corner = pygame.Surface((42, 58), pygame.SRCALPHA)
        rank_text = self.fonts["card_corner"].render(card.rank.label, True, suit_color)
        corner.blit(rank_text, rank_text.get_rect(center=(21, 17)))
        self._draw_suit_mark(corner, card.suit, (21, 43), 8, suit_color)
        if not top_left:
            corner = pygame.transform.rotate(corner, 180)
            surface.blit(corner, (surface.get_width() - 50, surface.get_height() - 66))
            return
        surface.blit(corner, (8, 8))

    def _draw_special_card_face(
        self,
        surface: pygame.Surface,
        card: Card,
        selected: bool,
    ) -> None:
        rect = surface.get_rect()
        burgundy = (58, 7, 24)
        deep = (33, 4, 14)
        gold = (218, 169, 73)
        bright_gold = (255, 213, 124)
        cream = (248, 231, 194)
        ink = (55, 12, 18)
        pygame.draw.rect(surface, burgundy, rect, border_radius=14)
        pygame.draw.rect(surface, bright_gold if selected else gold, rect, 2, 14)
        pygame.draw.rect(surface, (137, 78, 45), rect.inflate(-10, -10), 1, 10)
        pygame.draw.rect(surface, deep, rect.inflate(-18, -18), 1, 8)

        banner = pygame.Rect(12, 12, rect.width - 24, 24)
        pygame.draw.rect(surface, cream, banner, border_radius=7)
        pygame.draw.rect(surface, gold, banner, 1, 7)
        title = self.fonts["special_card"].render("SPECIAL", True, burgundy)
        surface.blit(title, title.get_rect(center=banner.center))

        if card.special is None:
            label = "SPECIAL"
            short_detail = ""
            tag = "CARD"
        else:
            label = card.special.display_name.upper()
            short_detail = self._special_card_short_detail(card.special).upper()
            tag = self._special_card_tag(card.special)

        tag_rect = pygame.Rect(20, 42, rect.width - 40, 20)
        pygame.draw.rect(surface, (25, 13, 10), tag_rect, border_radius=6)
        pygame.draw.rect(surface, gold, tag_rect, 1, 6)
        tag_surface = self.fonts["tiny"].render(tag, True, bright_gold)
        surface.blit(tag_surface, tag_surface.get_rect(center=tag_rect.center))

        name_plate = pygame.Rect(10, 68, rect.width - 20, 58)
        pygame.draw.rect(surface, cream, name_plate, border_radius=9)
        pygame.draw.rect(surface, (126, 72, 35), name_plate, 2, 9)
        words = label.split()
        line_height = 18
        total_height = len(words) * line_height
        y = name_plate.centery - total_height // 2
        for word in words:
            font = self._font_for_width(
                word,
                (self.fonts["hud_small"], self.fonts["special_card"], self.fonts["tiny"]),
                name_plate.width - 12,
            )
            text = font.render(word, True, ink)
            surface.blit(text, text.get_rect(center=(name_plate.centerx, y + line_height // 2)))
            y += line_height

        detail_plate = pygame.Rect(12, rect.bottom - 36, rect.width - 24, 24)
        pygame.draw.rect(surface, (29, 14, 10), detail_plate, border_radius=7)
        pygame.draw.rect(surface, (142, 83, 39), detail_plate, 1, 7)
        detail_font = self._font_for_width(
            short_detail,
            (self.fonts["tiny"],),
            detail_plate.width - 8,
        )
        detail_surface = detail_font.render(short_detail, True, cream)
        surface.blit(detail_surface, detail_surface.get_rect(center=detail_plate.center))

        for cx, cy in (
            (22, 52),
            (rect.width - 22, 52),
            (22, rect.height - 48),
            (rect.width - 22, rect.height - 48),
        ):
            pygame.draw.polygon(
                surface,
                (*gold, 205),
                [(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)],
            )

    def _draw_special_revolver_icon(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
    ) -> None:
        gold = (224, 161, 63)
        bright = (255, 222, 132)
        shadow = (91, 43, 23)
        pygame.draw.circle(surface, shadow, center, 43)
        pygame.draw.circle(surface, gold, center, 40, 6)
        pygame.draw.circle(surface, bright, center, 27, 3)
        for index in range(6):
            theta = -math.pi / 2 + math.tau * index / 6
            hole = (
                int(center[0] + math.cos(theta) * 23),
                int(center[1] + math.sin(theta) * 23),
            )
            pygame.draw.circle(surface, (48, 9, 20), hole, 10)
            pygame.draw.circle(surface, bright, hole, 10, 2)
        pygame.draw.polygon(
            surface,
            bright,
            [
                (center[0], center[1] - 12),
                (center[0] + 5, center[1] - 3),
                (center[0] + 14, center[1]),
                (center[0] + 5, center[1] + 3),
                (center[0], center[1] + 12),
                (center[0] - 5, center[1] + 3),
                (center[0] - 14, center[1]),
                (center[0] - 5, center[1] - 3),
            ],
        )

    def _draw_card_corner_ornaments(self, surface: pygame.Surface, card: Card) -> None:
        inset = surface.get_rect().inflate(-18, -18)
        pygame.draw.rect(surface, (168, 147, 120), inset, 1, 12)
        if card.is_special:
            return
        accent = (194, 169, 130)
        for cx, cy in (
            (inset.left + 10, inset.top + 10),
            (inset.right - 10, inset.top + 10),
            (inset.left + 10, inset.bottom - 10),
            (inset.right - 10, inset.bottom - 10),
        ):
            pygame.draw.circle(surface, accent, (cx, cy), 2)

    def _card_suit_color(self, suit: Suit | None) -> tuple[int, int, int]:
        if suit in {Suit.HEARTS, Suit.DIAMONDS}:
            return (176, 56, 56)
        return (39, 42, 48)

    def _draw_number_card(
        self,
        surface: pygame.Surface,
        card: Card,
        color: tuple[int, int, int],
    ) -> None:
        layouts = {
            Rank.SEVEN: [(0.36, 0.24), (0.64, 0.24), (0.36, 0.39), (0.64, 0.39), (0.36, 0.55), (0.64, 0.55), (0.5, 0.7)],
            Rank.EIGHT: [(0.36, 0.22), (0.64, 0.22), (0.36, 0.36), (0.64, 0.36), (0.36, 0.5), (0.64, 0.5), (0.36, 0.64), (0.64, 0.64)],
            Rank.NINE: [(0.36, 0.21), (0.64, 0.21), (0.36, 0.34), (0.64, 0.34), (0.5, 0.47), (0.36, 0.6), (0.64, 0.6), (0.36, 0.73), (0.64, 0.73)],
            Rank.TEN: [(0.36, 0.2), (0.64, 0.2), (0.36, 0.32), (0.64, 0.32), (0.36, 0.44), (0.64, 0.44), (0.36, 0.56), (0.64, 0.56), (0.36, 0.69), (0.64, 0.69)],
        }
        positions = layouts.get(card.rank, [(0.5, 0.5)])
        for px, py in positions:
            self._draw_suit_mark(
                surface,
                card.suit,
                (int(surface.get_width() * px), int(surface.get_height() * py)),
                13,
                color,
            )

    def _draw_face_card_art(
        self,
        surface: pygame.Surface,
        card: Card,
        color: tuple[int, int, int],
    ) -> None:
        width = surface.get_width()
        height = surface.get_height()
        center_panel = pygame.Rect(width // 2 - 30, 44, 60, height - 88)
        pygame.draw.rect(surface, (248, 248, 245), center_panel, border_radius=12)
        pygame.draw.rect(surface, (186, 185, 178), center_panel, 1, 12)
        rank_text = self.fonts["card_face"].render(card.rank.label, True, color)
        surface.blit(rank_text, rank_text.get_rect(center=(width // 2, height // 2)))
        self._draw_suit_mark(surface, card.suit, (width // 2, height // 2 - 45), 14, color)
        self._draw_suit_mark(surface, card.suit, (width // 2, height // 2 + 45), 14, color)

    def _draw_suit_mark(
        self,
        surface: pygame.Surface,
        suit: Suit | None,
        center: tuple[int, int],
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        x, y = center
        if suit == Suit.HEARTS:
            pygame.draw.circle(surface, color, (x - size // 2, y - size // 3), size // 2)
            pygame.draw.circle(surface, color, (x + size // 2, y - size // 3), size // 2)
            pygame.draw.polygon(surface, color, [(x - size, y - size // 6), (x + size, y - size // 6), (x, y + size)])
        elif suit == Suit.DIAMONDS:
            pygame.draw.polygon(surface, color, [(x, y - size), (x + size, y), (x, y + size), (x - size, y)])
        elif suit == Suit.CLUBS:
            pygame.draw.circle(surface, color, (x, y - size // 2), size // 2)
            pygame.draw.circle(surface, color, (x - size // 2, y + size // 6), size // 2)
            pygame.draw.circle(surface, color, (x + size // 2, y + size // 6), size // 2)
            pygame.draw.rect(surface, color, pygame.Rect(x - size // 5, y + size // 5, size // 2, size))
        elif suit == Suit.SPADES:
            pygame.draw.circle(surface, color, (x - size // 2, y), size // 2)
            pygame.draw.circle(surface, color, (x + size // 2, y), size // 2)
            pygame.draw.polygon(surface, color, [(x - size, y + size // 3), (x + size, y + size // 3), (x, y - size)])
            pygame.draw.rect(surface, color, pygame.Rect(x - size // 5, y + size // 3, size // 2, size))

    def _draw_card_back(self, rect: pygame.Rect, highlighted: bool, angle: float = 0) -> None:
        surface = self.assets.card_back((rect.width, rect.height), highlighted)
        if angle:
            rotated = pygame.transform.rotate(surface, angle)
            self.screen.blit(rotated, rotated.get_rect(center=rect.center))
            return
        self.screen.blit(surface, rect.topleft)

    def _draw_table_props(self, table_rect: pygame.Rect) -> None:
        if self.state is None:
            return
        table_center = table_rect.center
        for player in self.state.players:
            if player.is_human:
                continue
            center, scale = self._revolver_layout(player.seat_index, table_rect)
            if player.seat_index == 3:
                wolf_center, _ = self._revolver_layout(2, table_rect)
                angle = self._angle_toward(wolf_center, table_center)
            elif player.seat_index == 4:
                pig_center, _ = self._revolver_layout(1, table_rect)
                angle = self._angle_toward(pig_center, table_center)
            else:
                angle = self._angle_toward(center, table_center)
            self._draw_revolver(center, angle, scale)

    def _revolver_layout(
        self,
        seat_index: int,
        table_rect: pygame.Rect,
    ) -> tuple[tuple[int, int], float]:
        layouts = {
            0: ((table_rect.right - 190, table_rect.bottom - 48), 1.08),
            1: ((table_rect.x + 176, table_rect.y + 154), 0.96),
            2: ((table_rect.x + 364, table_rect.y + 102), 0.9),
            3: ((table_rect.centerx + 84, table_rect.y + 82), 0.92),
            4: ((table_rect.right - 300, table_rect.y + 126), 0.96),
        }
        return layouts.get(seat_index, (table_rect.center, 0.94))

    def _angle_toward(
        self,
        origin: tuple[int, int],
        target: tuple[int, int],
    ) -> float:
        dx = target[0] - origin[0]
        dy = target[1] - origin[1]
        if dx == 0 and dy == 0:
            return 0
        return -math.degrees(math.atan2(dy, dx))

    def _draw_revolver(
        self,
        center: tuple[int, int],
        angle: float,
        scale: float,
    ) -> None:
        asset_size = (max(1, int(190 * scale)), max(1, int(142 * scale)))
        asset = self.assets.transparent_image("revolver", asset_size)
        if asset is not None:
            rotated = pygame.transform.rotozoom(asset, angle, 1)
            bounds = rotated.get_bounding_rect(min_alpha=8)
            shadow = pygame.Surface((bounds.width + 26, bounds.height + 18), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 52), shadow.get_rect())
            self.screen.blit(shadow, shadow.get_rect(center=(center[0] + 8, center[1] + 10)))
            self.screen.blit(rotated, rotated.get_rect(center=center))
            return

        width = int(214 * scale)
        height = int(104 * scale)
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        barrel = pygame.Rect(int(width * 0.06), int(height * 0.4), int(width * 0.46), int(height * 0.12))
        pygame.draw.rect(surface, (24, 25, 29), barrel, border_radius=5)
        muzzle = pygame.Rect(barrel.x - int(width * 0.04), barrel.y + 2, int(width * 0.07), barrel.height - 4)
        pygame.draw.rect(surface, (32, 33, 38), muzzle, border_radius=4)
        top_bar = pygame.Rect(int(width * 0.14), int(height * 0.31), int(width * 0.38), int(height * 0.1))
        pygame.draw.rect(surface, (46, 48, 54), top_bar, border_radius=4)
        pygame.draw.rect(surface, (60, 63, 70), pygame.Rect(top_bar.x + 10, top_bar.y + 2, top_bar.width - 10, top_bar.height - 4), border_radius=3)
        pygame.draw.circle(surface, (54, 55, 60), (int(width * 0.53), int(height * 0.45)), int(height * 0.17))
        pygame.draw.circle(surface, (27, 28, 32), (int(width * 0.53), int(height * 0.45)), int(height * 0.08))
        for idx in range(6):
            theta = math.tau * idx / 6
            hole_x = int(width * 0.53 + math.cos(theta) * height * 0.08)
            hole_y = int(height * 0.45 + math.sin(theta) * height * 0.08)
            pygame.draw.circle(surface, (31, 32, 37), (hole_x, hole_y), max(2, int(height * 0.018)))
        frame = [
            (int(width * 0.42), int(height * 0.28)),
            (int(width * 0.64), int(height * 0.29)),
            (int(width * 0.69), int(height * 0.44)),
            (int(width * 0.61), int(height * 0.66)),
            (int(width * 0.45), int(height * 0.63)),
        ]
        pygame.draw.polygon(surface, (39, 40, 45), frame)
        pygame.draw.arc(surface, (27, 28, 32), pygame.Rect(int(width * 0.47), int(height * 0.4), int(width * 0.2), int(height * 0.34)), 1.35, 4.3, 5)
        trigger = [
            (int(width * 0.56), int(height * 0.46)),
            (int(width * 0.6), int(height * 0.54)),
            (int(width * 0.57), int(height * 0.59)),
            (int(width * 0.53), int(height * 0.54)),
        ]
        pygame.draw.polygon(surface, (74, 74, 78), trigger)
        grip = [
            (int(width * 0.67), int(height * 0.52)),
            (int(width * 0.92), int(height * 0.64)),
            (int(width * 0.82), int(height * 0.98)),
            (int(width * 0.62), int(height * 0.8)),
        ]
        pygame.draw.polygon(surface, (114, 74, 45), grip)
        pygame.draw.polygon(surface, (140, 92, 55), [(int(width * 0.69), int(height * 0.58)), (int(width * 0.89), int(height * 0.68)), (int(width * 0.82), int(height * 0.92)), (int(width * 0.66), int(height * 0.78))])
        rotated = pygame.transform.rotozoom(surface, angle + 180, 1)
        shadow = pygame.Surface((rotated.get_width() + 18, rotated.get_height() + 18), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 54), shadow.get_rect())
        shadow_rect = shadow.get_rect(center=(center[0] + 10, center[1] + 12))
        self.screen.blit(shadow, shadow_rect)
        self.screen.blit(rotated, rotated.get_rect(center=center))

    def _draw_wrapped_text(
        self,
        lines: list[str],
        rect: pygame.Rect,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        *,
        center: bool = False,
    ) -> None:
        y = rect.y
        for raw_line in lines:
            wrapped = self._wrap_line(raw_line, font, rect.width)
            if not wrapped:
                y += font.get_linesize() // 2
                continue
            for line in wrapped:
                surface = font.render(line, True, color)
                if center:
                    target = surface.get_rect(center=(rect.centerx, y + surface.get_height() // 2))
                    self.screen.blit(surface, target)
                else:
                    self.screen.blit(surface, (rect.x, y))
                y += font.get_linesize()
            y += 2
            if y > rect.bottom:
                return

    def _wrap_line(
        self,
        text: str,
        font: pygame.font.Font,
        width: int,
    ) -> list[str]:
        if not text:
            return []
        words = text.split()
        if not words:
            return [text]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _reputation_color(self, band: ReputationBand) -> tuple[int, int, int]:
        mapping = {
            ReputationBand.TRUSTED: (117, 176, 122),
            ReputationBand.NEUTRAL: (170, 150, 109),
            ReputationBand.SUSPECT: (192, 127, 88),
            ReputationBand.NOTORIOUS: (188, 73, 67),
        }
        return mapping[band]
