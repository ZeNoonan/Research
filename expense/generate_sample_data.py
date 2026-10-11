"""Generate made-up bank exports so finance_cash.py can be run and tested without real data.

Builds three years of fake transactions for a Visa card and a current account,
then writes them out the way the bank does: several downloads made on different
days, each reaching back only 24 months, in the bank's CSV layout (leading
spaces in the header, dd/mm/yyyy dates, amounts like "6,941.59", the current
account Balance printed on the last transaction of each day). Every download
also catches its last day part-way through - one made at 10am holds fewer of
that day's transactions than one made at 9pm.

Also writes coding_mapping.xlsx (Sheet1 Description -> Coding, Sheet2 Coding ->
Alt_Coding) and finance_config.json, with the opening balances at the start
date and the latest Visa balance worked out from the generated history.

Run:  python generate_sample_data.py      (rewrites ./sample_data)
"""

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent / 'sample_data'

HISTORY_START = date(2023, 10, 1)
HISTORY_END = date(2026, 10, 11)
START_DATE = date(2024, 2, 1)   # the fixed start date written to finance_config.json

# When each sample export was "downloaded" - the same rhythm as the real ones
CURRENT_ACCOUNT_DOWNLOADS = [datetime(2025, 12, 1, 10, 29), datetime(2026, 4, 1, 21, 9),
                             datetime(2026, 8, 1, 17, 9), datetime(2026, 10, 11, 12, 30)]
VISA_DOWNLOADS = [datetime(2026, 1, 19, 10, 28), datetime(2026, 5, 27, 21, 10),
                  datetime(2026, 9, 28, 17, 13), datetime(2026, 10, 11, 12, 31)]

CURRENT_ACCOUNT_HEADER = ['Posted Account', ' Posted Transactions Date', ' Description1', ' Description2',
                          ' Description3', ' Debit Amount', ' Credit Amount', 'Balance', 'Posted Currency',
                          'Transaction Type', 'Local Currency Amount', 'Local Currency']
VISA_HEADER = ['Masked Card Number', ' Transaction Date', ' Processed', ' Description', ' Paid out', ' Paid in']

# (probability per day, descriptions, amount range) for day-to-day Visa spending
VISA_SPENDING = [
    (0.35, ['TESCO STORES 3245', 'ALDI STORES 112', 'LIDL IRELAND GMBH', 'SUPERVALU RATHMINES',
            'DUNNES STORES CORNELSCOURT'], (15, 140)),
    (0.15, ['UBER *TRIP', 'BOLT.EU/O/2401', 'LUAS TICKET MACHINE'], (3, 30)),
    (0.07, ['AMZN MKTP DE*2041', 'AMZN MKTP DE*7730', 'AMZN MKTP DE*5512'], (10, 80)),
    (0.06, ['SEARSONS BAR', 'MANGAN BROS', 'ROTHAR BREWERY'], (15, 90)),
    (0.06, ['MAXOL SERVICE STATION', 'CIRCLE K FUEL'], (40, 90)),
    (0.05, ['SUPERMACS GALWAY', 'JUST EAT DUBLIN'], (12, 45)),
    (0.04, ['BOOTS IRELAND'], (6, 40)),
    (0.04, ['SUMUP *MARKET STALL', 'SQ *THE LOCAL SPOT', 'PAYPAL *EBAY'], (5, 60)),
    (0.03, ['PENNEYS MARY ST', 'RIVER ISLAND', 'REGATTA OUTDOOR'], (20, 120)),
    (0.03, ['ELM PARK GOLF CLUB'], (30, 60)),
    (0.01, ['HALLMARK CARDS DUNDRUM'], (4, 15)),
    (0.004, ['RYANAIR 0461234', 'AER LINGUS 0532'], (150, 600)),
]
CAFES = ['BUTLERS CHOCOLATE CAFE', 'COFFEE ANGEL', 'THIRD SPACE SMITHFIELD', 'BROWNES DELI']
COFFEE_PRICES = [3.50, 4.20, 4.50, 4.80]

# (day of month, description, amount) for Visa subscriptions
VISA_MONTHLY = [(3, 'CLAUDE.AI SUBSCRIPTION', 18.00), (9, 'GOOGLE *YOUTUBE PREMIUM', 13.99),
                (12, 'IRISH TIMES DIGITAL', 15.00), (15, 'NETFLIX.COM', 17.99), (20, 'SPOTIFY P1A2B3', 11.99)]

