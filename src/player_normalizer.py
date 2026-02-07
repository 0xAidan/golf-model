"""
Normalize player names across all Betsperts CSV formats.

Betsperts uses two formats:
  - "Scottie Scheffler"   (playerName column)
  - "Scheffler, Scottie"  (Player column, last-first)

We normalize to a lowercase key like "scottie_scheffler" so every
CSV source joins on the same player regardless of format.
"""

import re
import unicodedata


def _strip_accents(s: str) -> str:
    """Remove accents/diacritics (e.g. Pavón → Pavon)."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(raw: str) -> str:
    """
    Convert any player name format to a stable key.

    "Scottie Scheffler"   → "scottie_scheffler"
    "Scheffler, Scottie"  → "scottie_scheffler"
    "Adrien Dumont de Chassart" → "adrien_dumont_de_chassart"
    """
    if not raw or not isinstance(raw, str):
        return ""
    name = raw.strip().strip('"')
    name = _strip_accents(name)

    # Handle "Last, First" format
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2:
            name = f"{parts[1]} {parts[0]}"

    # Lowercase, collapse whitespace, replace spaces with underscore
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)  # remove punctuation
    name = re.sub(r"\s+", "_", name)
    return name


def display_name(raw: str) -> str:
    """
    Convert any format to 'First Last' display name.

    "Scheffler, Scottie" → "Scottie Scheffler"
    "Scottie Scheffler"  → "Scottie Scheffler"
    """
    if not raw or not isinstance(raw, str):
        return ""
    name = raw.strip().strip('"')
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2:
            return f"{parts[1]} {parts[0]}"
    return name
