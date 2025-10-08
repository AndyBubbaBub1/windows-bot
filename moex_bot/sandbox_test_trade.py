from tinkoff.invest import Client

TOKEN = "t.VtxWp5QjcwbIQuqg7DYFFocZgtTRN2ofhqisP3cW8SptzsxLzuny5n2LILOjbVm7_o0PgWrFcDWKBAjQk5oqFA"
ACCOUNT_ID = "e86fe048-ee57-4b00-b811-471a8821d0e3"

with Client(TOKEN) as client:
    print("=== Доступные акции ===")
    shares = client.instruments.shares().instruments
    tradable = [s for s in shares if s.api_trade_available_flag]
    for i, s in enumerate(tradable[:10], start=1):  # выводим первые 10
        print(f"{i}. {s.name} ({s.ticker}) FIGI={s.figi}")