CODING_SHEET1 = [  # Description -> Coding for the descriptions the keyword rules don't catch
    ('ACME LTD SALARY', 'Salary (Income)'),
    ('DSP CHILD BENEFIT', 'Child Benefit'),
    ('D/D AVANT MONEY MORTGAGE', 'Mortgage'),
    ('D/D VIRGIN MEDIA IRELAND', 'Utilities'),
    ('D/D THREE IRELAND', 'phone'),
    ('VISA PAYMENT 4417', 'Visa Payment'),
    ('PAYMENT RECEIVED THANK YOU', 'Visa Payment'),
    ('BOOTS IRELAND', 'Household Sundries'),
    ('BOOTS IRELAND', 'Pharmacy'),   # listed twice on purpose: the app keeps the last one
    ('JUST EAT DUBLIN', 'Take-Away'),
    ('IRISH TIMES DIGITAL', 'Spotify/Computer/Newspaper'),
]
CODING_SHEET2 = [  # Coding -> Alt_Coding (friendlier names; several codings can share one)
    ('Groceries', 'Groceries'), ('Café', 'Coffee & Cafés'), ('Take-Away', 'Eating Out'),
    ('Social', 'Eating Out'), ('netflix', 'TV & Streaming'), ('TV', 'TV & Streaming'),
    ('Spotify/Computer/Newspaper', 'Subscriptions'), ('amazon', 'Online Shopping'),
    ('Transport', 'Transport'), ('Car', 'Car'), ('Utilities', 'Household Bills'),
    ('phone', 'Household Bills'), ('Mortgage', 'Mortgage'), ('Salary (Income)', 'Salary'),
    ('Child Benefit', 'Child Benefit'), ('Visa Payment', 'Visa Repayment'),
    ('Bank/Visa Charges', 'Bank Charges'), ('ATM Withdrawal', 'Cash'), ('Clothes', 'Clothes'),
    ('Golf', 'Golf'), ('Holidays', 'Holidays'), ('Pharmacy', 'Health'),
    ('Household Sundries', 'Household Bills'),
]


def simulate_history(seed=7):
    """Every transaction on both accounts, in the order they happened.

    Returns {'Visa': df, 'Current_Account': df}, each with Date, Description,
    cash_in, cash_out and balance_after (the account balance after that row).
    """
    rng = np.random.default_rng(seed)
    balance = {'Visa': -612.40, 'Current_Account': 3105.77}
    rows = {'Visa': [], 'Current_Account': []}
    visa_payment_due = None

    def add(account, day, description, cash_out=0.0, cash_in=0.0):
        cash_out, cash_in = round(cash_out, 2), round(cash_in, 2)
        balance[account] = round(balance[account] + cash_in - cash_out, 2)
        rows[account].append({'Date': pd.Timestamp(day), 'Description': description, 'cash_in': cash_in,
                              'cash_out': cash_out, 'balance_after': balance[account]})

    def amount(low, high):
        return float(rng.uniform(low, high))

    day = HISTORY_START
    while day <= HISTORY_END:
        # Current account
        if day.day == 1:
            add('Current_Account', day, 'D/D AVANT MONEY MORTGAGE', cash_out=1450.00)
        if day.day == 3:
            add('Current_Account', day, 'DSP CHILD BENEFIT', cash_in=140.00)
        if day.day == 5 and balance['Visa'] < 0:
            visa_payment_due = (day + timedelta(days=1), -balance['Visa'])
            add('Current_Account', day, 'VISA PAYMENT 4417', cash_out=-balance['Visa'])
        if day.day == 14 and day.month % 2 == 0:
            add('Current_Account', day, 'D/D ELECTRIC IRELAND', cash_out=amount(150, 260))
        if day.day == 18 and day.month % 2 == 1:
            add('Current_Account', day, 'D/D FLOGAS NATURAL GAS', cash_out=amount(90, 210))
        if day.day == 21:
            add('Current_Account', day, 'D/D VIRGIN MEDIA IRELAND', cash_out=65.00)
            add('Current_Account', day, 'D/D THREE IRELAND', cash_out=30.00)
        if day.day == 25:
            add('Current_Account', day, 'ACME LTD SALARY', cash_in=6941.59 if day.month == 12 else 4180.00)
        if day.day == 26:
            add('Current_Account', day, 'SO CREDIT UNION SAVINGS', cash_out=300.00)
        if day.day == 28 and day.month in (1, 4, 7, 10):
            add('Current_Account', day, 'ACCOUNT FEE', cash_out=12.00)
        if rng.random() < 0.04:
            add('Current_Account', day, 'ATM POINT CASH GRAFTON', cash_out=float(rng.choice([50, 100])))
        if rng.random() < 0.03:
            add('Current_Account', day, 'REVOLUT**8842*', cash_out=amount(50, 200))
        if rng.random() < 0.02:
            add('Current_Account', day, 'TRANSFER TO J MURPHY', cash_out=amount(20, 150))

        # Visa
        if visa_payment_due and visa_payment_due[0] == day:
            add('Visa', day, 'PAYMENT RECEIVED THANK YOU', cash_in=visa_payment_due[1])
            visa_payment_due = None
        for day_of_month, description, price in VISA_MONTHLY:
            if day.day == day_of_month:
                add('Visa', day, description, cash_out=price)
        if day.day == 28 and day.month in (3, 6, 9, 12):
            add('Visa', day, 'FEE-QTR GOVT STAMP DUTY', cash_out=7.50)
        if rng.random() < 0.45:
            # Sometimes the same coffee twice in a day: identical rows that are both real
            cafe, price = rng.choice(CAFES), float(rng.choice(COFFEE_PRICES))
            for _ in range(2 if rng.random() < 0.2 else 1):
                add('Visa', day, cafe, cash_out=price)
        for probability, descriptions, (low, high) in VISA_SPENDING:
            if rng.random() < probability:
                add('Visa', day, rng.choice(descriptions), cash_out=amount(low, high))
        if rng.random() < 0.01:
            add('Visa', day, 'AMZN MKTP DE*2041', cash_in=amount(10, 60))   # a refund

        day += timedelta(days=1)

    return {account: pd.DataFrame(account_rows) for account, account_rows in rows.items()}


