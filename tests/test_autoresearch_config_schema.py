import pytest

from backtester.autoresearch_config import ContractValidationError, _validate_strategy_overrides


def test_strategy_overrides_reject_unknown_key():
    with pytest.raises(ContractValidationError):
        _validate_strategy_overrides({"bad_key": 1.0})


def test_strategy_overrides_reject_out_of_range():
    with pytest.raises(ContractValidationError):
        _validate_strategy_overrides({"kelly_fraction": 2.0})

