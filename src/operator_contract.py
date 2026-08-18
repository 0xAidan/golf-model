"""Typed contracts for the lightweight operator read model."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, TypedDict


SCHEMA_VERSION = "operator-read-model/v1"

OperatorTrack = Literal["champion", "challenger"]
OperatorMode = Literal["live", "upcoming", "past"]


class DataState(str, Enum):
    FRESH = "fresh"
    REFRESHING = "refreshing"
    STALE = "stale"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


class ReasonContract(TypedDict):
    code: str
    message: str


class SourceContract(TypedDict, total=False):
    snapshot_id: str | None
    generated_at: str | None
    age_seconds: int | None
    stale_after_seconds: int | None
    section: str


class EventContract(TypedDict, total=False):
    event_id: str | None
    event_name: str | None
    course_name: str | None


class PicksContract(TypedDict):
    matchups: list[dict[str, Any]]
    value_bets: list[dict[str, Any]]


class BoardContract(TypedDict):
    schema_version: str
    track: OperatorTrack
    mode: OperatorMode
    state: str
    reason: ReasonContract
    event: EventContract
    source: SourceContract
    eligibility: dict[str, Any]
    rankings: list[dict[str, Any]]
    leaderboard: list[dict[str, Any]]
    picks: PicksContract


class BootstrapSectionContract(TypedDict):
    available: bool
    event_id: str | None
    event_name: str | None
    state: str
    reason: ReasonContract


class BootstrapContract(TypedDict):
    schema_version: str
    state: str
    reason: ReasonContract
    source: SourceContract
    tracks: dict[str, dict[str, BootstrapSectionContract]]
