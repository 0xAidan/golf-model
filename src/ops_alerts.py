"""Ops alerts for outages. ntfy first, Telegram as a fallback.

Set NTFY_TOPIC (and optional NTFY_SERVER, default https://ntfy.sh) to get
a phone notification. TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID still work.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger("golf.ops_alerts")


def ntfy_configured() -> bool:
    return bool((os.environ.get("NTFY_TOPIC") or "").strip())


def telegram_configured() -> bool:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return bool(token and chat)


def alerts_configured() -> bool:
    return ntfy_configured() or telegram_configured()


def send_ops_alert(title: str, body: str) -> dict[str, bool]:
    """Send a short ops message. Never raises."""
    sent = {"ntfy": False, "telegram": False}
    text = f"{title}\n{body}".strip()
    topic = (os.environ.get("NTFY_TOPIC") or "").strip()
    if topic:
        server = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        try:
            response = requests.post(
                f"{server}/{topic}",
                data=text.encode("utf-8"),
                headers={"Title": title[:80], "Priority": "high", "Tags": "warning"},
                timeout=10.0,
            )
            sent["ntfy"] = response.status_code < 300
            if not sent["ntfy"]:
                logger.warning("ntfy alert failed: status=%s", response.status_code)
        except requests.RequestException as exc:
            logger.warning("ntfy alert failed: %s", exc)

    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_raw = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if token and chat_raw:
        try:
            chat_id: str | int
            try:
                chat_id = int(chat_raw)
            except ValueError:
                chat_id = chat_raw
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text[:3900]},
                timeout=10.0,
            )
            sent["telegram"] = response.status_code == 200
            if not sent["telegram"]:
                logger.warning("Telegram ops alert failed: status=%s", response.status_code)
        except requests.RequestException as exc:
            logger.warning("Telegram ops alert failed: %s", exc)

    if not alerts_configured():
        logger.warning("Ops alert dropped (no NTFY_TOPIC or Telegram): %s", title)
    return sent
