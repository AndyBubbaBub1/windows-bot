from tinkoff.invest import Client, MoneyValue
from tinkoff.invest.services import SandboxService

TOKEN = "t.VtxWp5QjcwbIQuqg7DYFFocZgtTRN2ofhqisP3cW8SptzsxLzuny5n2LILOjbVm7_o0PgWrFcDWKBAjQk5oqFA"  # вставь сюда свой песочничный токен

def main():
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

