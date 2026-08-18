# Operator Site Recovery Context

This is a single-operator golf analytics cockpit. Its two intentionally
isolated tracks are **Champion** (the operating reference) and **Challenger**
(the evaluated alternative).

- **Dashboard** is the Champion workspace. **Lab** is the Challenger workspace.
- The public site has no authentication; this is an accepted operating risk.
- The UI is a dark-only, professional analytics product—never a faux terminal
  and never theme-switchable.
- **Compare** shows current-event disagreement only. **Results** shows
  historical A/B evidence. Neither declares a track winner.
- Lab data is Challenger-only. It must never fall back to Champion data.
- Grading is automatic only; the operator can observe grade state but does not
  manually grade rows from the site.

The recovery acceptance gates are in
[`docs/frontend-recovery/acceptance.md`](docs/frontend-recovery/acceptance.md).
The implementation sequence is the **operator-site-recovery** Cursor plan; do
not edit that plan from implementation PRs.
