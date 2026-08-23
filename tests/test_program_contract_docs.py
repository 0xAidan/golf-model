"""Contract-document validation tests for the repointed program file."""

from __future__ import annotations

import pytest

from backtester.autoresearch_config import (
    ContractValidationError,
    PROGRAM_PATH,
    validate_contract_documents,
)


def test_program_path_points_at_docs_research():
    assert PROGRAM_PATH.name == "PROGRAM.md"
    assert PROGRAM_PATH.parent.name == "research"


def test_validate_contract_documents_passes_on_real_docs():
    # The committed PROGRAM.md and evaluation_contract.md must satisfy markers.
    validate_contract_documents()


def test_validate_contract_documents_requires_sections(monkeypatch):
    def fake_read_text(*_args, **_kwargs):
        return "missing sections"

    monkeypatch.setattr("pathlib.Path.read_text", fake_read_text)
    with pytest.raises(ContractValidationError):
        validate_contract_documents()
