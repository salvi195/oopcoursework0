# Liar's Table — OOP Coursework Report

---

## 1. Introduction

**Liar's Table** is a single-player bluffing card game built in Python with Pygame. The player sits at a table with four AI opponents, each with a distinct personality, and takes turns making claims about the poker-rank of a set of cards placed on the table. Any opponent can call out a claim as a bluff. When a bluff is caught — or a truthful challenge fails — the loser faces the revolver: a randomised Russian-roulette mechanic.

"Six special action cards (Blindfold, Memory Wipe, Wildcard Hand, Double Down, Mirror Damage, Shield) and a reputation system. The last player standing wins.

### How to run the program

1. Install dependencies (Python 3.10+):

   ```bash
   pip install -r requirements.txt
   ```

2. Launch the game:

   ```bash
   python main.py
   ```

### How to use the program

| Screen | Action |
|---|---|
| **Main menu** | Choose New Game or Resume |
| **Your turn** | Select cards from your hand, pick a poker rank to claim, optionally play a special card, then submit |
| **Opponent's turn** | Watch their action; press **Challenge** if you think they are bluffing |
| **Round resolution** | Loser faces the revolver |

---

## 2. Body / Analysis

### 2.1 The Four OOP Pillars

---

#### Encapsulation

`PlayerState` stores all per-player data — `hand`, `reputation`, `shield_charges`, `revolver`, `eliminated` — but none of these are meant to be manipulated directly by outside code. Instead, every operation goes through a dedicated method: 

```python
# src/models/player.py

def change_reputation(self, delta: int) -> None:
    self.reputation = max(
        MIN_REPUTATION,
        min(MAX_REPUTATION, self.reputation + delta),
    )

def resolve_bullet(self, rng: random.Random | None = None) -> BulletOutcome:
    if self.shield_charges > 0:
        self.shield_charges -= 1
        return BulletOutcome(result=ChamberResult.EMPTY, ..., shield_used=True, eliminated=False)
    chamber_index, result = self.revolver.fire(rng)
    ...
```

`change_reputation` enforces the `[0, 100]` clamp so callers cannot push reputation out of range. `resolve_bullet` decides internally whether the shield absorbs the shot — the engine never branches on `shield_charges` itself.

`Revolver` encapsulates its chamber list and spent indices. The only public operation is `fire()`:

```python
@dataclass(slots=True)
class Revolver:
    chambers: list[ChamberResult]
    spent_indices: set[int] = field(default_factory=set)

    def fire(self, rng=None) -> tuple[int, ChamberResult]:
        choices = self.available_indices()
        chamber_index = rng.choice(choices)
        self.spent_indices.add(chamber_index)
        ...
```

---

#### Abstraction

`BaseAIStrategy` exposes a single interface — `choose_action(context)` — that the engine calls for every AI turn without knowing how each character actually decides:

```python
# src/actors/strategy.py

class BaseAIStrategy:
    def choose_action(self, context: AIContext) -> TurnAction:
        if self._should_challenge(context):
            return self._with_special(context, TurnAction.challenge(...))
        ...

    def observe_turn(self, turn_record: TurnRecord) -> None:
        return None  # subclasses opt in
```

The decision logic — bluff rates, pressure counters, ghost mode — is entirely hidden from the caller. The engine calls `strategy.choose_action(context)` and receives a `TurnAction` regardless of which character it is talking to.

`TurnAction` also abstracts action construction through named class methods, so callers never set fields manually:

```python
# src/models/action.py

@classmethod
def claim(cls, card_indices, claim_rank, ...) -> "TurnAction":
    return cls(action_type=ActionType.CLAIM, ...)

@classmethod
def challenge(cls, ...) -> "TurnAction":
    return cls(action_type=ActionType.CHALLENGE, ...)
```

---

#### Inheritance

All four AI characters inherit from `BaseAIStrategy`. The base class provides the full default decision loop; each subclass overrides only what differs:

```python
# src/actors/strategy.py

class PigStrategy(BaseAIStrategy):
    bluff_chance = 0.70
    challenge_chance = 0.35
    max_claim_cards = 3
    style = PresentationStyle.AGGRESSIVE

class BullStrategy(BaseAIStrategy):
    bluff_chance = 0.15
    challenge_chance = 0.45
    style = PresentationStyle.COMPOSED
```

`BunnyStrategy` goes further — it adds its own private state and fully reimplements `choose_action` and `observe_turn`, calling `super()` as a fallback:

```python
class BunnyStrategy(BaseAIStrategy):
    def __init__(self, owner_name, rng=None):
        super().__init__(owner_name, rng)
        self.pressure = 0

    def choose_action(self, context: AIContext) -> TurnAction:
        if self.pressure >= 3:
            self.pressure = 0
            # activate Ghost Mode — challenge or claim at maximum aggression
            ...
        return super().choose_action(context)

    def observe_turn(self, turn_record: TurnRecord) -> None:
        if turn_record.actor_name != self.owner_name:
            self.pressure = min(3, self.pressure + 1)
```

---

#### Polymorphism

The engine calls `strategy.choose_action(context)` identically for all four AI types. Each returns a `TurnAction`, but the reasoning differs entirely:

```python
# src/engine.py

def choose_ai_action(self, player: PlayerState) -> TurnAction:
    strategy = self.ai_strategies[player.seat_index]
    context = self._build_ai_context(player)
    return strategy.choose_action(context)  # polymorphic dispatch
```

