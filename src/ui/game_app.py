from __future__ import annotations

import math
from pathlib import Path

import pygame

from constants import SCREEN_HEIGHT, SCREEN_WIDTH, TARGET_FPS, WINDOW_TITLE
from src.actors.ai_profiles import OPPONENT_PROFILES
from src.engine import GameEngine, GameState
from src.models.action import ActionType, TurnAction
from src.models.card import ClaimRank, SpecialCardType
from src.models.player import PlayerState, ReputationBand, TurnRecord
from src.persistence import MatchSnapshotStore
from src.ui.assets import AssetLibrary
from src.ui.card_views import CardViewsMixin
from src.ui.character_views import CharacterViewsMixin
from src.ui.hand_views import HandViewsMixin
from src.ui.input_handlers import InputHandlersMixin
from src.ui.presentation_views import PresentationEvent, PresentationViewsMixin
from src.ui.theme import build_theme
from src.ui.types import UIButton
from src.ui.visual_state import VisualStateMixin


class BluffingGameApp(
    InputHandlersMixin,
    VisualStateMixin,
    HandViewsMixin,
    PresentationViewsMixin,
    CharacterViewsMixin,
    CardViewsMixin,
):
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
        self.visual_reputation_holds: dict[str, int] = {}
        self.visual_elimination_holds: dict[str, bool] = {}
        self.visual_revolver_holds: dict[str, int] = {}
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
                duration_ms=2000,
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
                duration_ms=1800,
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

    def _clear_presentation(self) -> None:
        self.presentation_queue.clear()
        self.presentation_event = None
        self.presentation_started_at = 0
        self.presentation_until = 0
        self._clear_visual_holds()

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
            self._reveal_visuals_for_presentation(self.presentation_event)
            self._start_next_presentation(now)
        elif self.presentation_event is None and self.presentation_queue:
            self._start_next_presentation(now)
        elif self.presentation_event is None:
            self._clear_visual_holds_if_idle()

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
            if (
                self.state.current_claim is None
                and current_player.hand_size == 0
                and not current_player.eliminated
            ):
                self.engine.start_round(current_player.seat_index)
                self.turn_marker = (
                    self.state.round_number,
                    self.state.current_turn_index,
                    0,
                )
                self.status_message = "New hand dealt."
                self._save_snapshot()
                current_player = self.engine.current_player()
            if (
                self.state.current_claim is None
                and self.engine.player_needs_special_redraw(current_player)
            ):
                drawn = self.engine.refresh_special_only_hand(current_player)
                self.status_message = (
                    f"Only special cards left. Drew {drawn} replacement card(s)."
                    if drawn
                    else "Only special cards left, and the deck is empty."
                )
                self._save_snapshot()
            self._reset_human_selection()
            legal_claims = self.engine.legal_claim_ranks()
            if legal_claims:
                self.selected_claim_rank = legal_claims[0]
            self.ai_due_at = 0
        else:
            self.ai_due_at = pygame.time.get_ticks() + 900

    def _apply_action(self, player: PlayerState, action: TurnAction) -> None:
        if self.state is None:
            return
        if action.action_type == ActionType.CHALLENGE:
            self._clear_presentation()
        visual_before = self._capture_player_visuals()
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
            self._hold_challenge_visuals(self.state.turn_history[-1], visual_before)
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
                duration_ms=5000 if allow_input else 2000,
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
                duration_ms=2100,
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
                duration_ms=2500,
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
                    duration_ms=5000 if eliminated else 4200,
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
                    duration_ms=1700,
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
            if player.hand_size == 0 and self.state.current_claim is not None:
                title = "CALL"
                lines = [("LIAR", "X")]
            elif player.hand_size == 0:
                title = "DEAL"
                lines = [("Wait", "")]
            elif self.state.current_claim is not None:
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
            if player.is_human or self._display_eliminated(player):
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
            if player.profile_key == "bunny":
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
            str(self._display_reputation(player)),
            (rect.right - 8, rect.y + 17),
            anchor="midright",
            color=(255, 236, 190),
        )
        rep_rect = pygame.Rect(rect.x + 8, rect.y + 30, rect.width - 16, 6)
        fill_width = max(3, int(rep_rect.width * (self._display_reputation(player) / 100)))
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
        spent = self._display_spent_chambers(player)
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
        if self._display_eliminated(human):
            return
        rect = pygame.Rect(28, 86, 138, 30)
        self._draw_revolver_status_chip(human, rect)

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
        fill = int(rep_width * (self._display_reputation(player) / 100))
        pygame.draw.rect(
            self.screen,
            self._reputation_color(self._display_reputation_band(player)),
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
        if profile_key == "bull" or player.seat_index == 3:
            self._draw_bull_character(x, y, active, claimant, player.hand_size)
        elif profile_key == "wolf" or player.seat_index in {2, 4}:
            self._draw_wolf_character(x, y, active, claimant, player.hand_size)
        elif profile_key == "pig" or player.seat_index == 1:
            self._draw_pig_character(x, y, active, claimant, player.hand_size)
        else:
            self._draw_bunny_character(x, y, active, claimant, player.hand_size)

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

        if player.profile_key == "bunny":
            midbottom = (midbottom[0], midbottom[1] - 60)
        if flip:
            image = pygame.transform.flip(image, True, False)
        if self._display_eliminated(player):
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

    def _build_table_buttons(self, panel_rect: pygame.Rect, claim_buttons_top: int) -> None:
        if self.state is None or self.engine.is_match_over():
            return
        if self._human_eliminated():
            return
        player = self.engine.current_player()
        if not player.is_human:
            return
        if player.hand_size == 0:
            if self.state.current_claim is not None:
                self.buttons.append(
                    UIButton(
                        key="challenge",
                        label="Call Liar",
                        rect=pygame.Rect(panel_rect.x + 16, panel_rect.y + 58, panel_rect.width - 32, 34),
                        enabled=True,
                    )
                )
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
        elif selected_special_type == SpecialCardType.BLINDFOLD:
            claim_enabled = claim_enabled and player.claimable_hand_size > 0
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
        if player.hand_size == 0:
            if self.state.current_claim is not None:
                return [
                    *lines,
                    "No cards left.",
                    "Call Liar to resolve the stack.",
                    "A new hand is dealt after the roulette.",
                ]
            return [
                *lines,
                "No cards left.",
                "The next hand is being dealt.",
            ]
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
        if not legal:
            lines.append("No stronger claim exists. Challenge the stack.")
        return lines

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
