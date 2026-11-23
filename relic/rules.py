"""Rules and turn transitions. This module has no UI or database dependencies."""
from collections import deque
from dataclasses import dataclass
from random import Random

from relic.cards import STATS

DECK_SIZE = 36
COMPUTER = "Computer"
RULES = (
    "Choose a stat using only your top card. Highest wins for every stat, including "
    "Fragility, where 100 means especially delicate. Ratings are invented for the game.",
    "The winner puts the played cards and any pot at the bottom of their pile, "
    "then leads. An empty pile drops out after the comparison is resolved. "
    "Collect all 36 cards to win.",
    "If the high score ties, all played cards go into the pot. Everyone with cards "
    "compares their next card on the same stat, even if they scored lower before.",
    "If just one player can still contribute, they take the pot. If nobody can, "
    "the players tied for highest on the last comparison share the win.",
    "When the computer leads, it samples three different stats on its own card, "
    "calls the highest of those, and breaks equal choices at random.",
)


def computer_choice(card, rng):
    sample = rng.sample(tuple(STATS), 3)
    highest = max(card.score(stat) for stat in sample)
    return rng.choice([stat for stat in sample if card.score(stat) == highest])


@dataclass
class Player:
    name: str
    pile: deque
    computer: bool = False


@dataclass(frozen=True)
class Play:
    seat: int
    card_id: str
    score: int


@dataclass(frozen=True)
class Result:
    stat: str
    plays: tuple[Play, ...]
    high_seats: tuple[int, ...]
    collector: int | None
    collected: int
    pot_count: int
    outcome: str


class Game:
    def __init__(self, humans, cards, rng=None):
        names = [name.strip() for name in humans]
        all_names = names + [COMPUTER]
        if not 1 <= len(names) <= 3 or any(not name or len(name) > 30 for name in names):
            raise ValueError("Enter names of 1 to 30 characters for one to three humans.")
        if len({name.casefold() for name in all_names}) != len(all_names):
            raise ValueError("Use a different name for each human. Computer is reserved.")
        self.deck = {card.id: card for card in cards}
        if len(cards) != DECK_SIZE or len(self.deck) != DECK_SIZE:
            raise ValueError("A match needs exactly 36 distinct cards.")
        self.rng = rng if rng is not None else Random()
        shuffled = list(self.deck)
        self.rng.shuffle(shuffled)
        self.players = [Player(name, deque()) for name in names] + [
            Player(COMPUTER, deque(), computer=True)
        ]
        self.dealer = self.rng.randrange(len(self.players))
        self.leader = (self.dealer + 1) % len(self.players)
        for index, card_id in enumerate(shuffled):
            seat = (self.leader + index) % len(self.players)
            self.players[seat].pile.append(card_id)
        self.pot = []
        self.winners = ()
        self.result = None
        self.phase = "handoff"
        self.round_number = 1
        self.revision = 0

    @property
    def lead_player(self):
        return self.players[self.leader]

    @property
    def private_card(self):
        if self.phase == "choice":
            return self.deck[self.lead_player.pile[0]]
        return None

    def act(self, revision, action, stat=None):
        """An action belongs to one screen. A stale click can never replay a round."""
        if revision != self.revision:
            return False
        if self.phase == "handoff" and action == "reveal":
            if self.lead_player.computer:
                card = self.deck[self.lead_player.pile[0]]
                self._compare(computer_choice(card, self.rng))
            else:
                self.phase = "choice"
        elif self.phase == "choice" and action == "choose" and stat in STATS:
            self._compare(stat)
        elif self.phase == "result" and action == "continue" and not self.winners:
            self.round_number += 1
            if self.result.outcome == "tie":
                self._compare(self.result.stat)
            else:
                self.phase = "handoff"
                self.result = None
        else:
            return False
        self.revision += 1
        return True

    def _compare(self, stat):
        plays = []
        for seat, player in enumerate(self.players):
            if player.pile:
                card_id = player.pile.popleft()
                plays.append(Play(seat, card_id, self.deck[card_id].score(stat)))
        highest = max(play.score for play in plays)
        tied = tuple(play.seat for play in plays if play.score == highest)
        self.pot.extend(play.card_id for play in plays)
        collector = None
        collected = 0
        outcome = "win"
        if len(tied) == 1:
            collector = tied[0]
        else:
            remaining = [seat for seat, player in enumerate(self.players) if player.pile]
            if len(remaining) > 1:
                outcome = "tie"
            elif remaining:
                outcome = "last_contributor"
                collector = remaining[0]
            else:
                outcome = "shared"
                self.winners = tied
        if collector is not None:
            pile = self.players[collector].pile
            collected = len(self.pot)
            # Keep older pot cards in front of this comparison's cards.
            pile.extend(self.pot)
            self.pot.clear()
            self.leader = collector
            if len(pile) == DECK_SIZE:
                self.winners = (collector,)
        self.result = Result(stat, tuple(plays), tied, collector, collected, len(self.pot), outcome)
        self.phase = "result"
