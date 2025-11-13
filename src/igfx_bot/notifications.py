"""Notification utilities for messaging integrations."""

from __future__ import annotations

import time
from typing import Optional

import requests
from loguru import logger


class TelegramNotifier:
    """Send trading alerts via Telegram and optionally request confirmation."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        require_confirmation: bool = True,
        confirmation_timeout: int = 45,
        poll_interval: float = 2.0,
    ) -> None:
        self._session = requests.Session()
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id
        self._require_confirmation = require_confirmation
        self._confirmation_timeout = confirmation_timeout
        self._poll_interval = poll_interval
        self._last_update_id: Optional[int] = None

    def send_message(self, text: str, *, parse_mode: Optional[str] = None) -> None:
        payload = {"chat_id": self._chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = self._session.post(
                f"{self._base_url}/sendMessage", json=payload, timeout=10
            )
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - network/Telegram failures
            logger.warning(f"Telegram send_message failed: {exc}")

    def handle_trade_alert(
        self,
        *,
        symbol: str,
        direction: str,
        price: float,
        stop_loss: float,
        take_profit: float,
        size: float,
        price_format: str = "{:.5f}",
    ) -> bool:
        """Notify about a trade setup and optionally wait for confirmation."""

        summary = (
            "\n".join(
                [
                    "📈 Trade setup detected",
                    f"Symbol: {symbol}",
                    f"Direction: {direction}",
                    f"Entry: {price_format.format(price)}",
                    f"Stop Loss: {price_format.format(stop_loss)}",
                    f"Take Profit: {price_format.format(take_profit)}",
                    f"Size: {size}",
                ]
            )
        )

        if not self._require_confirmation:
            self.send_message(
                f"{summary}\n\nAuto-trading enabled – executing order without confirmation."
            )
            return True

        self.send_message(
            "\n".join(
                [
                    summary,
                    "",
                    (
                        "Reply with 'yes {symbol}' to approve or 'no {symbol}' to cancel "
                        "within the next {timeout}s."
                    ).format(symbol=symbol.upper(), timeout=self._confirmation_timeout),
                ]
            )
        )
        return self._await_confirmation(expected_symbol=symbol)

    def notify_execution(
        self,
        *,
        symbol: str,
        direction: str,
        price: float,
        size: float,
        deal_reference: Optional[str] = None,
        price_format: str = "{:.5f}",
    ) -> None:
        parts = [
            "✅ Trade executed",
            f"Symbol: {symbol}",
            f"Direction: {direction}",
            f"Fill: {price_format.format(price)}",
            f"Size: {size}",
        ]
        if deal_reference:
            parts.append(f"Deal ref: {deal_reference}")
        self.send_message("\n".join(parts))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _await_confirmation(self, *, expected_symbol: str) -> bool:
        deadline = time.monotonic() + float(self._confirmation_timeout)
        symbol_token = expected_symbol.lower()

        while time.monotonic() < deadline:
            for approved in self._consume_updates(symbol_token):
                return approved
            time.sleep(self._poll_interval)

        self.send_message(f"⏳ Trade request for {expected_symbol} timed out.")
        return False

    def _consume_updates(self, symbol_token: str):
        try:
            params = {}
            if self._last_update_id is not None:
                params["offset"] = self._last_update_id + 1
            resp = self._session.get(
                f"{self._base_url}/getUpdates", params=params, timeout=10
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:  # pragma: no cover - network/Telegram failures
            logger.warning(f"Telegram getUpdates failed: {exc}")
            return []

        results = payload.get("result", []) if isinstance(payload, dict) else []
        decisions = []
        for update in results:
            update_id = update.get("update_id")
            if update_id is not None:
                self._last_update_id = update_id

            message = update.get("message") or update.get("edited_message")
            if not message:
                continue

            text = (message.get("text") or "").strip().lower()
            if not text:
                continue

            tokens = text.split()
            if not tokens:
                continue

            decision = self._parse_decision(tokens, symbol_token)
            if decision is not None:
                decisions.append(decision)

        return decisions

    @staticmethod
    def _parse_decision(tokens, symbol_token: str) -> Optional[bool]:
        if len(tokens) == 1:
            command = tokens[0]
            if command in {"yes", "y"}:
                return True
            if command in {"no", "n"}:
                return False
            return None

        command, symbol = tokens[0], tokens[1]
        if symbol != symbol_token:
            return None
        if command in {"yes", "y", "buy", "long", "+"}:
            return True
        if command in {"no", "n", "sell", "short", "-"}:
            return False
        return None

