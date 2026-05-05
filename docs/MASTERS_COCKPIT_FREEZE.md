# Masters-era Cockpit snapshot (operator `/`)

**Purpose:** Record what “roll back Cockpit to Masters” means in this repo for agents and operators.

**Anchor commits (April 2026, pre–full v5 on main snapshot):**

- `8964c75` — `fix: harden Masters readiness rankings and matchup trust` (Masters-week hardening).
- Parent of `8d246ad` (`feat(ab): add isolated v5 test lane and cockpit test tab`) — main live/upcoming path had **no parallel v5 default** on the operator snapshot; experimental v5 lived in a **separate lane** only.

**Current wiring (post-change):**

- **`live_tournament` / `upcoming_tournament`** use `config.COCKPIT_SNAPSHOT_MODEL_VARIANT` (default **`baseline`** via env `COCKPIT_SNAPSHOT_MODEL_VARIANT`, unset = baseline).
- **`lab_live_tournament` / `lab_upcoming_tournament`** use `profiles.yaml` → `live_refresh.lab_profile_name` (default `lab_sandbox`, typically **`model_variant: v5`**).
- **`legacy_tournament`** still uses `LEGACY_MODEL_VARIANT` (**baseline**). When the upcoming event matches the legacy target and cockpit is already baseline, the runtime **reuses** the upcoming analysis dict to avoid a duplicate baseline `run_snapshot_analysis`.

**Promote research to `/` again:** set `COCKPIT_SNAPSHOT_MODEL_VARIANT=v5` (or change the default in `src/config.py` with care) after you intentionally want operator boards on v5.
