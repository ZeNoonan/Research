"""Tests for the export stitching and for finance_cash.py end to end on sample data.

Checks:
  1. stitching every sample download rebuilds the generated history exactly,
     row for row and in order
  2. two identical transactions on one day are both kept
  3. a download that caught its last day part-way through is completed by the
     next download
  4. a download that starts part-way through a day is completed by the older one
  5. exports are recognised from their header, whatever the file is called;
     "6,941.59" amounts and balances become numbers; a newest-first file is
     put in date order; anything else is skipped
  6. a stretch no download covers is reported
  7. the daily balance check pins a missing transaction to its day
  8. the app runs on the sample data with every check passing, and the monthly
     table ties to the reconciliation (uncoded transactions included)
  9. the app warns when the exports don't reach back to the start date

Run:  pytest test_finance.py
"""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import bank_exports
import generate_sample_data

HERE = Path(__file__).resolve().parent
KEY = bank_exports.TRANSACTION_KEY


def transactions(rows, balances=None):
    """Build a read_export-style DataFrame from (date, description, cash_out) rows."""
    df = pd.DataFrame(rows, columns=['Date', 'Description', 'cash_out'])
    df['Date'] = pd.to_datetime(df['Date'])
    df['cash_in'] = 0.0
    if balances is not None:
        df['Current_acc_Balance'] = balances
    return df


def test_stitched_sample_matches_history(tmp_path):
    history = generate_sample_data.write_sample_data(tmp_path)
    exports, files = bank_exports.load_exports(tmp_path / 'exports')
    for account, downloads in [('Visa', generate_sample_data.VISA_DOWNLOADS),
                               ('Current_Account', generate_sample_data.CURRENT_ACCOUNT_DOWNLOADS)]:
        stitched = bank_exports.stitch(exports[account])
        # What the downloads between them hold: everything from the oldest one's
        # first day up to the moment the newest one was made
        full = history[account]
        newest = generate_sample_data.downloaded_rows(full, downloads[-1])
        first_day = files.loc[files['Account'] == account, 'First date'].min()
        expected = pd.concat([full[(full['Date'] >= first_day) & (full['Date'] < newest['Date'].min())], newest])

        pd.testing.assert_frame_equal(stitched[KEY].astype({'Description': object}).reset_index(drop=True),
                                      expected[KEY].astype({'Description': object}).reset_index(drop=True),
                                      check_dtype=False)
        assert files.loc[files['Account'] == account, 'Rows'].sum() > len(stitched)   # the overlaps were real


def test_identical_transactions_on_one_day_are_kept():
    day = [('2025-03-01', 'COFFEE ANGEL', 4.50), ('2025-03-01', 'COFFEE ANGEL', 4.50), ('2025-03-01', 'TESCO', 30.0)]
    older = transactions([('2025-02-28', 'LIDL', 12.0)] + day)
    newer = transactions(day + [('2025-03-02', 'ALDI', 20.0)])
    stitched = bank_exports.stitch([older, newer])
    assert (stitched['Description'] == 'COFFEE ANGEL').sum() == 2
    assert stitched['cash_out'].sum() == 12.0 + 4.50 + 4.50 + 30.0 + 20.0


def test_partial_last_day_is_completed_by_next_download():
    lunchtime = transactions([('2025-03-01', 'LIDL', 12.0), ('2025-03-02', 'COFFEE ANGEL', 4.50)],
                             balances=[100.0, 95.50])
    evening = transactions([('2025-03-01', 'LIDL', 12.0), ('2025-03-02', 'COFFEE ANGEL', 4.50),
                            ('2025-03-02', 'COFFEE ANGEL', 4.50), ('2025-03-02', 'TESCO', 30.0)],
                           balances=[100.0, None, None, 61.0])
    stitched = bank_exports.stitch([lunchtime, evening])
    assert stitched['cash_out'].tolist() == [12.0, 4.50, 4.50, 30.0]
    # The lunchtime balance belonged to what was then the day's last row; the later download's copy wins
    assert stitched['Current_acc_Balance'].tolist()[1:] == pytest.approx([float('nan'), float('nan'), 61.0], nan_ok=True)


def test_download_starting_part_way_through_a_day_is_completed_by_older_one():
    older = transactions([('2025-03-01', 'EARLY', 1.0), ('2025-03-01', 'LATE', 2.0)])
    newer = transactions([('2025-03-01', 'LATE', 2.0), ('2025-03-02', 'NEXT DAY', 3.0)])
    stitched = bank_exports.stitch([older, newer])
    assert stitched['Description'].tolist() == ['EARLY', 'LATE', 'NEXT DAY']


