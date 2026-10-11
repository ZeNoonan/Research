"""Read the bank's CSV exports and stitch overlapping downloads into one history.

The bank only exports the last 24 months, so every download starts on a
different day. Rather than treat any one download as "the data", keep every
export you ever download, unchanged, in one folder. Each time the app runs this
module rebuilds a single continuous history from all of them:

- each file is recognised as Visa or current account from its header row, so
  the file names don't matter;
- overlapping downloads are combined without double counting (see stitch);
- coverage_gaps and daily_balance_check show whether the result is complete.
"""

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

VISA = 'Visa'
CURRENT_ACCOUNT = 'Current_Account'

# Export column (with the bank's leading spaces stripped) -> column name used in the app
EXPORT_COLUMNS = {
    VISA: {'Processed': 'Date', 'Description': 'Description',
           'Paid out': 'cash_out', 'Paid in': 'cash_in'},
    CURRENT_ACCOUNT: {'Posted Transactions Date': 'Date', 'Description1': 'Description',
                      'Debit Amount': 'cash_out', 'Credit Amount': 'cash_in',
                      'Balance': 'Current_acc_Balance'},
}

# What identifies a transaction across downloads. Balance is left out on purpose:
# a download made part-way through a day prints a balance on what was, at the
# time, that day's last transaction - a later download shows it without one.
TRANSACTION_KEY = ['Date', 'Description', 'cash_in', 'cash_out']


def to_number(values):
    """'6,941.59' -> 6941.59; blank -> NaN."""
    return pd.to_numeric(values.astype(str).str.replace(',', '', regex=False).str.strip(), errors='coerce')


def read_export(path):
    """Read one export file.

    Returns (account, transactions), or (None, None) when the header matches
    neither export layout. Transactions come back oldest first, with numeric
    cash_in / cash_out (blank = 0) and, for the current account, a numeric
    Current_acc_Balance (blank where the bank printed none).
    """
    columns = {c.strip() for c in pd.read_csv(path, nrows=0).columns}
    account = next((acc for acc, cols in EXPORT_COLUMNS.items() if set(cols) <= columns), None)
    if account is None:
        return None, None

    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.strip()
    df = df[list(EXPORT_COLUMNS[account])].rename(columns=EXPORT_COLUMNS[account])
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
    df['cash_in'] = to_number(df['cash_in']).fillna(0)
    df['cash_out'] = to_number(df['cash_out']).fillna(0)
    if 'Current_acc_Balance' in df:
        df['Current_acc_Balance'] = to_number(df['Current_acc_Balance'])

    # A newest-first file is flipped so the last row of a day is that day's latest
    if len(df) > 1 and df['Date'].iloc[0] > df['Date'].iloc[-1]:
        df = df.iloc[::-1]
    return account, df.reset_index(drop=True)


def downloaded_at(path):
    """When an export was made: from the bank's file name
    (Transaction_Export_28.09.2026_17.13.csv), else the file's modified time."""
    match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})_(\d{2})\.(\d{2})', path.name)
    if match:
        day, month, year, hour, minute = map(int, match.groups())
        return datetime(year, month, day, hour, minute)
    return datetime.fromtimestamp(path.stat().st_mtime)


def load_exports(folder):
    """Read every CSV in `folder`.

    Returns (exports, files):
      exports  {account: [transactions, ...]}, each list oldest download first
      files    one row per CSV: what it was recognised as and the dates it covers
    """
    found = []
    for path in sorted(Path(folder).glob('*.csv')):
        try:
            account, df = read_export(path)
            label = account or 'skipped: not a Visa or current account export'
        except (pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as error:
            account, df = None, None
            label = f'skipped: {error}'
        found.append({
            'File': path.name,
            'Account': label,
            'Rows': 0 if df is None else len(df),
            'First date': pd.NaT if df is None or df.empty else df['Date'].min(),
            'Last date': pd.NaT if df is None or df.empty else df['Date'].max(),
            'Downloaded': downloaded_at(path),
            'transactions': df,
        })

    files = pd.DataFrame(found, columns=['File', 'Account', 'Rows', 'First date', 'Last date',
                                         'Downloaded', 'transactions'])
    files[['First date', 'Last date']] = files[['First date', 'Last date']].apply(pd.to_datetime)
    files = files.sort_values(['Last date', 'Downloaded'], ignore_index=True)
    exports = {account: files.loc[files['Account'] == account, 'transactions'].tolist()
               for account in EXPORT_COLUMNS}
    return exports, files.drop(columns='transactions')


def stitch(downloads):
    """Combine overlapping downloads of one account into one history, each transaction once.

    `downloads` is a list of DataFrames from read_export, oldest download first.

    Two downloads that both cover a day list that day's transactions
    identically, so dropping repeated rows looks like the answer - but a day can
    genuinely hold two identical transactions (two 4.50 coffees in the same
    cafe), and both must stay. So each row is first numbered by how many times
    the same transaction has already appeared in its own file (0, 1, 2...), and
    duplicates are dropped on transaction + number. The second coffee is
    number 1 in every download that has it, so it is kept, while the overlap
    between downloads is counted once.

    The same rule completes a partial day: a download made at lunchtime is
    missing that afternoon's transactions, and the next download supplies them.
    Where several downloads hold a transaction, the latest download's copy is kept.
    """
    numbered = []
    for file_order, df in enumerate(downloads):
        df = df.copy()
        df['occurrence'] = df.groupby(TRANSACTION_KEY, dropna=False).cumcount()
        df['file_order'] = file_order
        df['row_order'] = range(len(df))
        numbered.append(df)

    combined = pd.concat(numbered, ignore_index=True)
    stitched = combined.drop_duplicates(TRANSACTION_KEY + ['occurrence'], keep='last')
    # Within a day, rows that only an older download has go first: a newer
    # download that starts part-way through a day is missing its earliest rows
    stitched = stitched.sort_values(['Date', 'file_order', 'row_order'], kind='stable')
    return stitched.drop(columns=['occurrence', 'file_order', 'row_order']).reset_index(drop=True)


def coverage_gaps(files):
    """Stretches no download covers, as (last covered date, next covered date) pairs.

    `files` is the load_exports table for one account. Coverage is judged from
    each file's first and last transaction, so a short gap can simply be a few
    days with no transactions; a long one means a download is missing.
    """
    gaps = []
    covered_to = None
    for first, last in files.dropna(subset=['First date']).sort_values('First date')[['First date', 'Last date']].itertuples(index=False):
        if covered_to is not None and first > covered_to + pd.Timedelta(days=1):
            gaps.append((covered_to, first))
        covered_to = last if covered_to is None else max(covered_to, last)
    return gaps


def daily_balance_check(transactions, opening_balance):
    """Re-add the current account from the opening balance and compare with the
    bank's own Balance at the end of every day.

    One row per day: the day's movement, the balance worked out from the
    opening balance plus every transaction so far, the last balance the bank
    printed that day, and the difference. A transaction missing from the
    stitched history, or counted twice, shows as a difference from that day on.
    """
    daily = transactions.groupby('Date').agg(movement=('amount', 'sum'),
                                             bank_balance=('Current_acc_Balance', 'last'))
    daily['calculated_balance'] = opening_balance + daily['movement'].cumsum()
    daily['difference'] = (daily['bank_balance'] - daily['calculated_balance']).round(2)
    return daily
