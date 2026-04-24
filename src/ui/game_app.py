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
from src.models.player import PlayerState, ReputationBand
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
        self.hand_targets: list[tuple[pygame.Rect, int]] = []
        self.selected_cards: set[int] = set()
        self.selected_special_index: int | None = None
        self.selected_claim_rank: ClaimRank | None = None
        self.keyboard_card_index = 0
        self.blindfold_count = 2
        self.status_message = ""
        self.last_result = ""
        self.ai_due_at = 0
        self.turn_marker: tuple[int, int, int] | None = None
        self.profile_lookup = {profile.key: profile for profile in OPPONENT_PROFILES}
        self.theme = build_theme(Path("assets"))
        self.colors = self.theme.colors
        self.fonts = self.theme.fonts
        self.profile_colors = self.theme.profile_colors
        self.assets = AssetLibrary(
            Path("assets"),
            self.colors,
            self.profile_colors,
            self.profile_lookup,
        )

    def run(self) -> None:
        while self.running:
            now = pygame.time.get_ticks()
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
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        for button in self.buttons:
            if button.rect.collidepoint(event.pos) and button.enabled:
                if button.key == "menu_new":
                    self._start_new_match()
                elif button.key == "menu_resume":
                    self._resume_match()
                elif button.key == "menu_quit":
                    self.running = False
                return

    def _handle_table_event(self, event: pygame.event.Event) -> None:
        if self.state is None:
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
        player = self.engine.current_player()
        if not player.is_human:
            return
        for button in self.buttons:
            if button.rect.collidepoint(event.pos) and button.enabled:
                self._handle_button_press(button)
                return
        for rect, index in self.hand_targets:
            if rect.collidepoint(event.pos):
                self._handle_card_press(index)
                return

    def _handle_table_keydown(self, event: pygame.event.Event) -> None:
        if self.state is None or self.engine.is_match_over():
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
            legal_claims = self.engine.legal_claim_ranks()
            if legal_claims:
                if self.selected_claim_rank not in legal_claims:
                    self.selected_claim_rank = legal_claims[0]
                else:
                    index = legal_claims.index(self.selected_claim_rank)
                    self.selected_claim_rank = legal_claims[(index - 1) % len(legal_claims)]
            return
        if button.key == "claim_next":
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
            self.blindfold_count = max(1, self.blindfold_count - 1)
            return
        if button.key == "blindfold_plus":
            self.blindfold_count = min(
                max(1, player.claimable_hand_size),
                self.blindfold_count + 1,
            )
            return
        if button.key == "reset_selection":
            self._reset_human_selection()
            legal_claims = self.engine.legal_claim_ranks()
            self.selected_claim_rank = legal_claims[0] if legal_claims else None
            return
        if button.key == "challenge":
            special_index = self._selected_special_for(ActionType.CHALLENGE)
            action = TurnAction.challenge(
                special_card_index=special_index,
                note="Human challenge.",
            )
            self._apply_action(player, action)
            return
        if button.key == "confirm_claim":
            action = self._build_human_claim_action(player)
            if action is not None:
                self._apply_action(player, action)

    def _selected_special_for(self, action_type: ActionType) -> int | None:
        if self.state is None or self.selected_special_index is None:
            return None
        player = self.engine.current_player()
        if self.selected_special_index >= player.hand_size:
            return None
        special = player.hand[self.selected_special_index].special
        if special in allowed_specials_for_action(action_type):
            return self.selected_special_index
        return None

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

    def _apply_action(self, player: PlayerState, action: TurnAction) -> None:
        if self.state is None:
            return
        try:
            result = self.engine.process_action(player, action)
        except Exception as error:
            self.status_message = str(error)
            return
        self.last_result = result.summary
        self.status_message = ""
        self._save_snapshot()
        self.turn_marker = None
        self._reset_human_selection()

    def _update_table(self, now: int) -> None:
        if self.state is None or self.engine.is_match_over():
            return
        current_player = self.engine.current_player()
        if current_player.is_human:
            return
        if self.ai_due_at == 0:
            self.ai_due_at = now + 900
            return
        if now < self.ai_due_at:
            return
        action = self.engine.choose_ai_action(current_player)
        self._apply_action(current_player, action)
        self.ai_due_at = 0

    def _draw(self, now: int) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self.buttons = []
        self.hand_targets = []
        self._draw_background(now)
        if self.mode == "menu":
            self._draw_menu(mouse_pos)
        else:
            self._draw_table(mouse_pos, now)

    def _layout(self) -> dict[str, object]:
        claim_hud = pygame.Rect(24, 14, 286, 132)
        move_hud = pygame.Rect(968, 14, 288, 158)
        control_rect = pygame.Rect(1000, 206, 244, 286)
        table_rect = pygame.Rect(70, 324, 1140, 416)
        dealer_rect = pygame.Rect(338, 18, 604, 22)
        hand_rect = pygame.Rect(250, 448, 780, 302)
        claim_buttons_top = control_rect.y + 18
        seat_positions = {
            0: (table_rect.centerx, 646),
            1: (164, 286),
            2: (362, 198),
            3: (table_rect.centerx, 146),
            4: (1122, 286),
        }
        return {
            "claim_hud": claim_hud,
            "move_hud": move_hud,
            "control_rect": control_rect,
            "table_rect": table_rect,
            "dealer_rect": dealer_rect,
            "hand_rect": hand_rect,
            "seat_positions": seat_positions,
            "claim_buttons_top": claim_buttons_top,
        }

    def _draw_background(self, now: int) -> None:
        self.screen.fill(self.colors["bg"])
        if self.mode == "menu":
            background = self.assets.background("menu_room", (SCREEN_WIDTH, SCREEN_HEIGHT))
            if background is not None:
                self.screen.blit(background, (0, 0))
            glow = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pulse = 18 + int(10 * (1 + pygame.math.Vector2(1, 0).rotate(now * 0.04).x))
            pygame.draw.circle(glow, (73, 46, 58, 70), (220, 160), 230 + pulse)
            pygame.draw.circle(
                glow,
                (25, 76, 68, 110),
                (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2),
                360,
            )
            pygame.draw.circle(glow, (108, 64, 44, 55), (SCREEN_WIDTH - 180, 210), 210)
            self.screen.blit(glow, (0, 0))
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

    def _draw_menu(self, mouse_pos: tuple[int, int]) -> None:
        title = self.fonts["title"].render(WINDOW_TITLE, True, self.colors["text"])
        subtitle = self.fonts["dealer"].render(
            "A staged room of trust, pressure, and bad timing.",
            True,
            self.colors["muted"],
        )
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 132)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 176)))
        self._draw_menu_gallery()

        panel = pygame.Surface((680, 336), pygame.SRCALPHA)
        pygame.draw.rect(panel, self.colors["panel"], panel.get_rect(), border_radius=28)
        pygame.draw.rect(panel, (*self.colors["border"], 210), panel.get_rect(), 2, 28)
        self.screen.blit(panel, (300, 258))

        button_specs = [
            ("menu_new", "Start New Match", True),
            ("menu_resume", "Resume Latest Match", self.saved_summary is not None),
            ("menu_quit", "Quit", True),
        ]
        top = 332
        for key, label, enabled in button_specs:
            rect = pygame.Rect(430, top, 420, 54)
            button = UIButton(key=key, label=label, rect=rect, enabled=enabled)
            self.buttons.append(button)
            self._draw_button(button, mouse_pos)
            top += 70

        if self.saved_summary is not None:
            summary_lines = [
                f"Latest checkpoint: round {self.saved_summary['round_number']}",
                f"Alive players: {', '.join(self.saved_summary['alive_players'])}",
            ]
        else:
            summary_lines = [
                "No saved checkpoint found yet.",
                "Start a match and the game will create one after each turn.",
            ]
        self._draw_wrapped_text(
            summary_lines,
            pygame.Rect(360, 558, 560, 62),
            self.fonts["small"],
            self.colors["muted"],
        )

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
        self._draw_human_hand(layout["hand_rect"], mouse_pos)
        self._draw_claim_hud(layout["claim_hud"])
        self._draw_action_hud(layout["move_hud"])
        self._draw_dealer_banner(layout["dealer_rect"])
        self._build_table_buttons(layout["control_rect"], layout["claim_buttons_top"])
        for button in self.buttons:
            self._draw_button(button, mouse_pos)
        if self.engine.is_match_over():
            self._draw_end_overlay(mouse_pos)

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

    def _draw_keycap(
        self,
        key: str,
        pos: tuple[int, int],
        *,
        anchor: str = "topright",
    ) -> pygame.Rect:
        font = self.fonts["hud_small"]
        pad_x = 8
        pad_y = 4
        text = font.render(key, True, self.colors["text"])
        rect = pygame.Rect(0, 0, text.get_width() + pad_x * 2, text.get_height() + pad_y * 2)
        setattr(rect, anchor, pos)
        shadow = rect.move(2, 2)
        pygame.draw.rect(self.screen, (16, 12, 10, 145), shadow, border_radius=8)
        pygame.draw.rect(self.screen, (27, 54, 53, 210), rect, border_radius=8)
        pygame.draw.rect(self.screen, (202, 210, 182), rect, 2, 8)
        self.screen.blit(text, text.get_rect(center=rect.center))
        return rect

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
        title_font = self.fonts["hud_title"]
        body_font = self.fonts["hud_body"]
        small_font = self.fonts["hud_small"]
        self._blit_shadow_text(title_font, "LIAR'S BAR", self.colors["text"], (rect.x, rect.y))
        pygame.draw.line(
            self.screen,
            self.colors["text"],
            (rect.x + 4, rect.y + 42),
            (rect.right - 10, rect.y + 42),
            2,
        )
        if self.state.current_claim is None:
            self._blit_shadow_text(
                body_font,
                "OPENING MOVE",
                self.colors["text"],
                (rect.x + 8, rect.y + 54),
            )
            self._blit_shadow_text(
                small_font,
                f"ROUND {self.state.round_number}",
                self.colors["muted"],
                (rect.x + 8, rect.y + 86),
            )
            return
        claimant = self.state.players[self.state.current_claimant_index]
        self._blit_shadow_text(
            body_font,
            claimant.name.upper(),
            self.colors["text"],
            (rect.x + 8, rect.y + 54),
        )
        self._blit_shadow_text(
            small_font,
            "CLAIMS",
            self.colors["muted"],
            (rect.x + 8, rect.y + 82),
        )
        claim_label = self.state.current_claim.display_text.upper()
        claim_font = body_font if body_font.size(claim_label)[0] <= rect.width - 12 else small_font
        self._blit_shadow_text(
            claim_font,
            claim_label,
            self.colors["text"],
            (rect.x + 8, rect.y + 102),
        )

    def _draw_action_hud(self, rect: pygame.Rect) -> None:
        if self.state is None:
            return
        player = self.engine.current_player()
        if self.engine.is_match_over():
            lines = [("Continue", "ENTER")]
            title = "TABLE DECIDED"
        elif not player.is_human:
            title = player.name.upper()
            lines = [("Watch", "")]
        else:
            title = "YOUR TURN!"
            lines = [
                ("Select Card", "SPACE"),
                ("Throw Card", "C"),
                ("Call LIAR!", "X"),
                ("Change Claim", "Q/E"),
            ]
        self._blit_shadow_text(
            self.fonts["hud_title"],
            title,
            self.colors["text"],
            (rect.right, rect.y),
            anchor="topright",
        )
        pygame.draw.line(
            self.screen,
            self.colors["text"],
            (rect.x + 28, rect.y + 42),
            (rect.right, rect.y + 42),
            2,
        )
        y = rect.y + 56
        for label, key in lines:
            if key:
                key_rect = self._draw_keycap(key, (rect.right, y - 1))
                label_right = key_rect.x - 20
            else:
                label_right = rect.right
            self._blit_shadow_text(
                self.fonts["hud_body"],
                label,
                self.colors["text"],
                (label_right, y),
                anchor="topright",
            )
            y += 28
        if self.status_message and player.is_human and not self.engine.is_match_over():
            status_font = self.fonts["hud_small"]
            status = self.status_message.upper()
            self._blit_shadow_text(
                status_font,
                status,
                self.colors["muted"],
                (rect.right, rect.bottom - 30),
                anchor="topright",
            )

    def _draw_table_surface(self, table_rect: pygame.Rect, now: int) -> None:
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

    def _draw_human_hand(self, panel_rect: pygame.Rect, mouse_pos: tuple[int, int]) -> None:
        if self.state is None:
            return
        player = self.state.players[0]
        left_arm = [(376, 800), (420, 694), (498, 608), (546, 634), (486, 800)]
        right_arm = [(864, 800), (842, 686), (900, 632), (980, 662), (1010, 800)]
        pygame.draw.polygon(self.screen, (88, 54, 43), left_arm)
        pygame.draw.polygon(self.screen, (103, 69, 52), right_arm)
        pygame.draw.ellipse(self.screen, (60, 40, 31), pygame.Rect(444, 618, 118, 58))
        pygame.draw.ellipse(self.screen, (72, 48, 37), pygame.Rect(864, 642, 126, 64))
        player_badge = pygame.Rect(546, 722, 188, 32)
        pygame.draw.rect(self.screen, (18, 20, 24, 190), player_badge, border_radius=16)
        pygame.draw.rect(self.screen, (240, 228, 210), player_badge, 1, 16)
        badge_text = self.fonts["small"].render("PLAYER", True, self.colors["text"])
        self.screen.blit(badge_text, badge_text.get_rect(center=player_badge.center))
        special_label = self._active_special_label(player)
        if special_label:
            special_text = self.fonts["small"].render(special_label, True, self.colors["gold"])
            self.screen.blit(
                special_text,
                (panel_rect.centerx - special_text.get_width() // 2, panel_rect.y + 6),
            )
        self.hand_targets = []
        if player.hand_size == 0:
            empty = self.fonts["body"].render("No cards left in hand.", True, self.colors["muted"])
            self.screen.blit(empty, empty.get_rect(center=(panel_rect.centerx, panel_rect.y + 70)))
            return
        fan_center_x = 620
        fan_center_y = 586
        spacing = 66
        card_width = 112
        card_height = 168
        mid_index = (player.hand_size - 1) / 2
        for index, card in enumerate(player.hand):
            is_selected = index in self.selected_cards or index == self.selected_special_index
            angle = (index - mid_index) * -8
            base_x = fan_center_x + int((index - mid_index) * spacing)
            base_y = fan_center_y + int(abs(index - mid_index) * 10) - (16 if is_selected else 0)
            rect = pygame.Rect(
                base_x - card_width // 2,
                base_y - card_height // 2,
                card_width,
                card_height,
            )
            final_rect = self._draw_player_card(
                card,
                rect,
                is_selected,
                rect.collidepoint(mouse_pos),
                angle=angle,
            )
            self.hand_targets.append((final_rect, index))

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
        if player.seat_index == 3:
            self._draw_bull_character(x, y, active, claimant, player.hand_size)
        elif player.seat_index == 2:
            self._draw_wolf_character(x, y, active, claimant, player.hand_size)
        elif player.seat_index == 1:
            self._draw_pig_character(x, y, active, claimant, player.hand_size)
        else:
            self._draw_fox_character(x, y, active, claimant, player.hand_size)

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
        pygame.draw.ellipse(self.screen, fur, head)...