SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
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
DEALER_OPENING_LINES = (
    "Cards first. Regrets after.",
    "No one came here to be believed.",
    "The room is quiet. That never lasts.",
    "Keep your hands steady. The table is listening.",
    "Every honest claim sounds rehearsed in here.",
    "A bad room to tell the truth in.",
)

DEALER_VICTORY_LINES = (
    "The table keeps its final witness.",
    "The room chooses one name and forgets the others.",
    "A winner is only the last person still willing to sit here.",
    "The bar closes around one steady hand.",
    "All that noise for one survivor.",
)

DEALER_EVENT_LINES = {
    "opening_claim": (
        "The first claim sets the room's temperature.",
        "Someone had to open the night. That was the easy part.",
        "A table always pretends to be calm before the first lie lands.",
    ),
    "opening_bluff": (
        "Starting with a lie is bold. Staying alive after it is harder.",
        "First blood nearly always begins with confidence.",
        "Opening on a bluff means asking the room for mercy.",
    ),
    "big_jump": (
        "Too high, too fast. Someone wants the room dizzy.",
        "That jump was meant to stun, not persuade.",
        "Big claims are usually aimed at the nerves, not the cards.",
    ),
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
    "dante_overbluff_death": (
        "Dante leaned too hard on a bad lie and paid for it.",
        "The Bluffer finally believed his own story.",
        "Dante died the only way he ever meant to live: overcommitted.",
    ),
    "fox_theatrical_challenge": (
        "The Fox made a performance out of doubt.",
        "Even the challenge was staged for applause.",
        "The Fox called it like he was stepping into spotlight.",
    ),
    "mirror_damage": (
        "The mirror does not forgive a bad read.",
        "Risk changed hands without warning.",
        "The table hates a trick that works this cleanly.",
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
    "double_down": (
        "The stakes were doubled and someone still reached.",
        "Confidence always sounds expensive after Double Down.",
        "The room let one honest hand become a punishment.",
    ),
    "ash_mirror": (
        "Ash does not invent. He reflects.",
        "The Mimic offers the table its own habits back.",
        "Someone taught Ash that move by making it first.",
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