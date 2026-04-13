from pathlib import Path

from src.run_provenance import write_run_provenance


def test_write_run_provenance_includes_blend_and_quality(tmp_path: Path):
    output_path = write_run_provenance(
        event_name="Test Event",
        output_dir=str(tmp_path),
        strategy_meta={"strategy_source": "registry", "strategy_name": "test"},
        runtime_settings={"ev_threshold": 0.08},
        run_quality={"pass": True, "score": 0.91, "issues": []},
        value_bets={
            "top10": [
                {
                    "blend_dg_used": 0.9,
                    "blend_model_used": 0.1,
                    "is_value": True,
                }
            ]
        },
        source="unit-test",
    )

    path = Path(output_path)
    assert path.exists()
    payload = path.read_text(encoding="utf-8")
    assert '"source": "unit-test"' in payload
    assert '"top10"' in payload
    assert '"dg": 0.9' in payload
    assert '"model": 0.1' in payload
    assert '"score": 0.91' in payload
