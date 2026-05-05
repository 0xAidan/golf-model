"""v5 vs legacy AB-style comparison from ``market_prediction_rows``."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import config
from src import db


def _safe_filename_part(event_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(event_id or "").strip())
    return cleaned or "unknown_event"


def _row_identity(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(row.get("market_family") or ""),
        str(row.get("market_type") or ""),
        str(row.get("player_key") or ""),
        str(row.get("opponent_key") or ""),
        str(row.get("book") or ""),
    )


def _payload_variant(row: dict[str, Any]) -> str:
    payload = row.get("payload") or {}
    v = payload.get("model_variant")
    if v is None or str(v).strip() == "":
        return str(config.DEFAULT_MODEL_VARIANT)
    return str(v).strip().lower()


def _is_v5_lane_row(row: dict[str, Any]) -> bool:
    """Research / v5 challenger rows: lab_* sections (v5) or live/upcoming with v5 payload."""
    sec = (row.get("section") or "").strip().lower()
    if sec in {"lab_live", "lab_upcoming"}:
        return _payload_variant(row) == "v5"
    if sec in {"live", "upcoming"}:
        return _payload_variant(row) == "v5"
    return False


def _is_legacy_lane_row(row: dict[str, Any]) -> bool:
    """Reference / baseline rows: explicit legacy section or operator Cockpit live/upcoming (baseline)."""
    sec = (row.get("section") or "").strip().lower()
    if sec == "legacy":
        return True
    if sec in {"live", "upcoming"}:
        return _payload_variant(row) == "baseline"
    return False


def _latest_by_key(rows: list[dict[str, Any]], predicate) -> dict[tuple[str, ...], dict[str, Any]]:
    filtered = [r for r in rows if predicate(r)]
    filtered.sort(
        key=lambda r: (str(r.get("generated_at") or ""), int(r.get("id") or 0)),
        reverse=True,
    )
    out: dict[tuple[str, ...], dict[str, Any]] = {}
    for r in filtered:
        k = _row_identity(r)
        if k not in out:
            out[k] = r
    return out


def build_ab_report(
    event_id: str,
    *,
    output_dir: Path | None = None,
    write_files: bool = True,
    row_limit: int = 50_000,
) -> dict[str, Any]:
    """
    Load ``market_prediction_rows`` for ``event_id``, align **research v5** (``lab_*`` with
    v5, or legacy live/upcoming v5 rows) vs **reference baseline** (section ``legacy``, or
    operator ``live`` / ``upcoming`` with baseline payload), emit summary JSON (+ optional markdown).

    Returns a dict with counts, paired metrics, and optional ``artifact_paths``.
    """
    normalized = str(event_id or "").strip()
    if not normalized:
        return {"ok": False, "error": "event_id is required"}

    raw_rows = db.get_market_prediction_rows_for_event(normalized, limit=row_limit)
    v5_map = _latest_by_key(raw_rows, _is_v5_lane_row)
    legacy_map = _latest_by_key(raw_rows, _is_legacy_lane_row)

    keys_intersection = sorted(set(v5_map.keys()) & set(legacy_map.keys()))
    keys_v5_only = sorted(set(v5_map.keys()) - set(legacy_map.keys()))
    keys_legacy_only = sorted(set(legacy_map.keys()) - set(v5_map.keys()))

    prob_diffs: list[float] = []
    ev_diffs: list[float] = []
    paired_samples: list[dict[str, Any]] = []

    for key in keys_intersection:
        v_row = v5_map[key]
        l_row = legacy_map[key]
        mp_v = v_row.get("model_prob")
        mp_l = l_row.get("model_prob")
        ev_v = v_row.get("ev")
        ev_l = l_row.get("ev")
        if mp_v is not None and mp_l is not None:
            prob_diffs.append(float(mp_v) - float(mp_l))
        if ev_v is not None and ev_l is not None:
            ev_diffs.append(float(ev_v) - float(ev_l))
        paired_samples.append(
            {
                "key": {
                    "market_family": key[0],
                    "market_type": key[1],
                    "player_key": key[2],
                    "opponent_key": key[3],
                    "book": key[4],
                },
                "v5_model_prob": mp_v,
                "legacy_model_prob": mp_l,
                "v5_ev": ev_v,
                "legacy_ev": ev_l,
            }
        )

    def _mean(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 6) if vals else None

    summary = {
        "ok": True,
        "event_id": normalized,
        "row_limit": row_limit,
        "counts": {
            "raw_rows": len(raw_rows),
            "v5_keys": len(v5_map),
            "legacy_keys": len(legacy_map),
            "paired_keys": len(keys_intersection),
            "v5_only_keys": len(keys_v5_only),
            "legacy_only_keys": len(keys_legacy_only),
        },
        "paired_metrics": {
            "mean_model_prob_delta_v5_minus_legacy": _mean(prob_diffs),
            "mean_ev_delta_v5_minus_legacy": _mean(ev_diffs),
            "n_prob_pairs": len(prob_diffs),
            "n_ev_pairs": len(ev_diffs),
        },
        "paired_samples": paired_samples[:200],
        "truncated_paired_samples": len(paired_samples) > 200,
    }

    artifact_paths: dict[str, str] = {}
    if write_files:
        base = output_dir or Path("output/research/ab_reports")
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = f"ab_{_safe_filename_part(normalized)}_{stamp}"
        json_path = base / f"{stem}.json"
        md_path = base / f"{stem}.md"
        json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        lines = [
            f"# AB report: `{normalized}`",
            "",
            f"- Generated (UTC): `{stamp}`",
            f"- Raw rows loaded: **{len(raw_rows)}** (limit {row_limit})",
            f"- Paired keys (v5 ∩ legacy): **{len(keys_intersection)}**",
            "",
            "## Paired metrics (v5 − legacy)",
            "",
            f"- Mean Δ model_prob: `{summary['paired_metrics']['mean_model_prob_delta_v5_minus_legacy']}`",
            f"- Mean Δ ev: `{summary['paired_metrics']['mean_ev_delta_v5_minus_legacy']}`",
            "",
            "## Interpretation",
            "",
            "Rows are matched on `(market_family, market_type, player_key, opponent_key, book)` "
            "using the latest tick per lane (`generated_at`, `id`). "
            "v5 lane = section `lab_live` / `lab_upcoming` with v5 payload, or `live` / `upcoming` "
            "with `payload.model_variant == 'v5'`. "
            "Reference lane = section `legacy`, or `live` / `upcoming` with baseline payload "
            "(operator Cockpit after Masters-era split).",
            "",
        ]
        md_path.write_text("\n".join(lines), encoding="utf-8")
        artifact_paths["json"] = str(json_path)
        artifact_paths["markdown"] = str(md_path)

    if artifact_paths:
        summary["artifact_paths"] = artifact_paths

    return summary
