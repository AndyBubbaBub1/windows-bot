"""Alert dispatching utilities."""

from __future__ import annotations

import os
import smtplib
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Dict, List, Optional

import requests
import structlog

from .monitoring import record_alert_dispatch


logger = structlog.get_logger(__name__)


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int = 587
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = True
    sender: Optional[str] = None
    recipients: List[str] = field(default_factory=list)


class AlertDispatcher:
    """Dispatch alerts to multiple channels with rate limiting."""

    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        slack_webhook: Optional[str] = None,
        email: Optional[EmailConfig] = None,
        min_interval_seconds: int = 300,
    ) -> None:
        self.telegram_token = telegram_token or os.getenv('TELEGRAM_TOKEN')
        self.telegram_chat_id = telegram_chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.slack_webhook = slack_webhook or os.getenv('SLACK_WEBHOOK_URL')
        if email is None and os.getenv('ALERT_EMAIL_RECIPIENTS'):
            recipients = [addr.strip() for addr in os.getenv('ALERT_EMAIL_RECIPIENTS', '').split(',') if addr.strip()]
            email = EmailConfig(
                smtp_host=os.getenv('ALERT_SMTP_HOST', 'localhost'),
                smtp_port=int(os.getenv('ALERT_SMTP_PORT', '587')),
                username=os.getenv('ALERT_SMTP_USER'),
                password=os.getenv('ALERT_SMTP_PASSWORD'),
                use_tls=os.getenv('ALERT_SMTP_TLS', '1') not in {'0', 'false', 'False'},
                sender=os.getenv('ALERT_EMAIL_SENDER'),
                recipients=recipients,
            )
        self.email_config = email
        self.min_interval_seconds = max(1, min_interval_seconds)
        self._last_sent: Dict[str, float] = {}

    @classmethod
    def from_config(cls, cfg: Dict[str, object] | None) -> 'AlertDispatcher':
        cfg = cfg or {}
        email_cfg = cfg.get('email') if isinstance(cfg, dict) else None
        email = None
        if isinstance(email_cfg, dict):
            raw_port = email_cfg.get('smtp_port', 587)
            port = int(raw_port) if str(raw_port).strip() else 587
            email = EmailConfig(
                smtp_host=str(email_cfg.get('smtp_host', 'localhost')),
                smtp_port=port,
                username=email_cfg.get('username'),
                password=email_cfg.get('password'),
                use_tls=bool(email_cfg.get('use_tls', True)),
                sender=email_cfg.get('sender'),
                recipients=[str(r) for r in email_cfg.get('recipients', [])],
            )
        raw_interval = cfg.get('min_interval_seconds', 300)
        interval = int(raw_interval) if isinstance(raw_interval, (int, str)) and str(raw_interval).strip() else 300
        token = cfg.get('telegram_token') if isinstance(cfg.get('telegram_token'), str) else None
        chat_id = cfg.get('telegram_chat_id') if isinstance(cfg.get('telegram_chat_id'), str) else None
        webhook = cfg.get('slack_webhook') if isinstance(cfg.get('slack_webhook'), str) else None
        return cls(
            telegram_token=token or None,
            telegram_chat_id=chat_id or None,
            slack_webhook=webhook or None,
            email=email,
            min_interval_seconds=interval,
        )

    def _rate_limited(self, channel: str) -> bool:
        now = time.monotonic()
        last = self._last_sent.get(channel)
        if last is not None and now - last < self.min_interval_seconds:
            return True
        self._last_sent[channel] = now
        return False

    def send(self, message: str) -> None:
        if not message:
            return
        channels = []
        if self.telegram_token and self.telegram_chat_id:
            channels.append('telegram')
        if self.slack_webhook:
            channels.append('slack')
        if self.email_config and self.email_config.recipients:
            channels.append('email')
        for channel in channels:
            if self._rate_limited(channel):
                continue
            try:
                if channel == 'telegram':
                    self._send_telegram(message)
                elif channel == 'slack':
                    self._send_slack(message)
                elif channel == 'email':
                    self._send_email(message)
                record_alert_dispatch(channel)
            except Exception as exc:  # pragma: no cover - logging side effect
                logger.warning('failed to send alert', channel=channel, error=str(exc))

    def _send_telegram(self, message: str) -> None:
        url = f'https://api.telegram.org/bot{self.telegram_token}/sendMessage'
        requests.post(url, json={'chat_id': self.telegram_chat_id, 'text': message}, timeout=5)

    def _send_slack(self, message: str) -> None:
        requests.post(self.slack_webhook, json={'text': message}, timeout=5)

    def _send_email(self, message: str) -> None:
        if not self.email_config:
            return
        email = EmailMessage()
        email['Subject'] = 'MOEX bot alert'
        email['From'] = self.email_config.sender or (self.email_config.username or 'moex-bot@example.com')
        email['To'] = ', '.join(self.email_config.recipients)
        email.set_content(message)
        if self.email_config.use_tls:
            with smtplib.SMTP(self.email_config.smtp_host, self.email_config.smtp_port, timeout=10) as client:
                client.starttls()
                if self.email_config.username and self.email_config.password:
                    client.login(self.email_config.username, self.email_config.password)
                client.send_message(email)
        else:
            with smtplib.SMTP(self.email_config.smtp_host, self.email_config.smtp_port, timeout=10) as client:
                if self.email_config.username and self.email_config.password:
                    client.login(self.email_config.username, self.email_config.password)
                client.send_message(email)


__all__ = ['AlertDispatcher', 'EmailConfig']
