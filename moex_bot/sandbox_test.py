"""Utility helpers for interacting with Tinkoff sandbox accounts.

The original script expected the third-party ``tinkoff`` package to be
installed.  The test environment that runs our automated checks does not have
this dependency which previously caused the import to fail during module
loading.  Instead of crashing, we now degrade gracefully by providing helpful
feedback when the dependency is missing.
"""

from __future__ import annotations

try:  # pragma: no cover - executed only when dependency is available
    from tinkoff.invest import Client, MoneyValue
    from tinkoff.invest.services import SandboxService
except ModuleNotFoundError:  # pragma: no cover - running without optional dependency
    Client = MoneyValue = SandboxService = None  # type: ignore[assignment]

    def _dependency_error() -> None:
        raise ModuleNotFoundError(
            "The 'tinkoff' package is required to run sandbox helpers. "
            "Install it with 'pip install tinkoff-investments' before running this script."
        )

TOKEN = "t.VtxWp5QjcwbIQuqg7DYFFocZgtTRN2ofhqisP3cW8SptzsxLzuny5n2LILOjbVm7_o0PgWrFcDWKBAjQk5oqFA"  # вставь сюда свой песочничный токен

def main():
    if Client is None:
        _dependency_error()

    with Client(TOKEN) as client:  # type: ignore[misc]
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

