from __future__ import annotations

import math

import pygame

from src.models.card import Card, Rank, Suit


class CardViewsMixin:
    """Card faces, card backs, and the table revolver props."""

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
