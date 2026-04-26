Liar's Table Coursework Report
==============================

Student name: ____________________

Course/module: ____________________

Repository: `oopcoursework0`

Language and library: Python with Pygame


1. Introduction
---------------

### What is the application?

Liar's Table is a turn-based bluffing card game inspired by Liar's Bar. The
player sits at a saloon-style card table with AI opponents. Players make claims
about the cards they play, raise previous claims, or call "Liar" when they think
someone has bluffed. When a player is caught lying, or when a wrong challenge is
made, the losing player faces a revolver penalty.

The goal of the coursework was to create a complete Python application that
uses object-oriented programming, file saving/loading, a design pattern, tests,
and a clear user interface.

### How to run the program

Install the dependency:

```powershell
pip install -r requirements.txt
```

Run the game:

```powershell
python main.py
```

The project also includes a VS Code launch configuration:

```text
.vscode/launch.json -> Launch game
```

### How to use the program

The game starts on a menu screen. The player can start a new match or resume a
saved match.

During the game:

- Select cards from the hand.
- Choose a claim rank.
- Press the claim/throw action to play cards.
- Press Call Liar when a claim looks suspicious.
- Watch the result presentation and revolver outcome.
- Continue until only one player is alive.

Visual description: the game uses a dark saloon table, warm gold text, character
portraits around the table, a card fan for the human player's hand, and focused
presentation screens for claims, challenges, bullets, and reputation changes.


2. Body / Analysis
------------------

### Project structure

The project is separated into clear folders:

```text
main.py
constants.py
assets/
src/
  actors/
    ai_profiles.py
    strategy.py
  models/
    action.py
    card.py
    evaluator.py
    player.py
  ui/
    assets.py
    card_views.py
    character_views.py
    game_app.py
    hand_views.py
    input_handlers.py
    presentation_views.py
    theme.py
    types.py
    visual_state.py
  engine.py
  persistence.py
tests/
REPORT.md
```

This structure keeps the project easier to understand:

- `src/models/` stores the main data classes and enums.
- `src/engine.py` stores the rules and turn flow.
- `src/actors/` stores AI opponent logic.
- `src/ui/` stores Pygame drawing, input, and visual presentation code.
- `src/persistence.py` stores file saving and loading.
- `tests/` stores unit tests.


### Functional requirements

| Requirement | How it is implemented |
| --- | --- |
| Playable program | `main.py` starts `BluffingGameApp`, which runs the Pygame loop. |
| OOP design | Models, engine, AI strategies, UI classes, and persistence are class-based. |
| 4 OOP pillars | Polymorphism, abstraction, inheritance, and encapsulation are all used. |
| Design pattern | Factory Method is used in `StrategyFactory`. |
| Composition / aggregation | `BluffingGameApp` owns engine/assets; `GameState` aggregates players and deck. |
| Reading/writing files | Match data is saved and loaded as JSON in `saves/latest_match.json`. |
| Unit tests | `unittest` tests are in the `tests` folder. |
| PEP8 style | Code uses clear names, class separation, type hints, and focused methods. |
| GitHub upload | The project is in one Git repository with code and `REPORT.md`. |


### Object-oriented programming pillars

#### Encapsulation

Encapsulation means keeping related data and behaviour together inside a class.
It protects the rest of the program from needing to know every internal detail.

In this project, `PlayerState` stores player data and also contains methods that
modify that player.

```python
@dataclass(slots=True)
class PlayerState:
    name: str
    seat_index: int
    hand: list[Card] = field(default_factory=list)
    reputation: int = STARTING_REPUTATION
    shield_charges: int = 0
    eliminated: bool = False

    def change_reputation(self, delta: int) -> None:
        self.reputation = max(
            MIN_REPUTATION,
            min(MAX_REPUTATION, self.reputation + delta),
        )
```

This is encapsulation because reputation logic is handled by the player class
instead of being repeated in many other files.


#### Abstraction

Abstraction means hiding complex details behind simple methods. Other parts of
the program can use a feature without knowing exactly how it is implemented.

The UI does not manually calculate all game rules. It calls clear methods from
`GameEngine`.

```python
def process_action(self, player: PlayerState, action: TurnAction) -> ActionResult:
    if action.action_type == ActionType.CLAIM:
        return self._process_claim(player, action)
    return self._process_challenge(player, action)
```

The method name explains what happens. The UI can process a claim or challenge
without knowing all private helper methods inside the engine.


#### Inheritance

Inheritance means one class can reuse or extend behaviour from another class.

The AI system uses a base strategy class and several specific strategy classes.

```python
class BaseAIStrategy:
    bluff_chance = 0.35
    challenge_chance = 0.25

    def choose_action(self, context: AIContext) -> TurnAction:
        ...


class PigStrategy(BaseAIStrategy):
    bluff_chance = 0.70
    challenge_chance = 0.35


class BullStrategy(BaseAIStrategy):
    bluff_chance = 0.15
    challenge_chance = 0.45
```

`PigStrategy` and `BullStrategy` inherit the shared AI logic but use different
values, creating different personalities.

The UI also uses inheritance through mixins:

```python
class BluffingGameApp(
    InputHandlersMixin,
    VisualStateMixin,
    HandViewsMixin,
    PresentationViewsMixin,
    CharacterViewsMixin,
    CardViewsMixin,
):
    ...
```

This keeps the main app class smaller and easier to explain.


#### Polymorphism

Polymorphism means different objects can be used through the same interface, but
each object can behave differently.

All AI strategies provide a `choose_action` method. The engine can ask any AI
strategy to choose an action without needing special code for each opponent.

