"""Shared result wording for both interfaces."""


def result_message(game):
    result = game.result
    if result.outcome == "tie":
        return f"{result.pot_count} cards in the pot. Everyone with cards continues on {result.stat}."
    if result.outcome == "shared":
        return "Nobody can contribute another card. The highest scorers share the win."
    name = game.players[result.collector].name
    collected = f"{name} collected {result.collected} cards."
    if result.outcome == "last_contributor":
        return f"{name} was the only player with another card. {collected}"
    return collected


def winners_message(game):
    names = [game.players[seat].name for seat in game.winners]
    return " and ".join((", ".join(names[:-1]), names[-1])) if len(names) > 1 else names[0]