def downloaded_rows(history, downloaded_at):
    """The rows a download made at `downloaded_at` contains: the previous 24
    months, plus only part of the download day itself."""
    download_day = pd.Timestamp(downloaded_at.date())
    first_day = download_day - pd.DateOffset(months=24)
    rows = history[(history['Date'] >= first_day) & (history['Date'] < download_day)]
    on_the_day = history[history['Date'] == download_day]
    return pd.concat([rows, on_the_day.head(len(on_the_day) * downloaded_at.hour // 24)])


def money(value):
    return f'{value:,.2f}' if value else ''


def write_export(history, account, downloaded_at, folder):
    rows = downloaded_rows(history, downloaded_at)
    path = folder / f'Transaction_Export_{downloaded_at:%d.%m.%Y_%H.%M}.csv'
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if account == 'Current_Account':
            writer.writerow(CURRENT_ACCOUNT_HEADER)
            last_of_day = ~rows['Date'].duplicated(keep='last')
            for row, is_last in zip(rows.itertuples(), last_of_day):
                writer.writerow(['93-11-22 00012345', f'{row.Date:%d/%m/%Y}', row.Description, '', '',
                                 money(row.cash_out), money(row.cash_in),
                                 money(row.balance_after) if is_last else '', 'EUR',
                                 'Debit' if row.cash_out else 'Credit', money(row.cash_out or row.cash_in), 'EUR'])
        else:
            writer.writerow(VISA_HEADER)
            for row in rows.itertuples():
                writer.writerow(['************4417', f'{row.Date - pd.Timedelta(days=1):%d/%m/%Y}',
                                 f'{row.Date:%d/%m/%Y}', row.Description, money(row.cash_out), money(row.cash_in)])
    return path


def opening_balance(history, start_date):
    """Balance at the start of `start_date`, before that day's transactions."""
    first = history[history['Date'] >= pd.Timestamp(start_date)].iloc[0]
    return round(first['balance_after'] - first['cash_in'] + first['cash_out'], 2)


def write_sample_data(out_dir=OUT_DIR, seed=7):
    """Write exports/, coding_mapping.xlsx and finance_config.json; return the full history."""
    history = simulate_history(seed)
    exports_dir = Path(out_dir) / 'exports'
    exports_dir.mkdir(parents=True, exist_ok=True)
    for old in exports_dir.glob('*.csv'):
        old.unlink()
    for account, downloads in [('Current_Account', CURRENT_ACCOUNT_DOWNLOADS), ('Visa', VISA_DOWNLOADS)]:
        for downloaded_at in downloads:
            write_export(history[account], account, downloaded_at, exports_dir)

    with pd.ExcelWriter(Path(out_dir) / 'coding_mapping.xlsx') as writer:
        pd.DataFrame(CODING_SHEET1, columns=['Description', 'Coding']).to_excel(writer, sheet_name='Sheet1', index=False)
        pd.DataFrame(CODING_SHEET2, columns=['Coding', 'Alt_Coding']).to_excel(writer, sheet_name='Sheet2', index=False)

    latest_visa = downloaded_rows(history['Visa'], VISA_DOWNLOADS[-1])
    config = {
        'start_date': START_DATE.isoformat(),
        'opening_balances': {account: opening_balance(history[account], START_DATE) for account in history},
        'visa_closing_balance': float(latest_visa['balance_after'].iloc[-1]),
    }
    (Path(out_dir) / 'finance_config.json').write_text(json.dumps(config, indent=2) + '\n')
    return history


if __name__ == '__main__':
    write_sample_data()
    print(f'Sample data written to {OUT_DIR}')
