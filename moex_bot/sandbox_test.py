"""Utility script for working with a sandbox account.

The original version unconditionally imported the ``tinkoff`` package.  The
package is not installed in the test environment which caused an immediate
``ModuleNotFoundError`` during module import, preventing the rest of the
project's test suite from running.  To make the script more robust we now
guard the optional dependency and only surface an informative error message
when the script is executed directly.
"""

from __future__ import annotations

from typing import Optional

try:  # pragma: no cover - exercised indirectly via integration usage
    from tinkoff.invest import Client, MoneyValue
    from tinkoff.invest.services import SandboxService
    _IMPORT_ERROR: Optional[ModuleNotFoundError] = None
except ModuleNotFoundError as exc:  # pragma: no cover - exercised when optional dep missing
    Client = MoneyValue = SandboxService = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc

TOKEN = "t.VtxWp5QjcwbIQuqg7DYFFocZgtTRN2ofhqisP3cW8SptzsxLzuny5n2LILOjbVm7_o0PgWrFcDWKBAjQk5oqFA"  # вставь сюда свой песочничный токен

def main():
    if _IMPORT_ERROR is not None:
        raise RuntimeError(
            "The optional dependency 'tinkoff.invest' is required to work with "
            "the sandbox. Install it with 'pip install tinkoff-investments'."
        ) from _IMPORT_ERROR

    with Client(TOKEN) as client:
        print("=== Проверка sandbox аккаунтов ===")

        # получаем список sandbox аккаунтов
        accounts = client.sandbox.get_sandbox_accounts()

        if accounts.accounts:
            account_id = accounts.accounts[0].id
            print(f"✅ Найден существующий sandbox account_id: {account_id}")
        else:
            print("⚠️ Sandbox аккаунтов нет, создаём новый...")
            resp = client.sandbox.open_sandbox_account()
            account_id = resp.account_id
            print(f"✅ Создан новый sandbox account_id: {account_id}")

        # Пополняем счёт
        print("💰 Пополняем счёт на 100 000 ₽...")
        client.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount=MoneyValue(currency="rub", units=100000)
        )
        print("✅ Баланс пополнен")

        print("\n👉 Используй этот account_id в config.yaml:")
        print(account_id)

if __name__ == "__main__":
    main()

