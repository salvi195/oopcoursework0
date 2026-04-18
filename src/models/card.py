import random

class Card:
    def init(self, suit, rank, value):
        self.suit = suit
        self.rank = rank
        self.value = value

    def repr(self):
        return f"{self.rank} of {self.suit}"

class Deck:
    def init(self):
        self.cards = []
        self.build_deck()

    def build_deck(self):
        suits = ["Hearts", "Diamonds", "Clubs", "Spades"]
        ranks = {"7": 7, "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
        for s in suits:
            for r, v in ranks.items():
                self.cards.append(Card(s, r, v))

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self):
        return self.cards.pop() if self.cards else None