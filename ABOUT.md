# About This Project

## What this is

This project is an always-on golf betting intelligence app.

It continuously:
- pulls tournament and player data from DataGolf,
- updates player rankings and model scores,
- evaluates matchup/value opportunities,
- refreshes the dashboard for live and upcoming tournaments.

## Why it exists

The goal is to remove manual workflows.

Instead of pressing buttons to get updated picks, the platform runs a 24/7 background refresh loop and surfaces the latest snapshot in the UI.

## What changed recently

The app now includes:
- a dedicated live-refresh runtime (`backtester/dashboard_runtime.py`),
- persisted refresh cadence settings (`src/live_refresh_policy.py`, `src/autoresearch_settings.py`),
- new live-refresh API endpoints in `app.py`,
- separate dashboard tabs for **Live Tournament** and **Upcoming Tournament**,
- visibility-aware polling and quieter development access logs,
- a dedicated `golf-live-refresh.service` for VPS deployment.

## How data flows

1. DataGolf endpoints are fetched on a cadence.
2. Model services recompute rankings and matchup edges.
3. Snapshot payload is written and exposed through API.
4. Frontend polls status/snapshot and re-renders live tables.

## Runtime model

The platform uses two complementary execution paths:
- **API process** (FastAPI app + dashboard)
- **Worker process** (live refresh loop for 24/7 updates)

On server deploy, `systemd` keeps these services running and restartable.

## Domain requirement

A domain is **not required** to operate the system.

You can run production from a Hetzner server IP first (for functional validation), then add a domain + HTTPS when you are ready for public access and trust signals.

## Intended audience

This repo is designed for:
- operator-style usage (you run and monitor a live model),
- iterative research and strategy tuning,
- long-running deployment where reliability and observability matter.
