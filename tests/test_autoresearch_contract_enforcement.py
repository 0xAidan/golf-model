import pytest

from backtester.autoresearch_config import ContractValidationError, validate_contract_documents


def test_contract_docs_validation_requires_sections(monkeypatch):
    def fake_read_text(*_args, **_kwargs):
        return "missing sections"

    monkeypatch.setattr("pathlib.Path.read_text", fake_read_text)
    with pytest.raises(ContractValidationError):
        validate_contract_documents()

