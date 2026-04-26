from __future__ import annotations

from src.models.action import ActionType
from src.models.player import PlayerState, ReputationBand, TurnRecord
from src.ui.presentation_views import PresentationEvent
from src.ui.types import PlayerVisualHold


class VisualStateMixin:
    """Keeps reputation/elimination changes hidden until their presentation is shown."""

    def _capture_player_visuals(self) -> dict[str, PlayerVisualHold]:
        if self.state is None:
            return {}
        return {
            player.name: PlayerVisualHold(
                reputation=player.reputation,
                eliminated=player.eliminated,
                spent_chambers=len(player.revolver.spent_indices),
            )
            for player in self.state.players
        }

    def _hold_challenge_visuals(
        self,
        record: TurnRecord,
        visual_before: dict[str, PlayerVisualHold],
    ) -> None:
        if record.action != ActionType.CHALLENGE.value:
            return
        for name, delta in record.reputation_deltas.items():
            previous = visual_before.get(name)
            if previous is not None and delta != 0:
                self.visual_reputation_holds[name] = previous.reputation
        target_name = record.bullet_target_name
        previous_target = visual_before.get(target_name or "")
        if target_name is not None and previous_target is not None and record.bullet_results:
            self.visual_elimination_holds[target_name] = previous_target.eliminated
            self.visual_revolver_holds[target_name] = previous_target.spent_chambers

    def _reveal_visuals_for_presentation(self, event: PresentationEvent) -> None:
        target_name = event.target_name
        if target_name is None:
            return
        if event.kind == "bullet":
            if not self._has_queued_presentation("bullet", target_name):
                self.visual_elimination_holds.pop(target_name, None)
                self.visual_revolver_holds.pop(target_name, None)
            return
        if event.kind == "reputation":
            self.visual_reputation_holds.pop(target_name, None)

    def _has_queued_presentation(self, kind: str, target_name: str) -> bool:
        return any(
            event.kind == kind and event.target_name == target_name
            for event in self.presentation_queue
        )

    def _clear_visual_holds(self) -> None:
        self.visual_reputation_holds.clear()
        self.visual_elimination_holds.clear()
        self.visual_revolver_holds.clear()

    def _clear_visual_holds_if_idle(self) -> None:
        if self.presentation_event is None and not self.presentation_queue:
            self._clear_visual_holds()

    def _display_reputation(self, player: PlayerState) -> int:
        return self.visual_reputation_holds.get(player.name, player.reputation)

    def _display_reputation_band(self, player: PlayerState) -> ReputationBand:
        reputation = self._display_reputation(player)
        if reputation >= 70:
            return ReputationBand.TRUSTED
        if reputation >= 45:
            return ReputationBand.NEUTRAL
        if reputation >= 25:
            return ReputationBand.SUSPECT
        return ReputationBand.NOTORIOUS

    def _display_eliminated(self, player: PlayerState) -> bool:
        return self.visual_elimination_holds.get(player.name, player.eliminated)

    def _display_spent_chambers(self, player: PlayerState) -> int:
        return self.visual_revolver_holds.get(
            player.name,
            len(player.revolver.spent_indices),
        )
