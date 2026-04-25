from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from src.engine import GameState


class MatchSnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def save_state(self, state: GameState) -> None:
        payload = {
            "round_number": state.round_number,
            "phase": state.phase.value,
            "dealer_index": state.dealer_index,
            "current_turn_index": state.current_turn_index,
            "alive_players": [
                player.name for player in state.players if not player.eliminated
            ],
            "players": [
                {
                    "name": player.name,
                    "seat_index": player.seat_index,
                    "reputation": player.reputation,
                    "shield_charges": player.shield_charges,
                    "eliminated": player.eliminated,
                    "profile_key": player.profile_key,
                    "hand": [card.short_label for card in player.hand],
                }
                for player in state.players
            ],
            "current_claim": (
                {
                    "rank": int(state.current_claim.rank),
                    "declared_by": state.current_claim.declared_by,
                    "card_count": state.current_claim.card_count,
                }
                if state.current_claim is not None
                else None
            ),
            "memory_log": list(state.public_memory_log),
            "turn_history": [asdict(record) for record in state.turn_history],
            "narration_log": [asdict(event) for event in state.narration_log],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_previous_summary(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))