There is no `isinstance` branching — the correct behaviour for `PigStrategy`, `BullStrategy`, or `BunnyStrategy` is resolved at runtime through the method override. `PigStrategy` bluffs 70 % of the time; `BullStrategy` challenges aggressively; `BunnyStrategy` may enter Ghost Mode. Same call, different outcome.

`ClaimRank` extends `IntEnum`, so comparisons like `evaluated_rank >= claimed_rank` work naturally across all rank values without explicit branching.

---

### 2.2 Design Pattern — Factory Method

`StrategyFactory` centralises AI object creation. The engine passes a `profile_key` string and receives the correct concrete strategy without depending on any specific class:

```python
# src/actors/strategy.py

class StrategyFactory:
    _strategies = {
        "pig":   PigStrategy,
        "wolf":  WolfStrategy,
        "bull":  BullStrategy,
        "bunny": BunnyStrategy,
    }

    @classmethod
    def create(cls, profile_key: str, owner_name: str, rng=None) -> BaseAIStrategy:
        strategy_class = cls._strategies.get(profile_key)
        if strategy_class is None:
            raise ValueError(f"Unknown AI profile key: {profile_key}")
        return strategy_class(owner_name=owner_name, rng=rng)
```

---

### 2.3 Composition and Aggregation

**Composition** — `PlayerState` composes a `Revolver`. The revolver is created by the dataclass `default_factory` at the same moment as the player and is discarded with it:

```python
@dataclass(slots=True)
class PlayerState:
    ...
    revolver: Revolver = field(default_factory=Revolver.randomised)
```

`Deck` composes its `Card` objects — cards are generated inside `Deck.standard()`, drawn out, and consumed. They have no lifecycle outside the deck.

**Aggregation** — `AIContext` holds references to `PlayerState` objects that continue to exist in `GameState.players` after the context is discarded:

```python
@dataclass(frozen=True, slots=True)
class AIContext:
    player: PlayerState               # reference, not ownership
    opponents: tuple[PlayerState, ...]
    current_claim: Claim | None
    ...
```

`GameEngine` aggregates `GameState` — the engine creates the state via `bootstrap_match()` and returns it to the UI layer, which holds its own reference. The state can be inspected and serialised independently of the engine.

---

### 2.4 Reading from File and Writing to File

`MatchSnapshotStore` in `src/persistence.py` handles all file I/O using **JSON**:

```python
# src/persistence.py

class MatchSnapshotStore:
    def save_state(self, state: GameState) -> None:
        payload = {
            "round_number": state.round_number,
            "phase": state.phase.value,
            "players": [
                {
                    "name": player.name,
                    "reputation": player.reputation,
                    "hand": [card.short_label for card in player.hand],
                    ...
                }
                for player in state.players
            ],
            "turn_history": [asdict(record) for record in state.turn_history],
            ...
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_previous_summary(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))
```

On the next launch, `GameEngine.resume_match(snapshot)` reads the JSON back and reconstructs all player states, AI strategies, round number, and phase exactly where the session ended.

---

### 2.5 Testing

Tests live in `tests/` and use Python's `unittest` framework across three files:

| File | Coverage |
|---|---|
| `test_game_core.py` | Hand evaluator, player mechanics, strategy factory, persistence, engine helpers, all 6 special cards |
| `test_asset_cache.py` | Cache regeneration when a cached PNG is corrupt |
| `test_menu_input.py` | Text-input widget edge cases (backspace, max length, Enter) |

```python
# Hand evaluator
def test_detects_royal_flush(self):
    cards = [Card(rank=Rank.TEN, suit=Suit.HEARTS), ..., Card(rank=Rank.ACE, suit=Suit.HEARTS)]
    self.assertEqual(evaluate_claim_rank(cards), ClaimRank.ROYAL_FLUSH)

# Shield absorbs bullet before revolver fires
def test_shield_absorbs_bullet(self):
    player = PlayerState(name="Tester", seat_index=0)
    player.grant_shield()
    outcome = player.resolve_bullet()
    self.assertTrue(outcome.shield_used)
    self.assertFalse(outcome.eliminated)

# Mirror Damage redirects the bullet to the claimant
def test_mirror_damage_redirects_truthful_challenge_penalty(self):
    ...
    result = self.engine.process_action(self.opponent, TurnAction.challenge(special_card_index=0))
    self.assertIn("Mirror Damage redirects", result.summary)
    self.assertEqual(len(self.player.revolver.spent_indices), 1)
    self.assertEqual(len(self.opponent.revolver.spent_indices), 0)
```

---

## 3. Results and Summary

### Results

- The program implements a complete, playable bluffing card game with five distinct characters, six special-card mechanics, a reputation system, and a Russian-roulette elimination loop.
- The most significant challenge was managing state consistency across branching special-card interactions — Double Down triggering two bullet spins, Mirror Damage redirecting the penalty to a different player — while keeping each handler independently testable.

### Conclusions

The coursework produced a themed bluffing card game that demonstrates all four OOP pillars. The AI strategy hierarchy cleanly illustrates inheritance and polymorphism; `PlayerState` and `Revolver` demonstrate encapsulation; `BaseAIStrategy` and `TurnAction` demonstrate abstraction. The Factory Method pattern keeps the engine decoupled from AI classes.

**Future prospects:**

- **Character abilities** — Each animal could have a passive or once-per-round ability.
- **Extended persistence** — the save system could be extended to store match history and win rates across multiple sessions.

---
