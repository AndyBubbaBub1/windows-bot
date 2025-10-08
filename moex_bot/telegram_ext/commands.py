from __future__ import annotations
from typing import Tuple, Optional, List

HELP_TEXT = (
    "Команды:\n"
    "/help — помощь\n"
    "/status — баланс/позиции/доходность\n"
    "/buy <TICKER> <LOTS> — заявка на покупку (с подтверждением)\n"
    "/sell <TICKER> [LOTS] — заявка на продажу (если LOTS нет — все)\n"
    "/stop — экстренная остановка торговли"
)

def parse_order_args(text: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    parts: List[str] = text.strip().split()
    if len(parts) < 2:
        return None, None, "Укажите тикер"
    ticker = parts[1].upper()
    lots = 1
    if len(parts) >= 3:
        if not parts[2].isdigit():
            return None, None, "Количество должно быть целым числом"
        lots = int(parts[2])
        if lots <= 0:
            return None, None, "Количество должно быть > 0"
    return ticker, lots, None
