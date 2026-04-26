SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
WINDOW_TITLE = "Liar's Table"
TARGET_FPS = 60
PLAYER_COUNT = 5
STARTING_HAND_SIZE = 5
STARTING_REPUTATION = 50
MAX_REPUTATION = 100
MIN_REPUTATION = 0
REVOLVER_CHAMBERS = 6
SPECIAL_CARD_COPIES = 2
TABLE_BACKGROUND = (18, 24, 31)
TABLE_FELT = (27, 54, 46)
ACCENT_GOLD = (207, 175, 102)
TEXT_PRIMARY = (238, 231, 218)
TEXT_MUTED = (163, 155, 142)

DEALER_EVENT_LINES = {
    "elimination": (
        "One chair goes quiet.",
        "The room makes space for the dead.",
        "No one looks away fast enough.",
    ),
    "ghost_mode": (
        "Vesper finally focuses. The table notices too late.",
        "The Ghost decides the room has said enough.",
        "A still man becomes a threat all at once.",
    ),
    "blindfold_claim": (
        "Even the liar went in blind.",
        "A blind claim always sounds a little too brave.",
        "No one at the table knows what was really thrown there.",
    ),
    "memory_wipe": (
        "The table forgets what it swore it saw.",
        "Useful thing, panic. It erases cleanly.",
        "The memory goes dark and everyone hates it.",
    ),
    "wildcard_hand": (
        "He burned the hand and bought another chance.",
        "Nothing says desperation like asking the deck for mercy.",
        "Sometimes survival sounds like shuffling.",
    ),
    "shield_turn": (
        "Steel met luck and luck blinked first.",
        "The chamber wanted blood and found a shield instead.",
        "Protection looks cheap until it saves a life.",
    ),
    "misfire": (
        "The chamber spits smoke and mercy.",
        "A misfire is still a warning. The table heard it.",
        "The room exhales when the metal changes its mind.",
    ),
    "trusted_claim": (
        "A trusted voice buys itself dangerous room.",
        "They let that jump breathe because the name behind it still carries weight.",
        "Trust stretches the table wider than logic should allow.",
    ),
    "notorious_claim": (
        "That kind of reputation turns every claim into bait.",
        "No one hears a notorious player without reaching for doubt.",
        "The room treats a bad name like a warning bell.",
    ),
    "challenge_catches_bluff": (
        "At last, someone called the lie at the right time.",
        "The table rewards courage only when it arrives on schedule.",
        "A bluff lives until somebody finally looks at it properly.",
    ),
    "challenge_fails": (
        "The challenge broke first.",
        "Doubt moved too early and paid for it.",
        "The room respects certainty right up until it misses.",
    ),
}
