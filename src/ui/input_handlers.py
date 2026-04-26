from __future__ import annotations

import pygame

from constants import SCREEN_HEIGHT, SCREEN_WIDTH
from src.models.action import ActionType, TurnAction
from src.models.card import SpecialCardType
from src.models.player import PlayerState
from src.ui.types import UIButton, allowed_specials_for_action


class InputHandlersMixin:
    """Menu, table, keyboard, and hand-selection input for the game app."""

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
        if player.hand_size == 0:
            self.status_message = "No cards left. Call Liar to resolve the stack."
            return None
        legal_claims = self.engine.legal_claim_ranks()
        if not legal_claims or self.selected_claim_rank not in legal_claims:
            self.status_message = "Choose a legal claim first."
            return None
        special_index = self._selected_special_for(ActionType.CLAIM)
        special_type = (
            player.hand[special_index].special if special_index is not None else None
        )
        if special_type == SpecialCardType.BLINDFOLD:
            if player.claimable_hand_size == 0:
                self.status_message = "Blindfold needs at least one regular card left."
                return None
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
            if card.special == SpecialCardType.BLINDFOLD and player.claimable_hand_size == 0:
                self.selected_special_index = None
                self.status_message = "Blindfold needs regular cards to pick."
                return
            if self.selected_special_index == index:
                self.selected_special_index = None
            else:
                self.selected_special_index = index
                if card.special in {SpecialCardType.BLINDFOLD, SpecialCardType.WILDCARD_HAND}:
                    self.selected_cards.clear()
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
