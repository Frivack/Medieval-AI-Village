# Amounts as models read them: coins, the copper total, and the per-unit
# price for more than one — so nobody has to convert silver in their head.
import pytest

from backend.utils.currency import to_string, with_copper


@pytest.mark.parametrize("copper, quantity, text", [
    (34, 2, "3s 4c (34c, 17c each)"),
    (140, 8, "14s (140c, 17.5c each)"),   # the "35c apiece" rumor started here
    (300, 1, "1g 10s (300c)"),
    (6, 1, "6c"),                          # copper only: nothing to convert
    (12, 2, "1s 2c (12c, 6c each)"),
    (0, 1, "0c"),
])
def test_with_copper(copper, quantity, text):
    assert with_copper(copper, quantity) == text


def test_to_string_is_unchanged_for_the_frontend_mirror():
    assert to_string(34) == "3s 4c" and to_string(3000) == "15g"