```python
strategy = self.ai_strategies.get(player.seat_index)
return strategy.choose_action(self._build_ai_context(player))
```

The result can be different depending on whether the strategy is Pig, Wolf,
Bull, or Bunny.


### Design pattern: Factory Method

The project uses the Factory Method pattern in `StrategyFactory`.

Factory Method means object creation is moved into a separate factory method
instead of creating objects directly everywhere in the code. This is useful when
the program needs different object types that share a common role.

```python
class StrategyFactory:
    _strategies = {
        "pig": PigStrategy,
        "wolf": WolfStrategy,
        "bull": BullStrategy,
        "bunny": BunnyStrategy,
    }

    @classmethod
    def create(
        cls,
        profile_key: str,
        owner_name: str,
        rng: random.Random | None = None,
    ) -> BaseAIStrategy:
        strategy_class = cls._strategies.get(profile_key)
        if strategy_class is None:
            raise ValueError(f"Unknown AI profile key: {profile_key}")
        return strategy_class(owner_name=owner_name, rng=rng)
```

Why this pattern fits:

- The game has several AI types.
- Each AI type has different behaviour.
- The engine should not need long `if` statements for every opponent.
- Adding a new AI only requires adding a strategy class and registering it in
  the factory.

Factory Method is more suitable than Singleton here because the game needs many
AI strategy objects, not one global object. It is also simpler than Abstract
Factory because only one family of objects is being created: AI strategies.


### Composition and aggregation

Composition means one object is built from other objects that it owns.
Aggregation means one object keeps references to related objects that can also
exist as separate concepts.

Composition is used in `BluffingGameApp`. The app creates and owns important
helper objects:

```python
self.engine = GameEngine()
self.snapshot_store = MatchSnapshotStore(Path("saves/latest_match.json"))
self.assets = AssetLibrary(asset_dir, self.colors, self.profile_colors, self.profile_lookup)
```

The app is composed from the engine, snapshot store, asset library, clock,
screen, theme, and UI mixins.

Aggregation is used in `GameState`. It groups players, deck, claims, history,
and narration into one match state:

```python
@dataclass(slots=True)
class GameState:
    players: list[PlayerState]
    deck: Deck
    current_claim: Claim | None = None
    turn_history: list[TurnRecord] = field(default_factory=list)
```

This is aggregation because a game state contains related game objects and uses
them together to represent the match.


### Reading from file and writing to file

The program saves and loads match progress using JSON. This is implemented in
`MatchSnapshotStore`.

```python
class MatchSnapshotStore:
    def save_state(self, state: GameState) -> None:
        payload = {
            "round_number": state.round_number,
            "players": [
                {
                    "name": player.name,
                    "reputation": player.reputation,
                    "eliminated": player.eliminated,
                }
                for player in state.players
            ],
            "turn_history": [asdict(record) for record in state.turn_history],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_previous_summary(self) -> dict | None:
        if not self.path.exists():
            return None
        return json.loads(self.path.read_text(encoding="utf-8"))
```

The save file is stored at:

```text
saves/latest_match.json
```

This covers the requirement for reading from and writing to a file.


### Testing

The project uses the `unittest` framework. Tests are placed in the `tests`
folder.

Main test files:

- `tests/test_game_core.py`
- `tests/test_menu_input.py`
- `tests/test_asset_cache.py`

The tests cover:

- card evaluation
- player reputation bands
- revolver and shield behaviour
- AI strategy creation
- special card behaviour
- challenge and round reset rules
- empty-hand edge cases
- menu and UI input behaviour
- save/load behaviour
- asset cache recovery

Run tests with:

```powershell
python -m unittest discover -s tests
```

Latest result:

```text
Ran 30 tests
OK
```


### User interface and visual design

The interface is designed to match the saloon/card-table theme.

Main menu:

- dark bar background
- large neon-style title
- simple menu buttons
- character gallery atmosphere

Game table:

- large central table
- opponents around the table
- human hand shown as a card fan at the bottom
- compact HUD for current claim, actions, reputation, and revolver status

Presentation overlays:

- claim screen
- challenge screen
- revolver screen
- reputation screen

The presentation overlays make important events clear before visual state
changes happen. For example, a character does not fade out before the bullet
result is shown.


3. Results and Summary
----------------------

### Results

- The result is a playable Python/Pygame card bluffing game with AI opponents,
  special cards, saving/loading, and a themed interface.
- A major challenge was preventing edge cases where a player had no playable
  cards. This was solved by allowing "Call Liar" when a claim is active and
  dealing a new round after roulette.
- Another challenge was keeping the UI understandable. The large UI file was
  split into smaller focused files such as `hand_views.py`,
  `input_handlers.py`, and `visual_state.py`.
- The project includes automated tests, and the current test suite passes with
  30 tests.
- The project is organised in one Git repository and is ready to upload to
  GitHub with the program files and this Markdown report.

### Conclusions

This coursework achieved the goal of building a complete object-oriented Python
application. The final program separates models, rules, AI, persistence, and UI
code. It demonstrates the four OOP pillars, uses the Factory Method pattern,
uses composition and aggregation, saves/loads JSON data, and includes unit
tests.

The final result is a working game that can be launched with `python main.py`.
The code is structured so it can be explained and extended. Future improvements
could include sound effects, more AI difficulty settings, a tutorial screen,
more card modes, or a more advanced save system.


4. Resources / References
-------------------------

- Python documentation: https://docs.python.org/3/
- Pygame documentation: https://www.pygame.org/docs/
- `unittest` documentation: https://docs.python.org/3/library/unittest.html
- Liar's Bar rule inspiration: https://www.liarsbar.net/g/liars-bar-quick-start