def test_read_export_recognises_files_and_parses_amounts(tmp_path):
    (tmp_path / 'current.csv').write_text(
        'Posted Account, Posted Transactions Date, Description1, Debit Amount, Credit Amount,Balance\n'
        '1,25/12/2025,ACME LTD SALARY,,"6,941.59","8,000.00"\n'
        '1,24/12/2025,TESCO,"1,058.41",,"1,058.41"\n')   # newest first
    (tmp_path / 'visa.csv').write_text(
        'Card, Processed, Description, Paid out, Paid in\n'
        '1,02/01/2026,NETFLIX.COM,17.99,\n'
        '1,03/01/2026,PAYMENT RECEIVED THANK YOU,,"1,200.00"\n')
    (tmp_path / 'something_else.csv').write_text('a,b\n1,2\n')

    account, current = bank_exports.read_export(tmp_path / 'current.csv')
    assert account == bank_exports.CURRENT_ACCOUNT
    assert current['Description'].tolist() == ['TESCO', 'ACME LTD SALARY']   # flipped to date order
    assert current['cash_in'].tolist() == [0, 6941.59]
    assert current['Current_acc_Balance'].tolist() == [1058.41, 8000.0]
    assert current['Date'].iloc[1] == pd.Timestamp('2025-12-25')

    account, visa = bank_exports.read_export(tmp_path / 'visa.csv')
    assert account == bank_exports.VISA
    assert visa['cash_in'].tolist() == [0, 1200.0]
    assert visa['Date'].iloc[0] == pd.Timestamp('2026-01-02')   # dd/mm, not mm/dd

    exports, files = bank_exports.load_exports(tmp_path)
    assert files.set_index('File')['Account'].to_dict() == {
        'current.csv': 'Current_Account', 'visa.csv': 'Visa',
        'something_else.csv': 'skipped: not a Visa or current account export'}


def test_coverage_gap_is_reported():
    files = pd.DataFrame({'First date': pd.to_datetime(['2024-01-01', '2024-06-01', '2025-03-01']),
                          'Last date': pd.to_datetime(['2025-12-31', '2026-01-31', '2027-02-28'])})
    assert bank_exports.coverage_gaps(files) == []
    files.loc[2, 'First date'] = pd.Timestamp('2026-03-01')
    assert bank_exports.coverage_gaps(files) == [(pd.Timestamp('2026-01-31'), pd.Timestamp('2026-03-01'))]


def test_daily_balance_check_pins_a_missing_transaction():
    current = transactions([('2025-03-01', 'A', 10.0), ('2025-03-02', 'B', 20.0), ('2025-03-03', 'C', 30.0)],
                           balances=[90.0, 70.0, 40.0])
    current['amount'] = -current['cash_out']
    assert (bank_exports.daily_balance_check(current, 100.0)['difference'] == 0).all()

    missing_b = current.drop(index=1)
    check = bank_exports.daily_balance_check(missing_b, 100.0)
    assert check.loc[check['difference'] != 0].index[0] == pd.Timestamp('2025-03-03')


def run_app(app_dir):
    return AppTest.from_file(str(app_dir / 'finance_cash.py'), default_timeout=120).run()


def messages(elements):
    """Message texts without the leading emoji (older Streamlit keeps it in .value)."""
    return [e.value.removeprefix('✅ ').removeprefix('❌ ') for e in elements]


def test_app_on_sample_data():
    at = run_app(HERE)
    assert not at.exception
    assert not at.error
    assert not at.warning
    assert messages(at.success) == [
        'Sum-preservation test passed', 'Reconciliation PASSED - Balances match!',
        "Current account agrees with the bank's balance at the end of all 307 days"]

    reconciliation = next(d.value for d in at.dataframe if 'Visa' in d.value.index)
    monthly = next(d.value for d in at.dataframe if 'Net Cash Movement' in d.value.index)
    assert 'Uncoded' in monthly.index
    assert monthly.loc['Closing Balance', 'Total'] == pytest.approx(
        reconciliation.loc['Total', 'Expected Closing Balance'])
    assert monthly.loc['Net Cash Movement', 'Total'] == pytest.approx(reconciliation.loc['Total', 'Transactions'])


def test_app_warns_when_exports_dont_reach_start_date(tmp_path):
    shutil.copy(HERE / 'finance_cash.py', tmp_path)
    shutil.copy(HERE / 'bank_exports.py', tmp_path)
    shutil.copytree(HERE / 'sample_data', tmp_path / 'sample_data')
    # Lose the oldest current account download: the rest only reach back to April 2024
    (tmp_path / 'sample_data' / 'exports' / 'Transaction_Export_01.12.2025_10.29.csv').unlink()

    at = run_app(tmp_path)
    assert not at.exception
    assert any('Current account exports only go back to 01 Apr 2024' in w.value for w in at.warning)
    assert 'Reconciliation FAILED' in messages(at.error)
