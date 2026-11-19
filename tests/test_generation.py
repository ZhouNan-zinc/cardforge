from src.generator import DEFAULT_THEME, balance_cards, generate_fallback


def test_fallback_card_set_is_valid():
    card_set = generate_fallback(DEFAULT_THEME, count=24, seed=1)
    assert len(card_set.cards) == 24
    assert len({card.id for card in card_set.cards}) == 24
    assert all(card.effects for card in card_set.cards)
    assert all(0 <= card.cost <= 3 for card in card_set.cards)


def test_balance_only_nudges_cards():
    card_set = generate_fallback(DEFAULT_THEME, count=24, seed=2)
    stats = {
        "card_stats": {
            card.id: {"plays": 10, "win_rate": 0.9 if i % 2 == 0 else 0.1}
            for i, card in enumerate(card_set.cards)
        }
    }
    balanced = balance_cards(card_set, stats)
    assert len(balanced.cards) == len(card_set.cards)
    assert balanced.source == "balanced"
