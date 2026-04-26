from __future__ import annotations

import pygame

from src.models.card import Card, SpecialCardType
from src.models.player import PlayerState


class HandViewsMixin:
    """Human hand fan, empty-hand copy, and special-card labels."""

    def _draw_human_hand(self, panel_rect: pygame.Rect, mouse_pos: tuple[int, int]) -> None:
        if self.state is None:
            return
        player = self.state.players[0]
        self._draw_hand_tray(panel_rect)
        self.hand_targets = []
        if player.hand_size == 0:
            self._draw_empty_hand_message(panel_rect)
            return
        fan_center_x = panel_rect.centerx
        fan_center_y = panel_rect.y + 112
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

    def _draw_empty_hand_message(self, panel_rect: pygame.Rect) -> None:
        center_x = panel_rect.centerx
        title_y = panel_rect.y + 72
        detail = (
            "CALL LIAR TO DEAL AGAIN"
            if self.state is not None and self.state.current_claim is not None
            else "WAIT FOR THE NEXT DEAL"
        )
        title_font = self._font_for_width(
            "NO CARDS LEFT",
            (self.fonts["hud_body"], self.fonts["hud_small"], self.fonts["tiny"]),
            360,
        )
        detail_font = self._font_for_width(
            detail,
            (self.fonts["hud_small"], self.fonts["tiny"]),
            360,
        )
        self._blit_hud_text(
            title_font,
            "NO CARDS LEFT",
            (center_x, title_y),
            anchor="center",
            color=self.colors["cream"],
        )
        line_y = title_y + 22
        pygame.draw.line(
            self.screen,
            self.colors["gold"],
            (center_x - 142, line_y),
            (center_x + 142, line_y),
            1,
        )
        for dot_x in (center_x - 154, center_x + 154):
            pygame.draw.circle(self.screen, self.colors["gold"], (dot_x, line_y), 3)
            pygame.draw.circle(self.screen, (40, 20, 11), (dot_x, line_y), 5, 1)
        self._blit_hud_text(
            detail_font,
            detail,
            (center_x, title_y + 46),
            anchor="center",
            color=self.colors["gold"],
        )

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
        rect = pygame.Rect(0, 0, 390, 74)
        rect.midbottom = (panel_rect.centerx, panel_rect.y - 14)
        name = card.special.display_name.upper()
        detail = self._special_card_detail(card.special).upper()
        name_font = self._font_for_width(
            name,
            (self.fonts["hud_body"], self.fonts["hud_small"], self.fonts["tiny"]),
            rect.width,
        )
        self._blit_shadow_text(
            name_font,
            name,
            self.colors["cream"],
            (rect.x, rect.y + 2),
            anchor="topleft",
            shadow_color=(14, 7, 5),
        )
        pygame.draw.line(
            self.screen,
            self.colors["gold"],
            (rect.x, rect.y + 40),
            (rect.x + min(rect.width, name_font.size(name)[0] + 42), rect.y + 40),
            1,
        )
        detail_font = self._font_for_width(
            detail,
            (self.fonts["hud_small"], self.fonts["tiny"]),
            rect.width,
        )
        self._blit_shadow_text(
            detail_font,
            detail,
            self.colors["gold"],
            (rect.x, rect.y + 48),
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
