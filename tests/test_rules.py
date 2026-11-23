from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from random import Random

import pytest

from relic.cards import STATS
from relic.room import Tables
from relic.rules import COMPUTER, Game, computer_choice
from relic.seed import seed_cards

FRAGILITY = "Fragility"


def accounted(game):
    cards = [card for player in game.players for card in player.pile] + list(game.pot)
    assert len(cards) == len(set(cards)) == 36
    assert set(cards) == set(game.deck)


def act(game, action, stat=None):
    assert game.act(game.revision, action, stat)
    accounted(game)


@pytest.mark.parametrize("humans, pile_size", [(1, 18), (2, 12), (3, 9)])
def test_deal_and_play_through_a_match(humans, pile_size):
    cards = tuple(seed_cards())
    names = ["Jo", "Sam", "Alex"][:humans]
    game = Game(names, cards, Random(152))
    second = Game(names, cards, Random(152))
    human_choices = Random(51)
    assert game.leader == (game.dealer + 1) % len(game.players)
    assert [player.name for player in game.players] == names + [COMPUTER]
    assert [player.computer for player in game.players] == [False] * humans + [True]
    assert all(len(player.pile) == pile_size for player in game.players)
    assert [p.pile for p in game.players] == [p.pile for p in second.players]
    accounted(game)

    for _ in range(5_000):
        if game.winners:
            break
        if game.phase == "handoff":
            assert game.private_card is None
            act(game, "reveal")
        elif game.phase == "choice":
            assert game.private_card.id == game.lead_player.pile[0]
            stat = human_choices.choice(tuple(STATS))
            act(game, "choose", stat)
        else:
            act(game, "continue")
    assert game.winners
    if len(game.winners) == 1:
        assert len(game.players[game.winners[0]].pile) == 36


def test_computer_uses_three_distinct_stats_and_random_tie_break():
    class ObservedRandom(Random):
        def __init__(self, seed):
            super().__init__(seed)
            self.sampled = []
            self.tied = []

        def sample(self, population, k):
            assert tuple(population) == tuple(STATS)
            assert k == 3
            self.sampled = super().sample(population, k)
            return self.sampled

        def choice(self, possibilities):
            self.tied = list(possibilities)
            return super().choice(possibilities)

    card = replace(next(seed_cards()), scores=(18, 29, 43, 59, 83, 100))
    rng = ObservedRandom(8)
    selected = computer_choice(card, rng)
    assert len(set(rng.sampled)) == 3
    assert selected == max(rng.sampled, key=card.score)
    assert selected == computer_choice(card, Random(8))
    assert card.score(selected) < 100

    card = replace(card, scores=(71,) * 6)
    choices = set()
    for seed in range(25):
        rng = ObservedRandom(seed)
        choices.add(computer_choice(card, rng))
        assert rng.tied == rng.sampled
    assert choices == set(STATS)


def staged_game(seat_scores):
    game = Game(["Jo", "Sam", "Alex"][:len(seat_scores) - 1], tuple(seed_cards()), Random(7))
    remaining = iter(game.deck)
    game.leader = 0
    for player, scores in zip(game.players, seat_scores):
        player.pile = deque()
        for score in scores:
            card_id = next(remaining)
            card = game.deck[card_id]
            game.deck[card_id] = replace(card, scores=(score, *card.scores[1:]))
            player.pile.append(card_id)
    game.pot = list(remaining)
    accounted(game)
    return game


def compare_fragility(game):
    act(game, "reveal")
    act(game, "choose", FRAGILITY)


def test_repeated_ties_include_lower_scorers_and_keep_the_stat():
    game = staged_game(((90, 75, 40, 35), (90, 50, 60), (50, 75, 96, 60)))
    game.players[0].pile.extend(game.pot)
    game.pot = []
    original_piles = [tuple(player.pile) for player in game.players]
    compare_fragility(game)
    assert game.result.outcome == "tie"
    assert game.result.pot_count == 3
    assert game.result.high_seats == (0, 1)
    act(game, "continue")
    assert game.result.outcome == "tie"
    assert game.result.pot_count == 6
    assert game.result.high_seats == (0, 2)
    act(game, "continue")
    assert game.result.stat == FRAGILITY
    assert game.round_number == 3
    assert game.result.collector == 2 and game.result.collected == 9
    assert not game.players[1].pile
    expected_cards = [original_piles[seat][comparison] for comparison in range(3) for seat in range(3)]
    assert list(game.players[2].pile) == [original_piles[2][3], *expected_cards]
    act(game, "continue")
    assert game.phase == "handoff" and game.leader == 2 and game.private_card is None


def test_winning_with_last_card_keeps_that_seat_in_the_match():
    game = staged_game(((96,), (25, 81)))
    compare_fragility(game)
    assert game.result.collector == 0
    assert [len(player.pile) for player in game.players] == [35, 1]
    assert game.winners == ()
    act(game, "continue")
    assert game.leader == 0


def test_single_remaining_contributor_takes_the_whole_pot_even_if_they_scored_lower():
    game = staged_game(((96,), (96,), (30, 10)))
    compare_fragility(game)
    assert game.result.outcome == "last_contributor"
    assert game.result.high_seats == (0, 1)
    assert game.result.collector == 2 and game.result.collected == 35
    assert game.winners == (2,) and not game.pot
    assert not game.act(game.revision, "continue")
    accounted(game)


def test_no_remaining_contributor_means_a_shared_win_among_top_scorers():
    game = staged_game(((71,), (93,), (93,)))
    compare_fragility(game)
    assert game.result.outcome == "shared"
    assert game.winners == (1, 2)
    assert len(game.pot) == 36
    assert not game.act(game.revision, "continue")
    accounted(game)


def test_parallel_clicks_play_only_one_round_and_do_not_reveal_the_next_card():
    game = staged_game(((95, 80), (30, 40)))
    tables = Tables()
    key = tables.start(game)
    assert not tables.act(key, 0, "choose", FRAGILITY)
    assert tables.act(key, 0, "reveal")

    def choose(_):
        return tables.act(key, 1, "choose", FRAGILITY)

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(choose, range(8))).count(True) == 1
    snapshot = tables.view(key)
    accounted(snapshot)
    assert snapshot.phase == "result" and snapshot.round_number == 1
    assert tables.act(key, 2, "continue")
    assert not tables.act(key, 2, "reveal")
    snapshot = tables.view(key)
    assert snapshot.phase == "handoff" and snapshot.private_card is None
    accounted(snapshot)
