import re

import pandas as pd
import streamlit as st
from pathlib import Path

HERE = Path(__file__).parent

st.set_page_config(page_title='hedgerows_analysis', layout='wide')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Data files live next to this script and follow the naming pattern
# bank_<year>.xlsx / visa_<year>.xlsx. Any year with at least one file
# present is picked up automatically — to add 2025, just drop in
# bank_2025.xlsx and visa_2025.xlsx.

BANK_FILE = 'bank_{year}.xlsx'
VISA_FILE = 'visa_{year}.xlsx'
MAPPING_FILE = 'mapping.xlsx'

# Balance sheet balances at the END of the year BEFORE the earliest year of
# accounts. Later years don't need an entry: their opening balances are
# carried forward automatically from the previous year's closing trial
# balance. Only add an entry here to seed a year whose prior year has no
# data files.
SEED_PRIOR_BALANCES = {
    2024: {
        'stock': 40_833.17,
        'bank': 51_721.11,
        'other_loans': 50_627.35,
        'fixed_assets': 408,
    },
}

# One-off reclassifications: VAT transactions of exactly these amounts are
# recoded to Revenue Commissioners, per year. Add 2025 amounts as they are
# identified.
REVENUE_COMMISSIONERS_VAT_AMOUNTS = {
    2024: [13_050.00],
}

# VAT transactions below this absolute amount are treated as P35.
P35_VAT_THRESHOLD = 400

DEFAULT_STOCK_PCT = 95


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def discover_years():
    years = set()
    for pattern in ('bank_*.xlsx', 'visa_*.xlsx'):
        for f in HERE.glob(pattern):
            m = re.fullmatch(r'(?:bank|visa)_(\d{4})\.xlsx', f.name)
            if m:
                years.add(int(m.group(1)))
    return sorted(years)


def require_columns(df, cols, filename):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        st.error(
            f'{filename} is missing expected column(s) {missing}. '
            f'Columns found: {list(df.columns)}. '
            'Update the file headers (or this script) so they match.'
        )
        st.stop()


def load_mapping():
    mapping = pd.read_excel(HERE / MAPPING_FILE)
    mapping.columns = mapping.columns.str.strip()
    require_columns(mapping, ['Description', 'Account Description'], MAPPING_FILE)
    mapping['Description'] = mapping['Description'].str.strip()
    mapping = mapping.rename(columns={'Account Description': 'account_description'})
    mapping['_key'] = mapping['Description'].str.lower()
    mapping = mapping.dropna(subset=['_key'])
    mapping = mapping.drop_duplicates(subset=['_key'])
    return mapping


def load_sheet2():
    sheet2 = pd.read_excel(HERE / MAPPING_FILE, sheet_name='Sheet2')
    sheet2.columns = sheet2.columns.str.strip()
    require_columns(sheet2, ['Account Description', 'Stats_Group', 'PL_BS', 'Sorting'], f'{MAPPING_FILE} (Sheet2)')
    sheet2 = sheet2.rename(columns={'Account Description': 'account_description'})
    return sheet2


def load_visa(year, mapping):
    """Return (slim transactions, source total) for one year's visa file, or None if absent."""
    path = HERE / VISA_FILE.format(year=year)
    if not path.exists():
        return None
    visa = pd.read_excel(path)
    visa.columns = visa.columns.str.strip()
    require_columns(visa, ['Processed', 'Description', 'Paid out', 'Paid in'], path.name)
    visa['Processed'] = pd.to_datetime(visa['Processed'])
    visa = visa[visa['Processed'].dt.year == year]
    source_total = visa['Paid out'].fillna(0).sum() - visa['Paid in'].fillna(0).sum()

    visa['Description'] = visa['Description'].str.strip()
    visa['_key'] = visa['Description'].str.lower()
    visa = visa.merge(mapping[['_key', 'account_description']], on='_key', how='left').drop(columns='_key')

    slim = visa[['Processed', 'Description', 'Paid out', 'Paid in', 'account_description']].copy()
    slim.columns = ['date', 'description', 'debit', 'credit', 'account_description']
    slim['source'] = 'visa'
    return slim, source_total


def load_bank(year, mapping):
    """Return (slim transactions, source total) for one year's bank file, or None if absent."""
    path = HERE / BANK_FILE.format(year=year)
    if not path.exists():
        return None
    bank = pd.read_excel(path)
    bank.columns = bank.columns.str.strip()
    require_columns(bank, ['Posted Transactions Date', 'Description1', 'Debit Amount', 'Credit Amount'], path.name)
    bank['Posted Transactions Date'] = pd.to_datetime(bank['Posted Transactions Date'])
    bank = bank[bank['Posted Transactions Date'].dt.year == year]
    source_total = bank['Debit Amount'].fillna(0).sum() - bank['Credit Amount'].fillna(0).sum()

    bank['Description1'] = bank['Description1'].astype(str).where(bank['Description1'].notna()).str.strip()
    bank['_key'] = bank['Description1'].str.lower()
    bank = bank.merge(mapping[['_key', 'account_description']], on='_key', how='left').drop(columns='_key')

    slim = bank[['Posted Transactions Date', 'Description1', 'Debit Amount', 'Credit Amount', 'account_description']].copy()
    slim.columns = ['date', 'description', 'debit', 'credit', 'account_description']
    slim['source'] = 'bank'
    return slim, source_total


def load_all_years(years, mapping):
    """Load every year's files. Returns (combined transactions, source totals by year)."""
    frames = []
    source_totals = {}
    for year in years:
        total = 0.0
        for loader, label in ((load_bank, 'bank'), (load_visa, 'visa')):
            result = loader(year, mapping)
            if result is None:
                st.warning(f'No {label} file found for {year} ({label}_{year}.xlsx) — continuing without it.')
                continue
            slim, file_total = result
            frames.append(slim)
            total += file_total
        source_totals[year] = total
    combined = pd.concat(frames, ignore_index=True).sort_values('date').reset_index(drop=True)
    return combined, source_totals


# ---------------------------------------------------------------------------
# Coding rules
# ---------------------------------------------------------------------------

def apply_sales_mapping(combined):
    rules = [
        ('AIBMS|ATMLDG|STRIPE', 'Sales', dict(credit_gt=0.01)),
        ('RYANAIR|AERLING', 'Travel', {}),
        ('SHOPIFY', 'Purchases', {}),
        ('AIB MERCHANT', 'Visa Charges', {}),
        ('^500', 'Insurance', {}),
    ]
    for pattern, label, conditions in rules:
        mask = combined['account_description'].isna() & combined['description'].str.contains(pattern, na=False, regex=True)
        if conditions.get('credit_gt'):
            mask &= combined['credit'] > conditions['credit_gt']
        combined.loc[mask, 'account_description'] = label
    return combined


def apply_vat_reclasses(combined):
    """P35 for small VAT amounts; Revenue Commissioners for configured one-off amounts."""
    is_vat = combined['account_description'] == 'VAT'
    combined.loc[is_vat & (combined['amount'].abs() < P35_VAT_THRESHOLD), 'account_description'] = 'P35'

    rev_comm_mask = pd.Series(False, index=combined.index)
    for year, amounts in REVENUE_COMMISSIONERS_VAT_AMOUNTS.items():
        for amount in amounts:
            rev_comm_mask |= (
                (combined['account_description'] == 'VAT')
                & (combined['year'] == year)
                & (combined['amount'] == amount)
            )
    rev_comm = combined[rev_comm_mask].copy()
    combined.loc[rev_comm_mask, 'account_description'] = 'Revenue Commissioners'
    return combined, rev_comm


# ---------------------------------------------------------------------------
# Trial balance
# ---------------------------------------------------------------------------

def compute_trial_balance(year, summary, sort_keys, prior, stock_pct):
    """Build the trial balance for one year from its opening balances.

    Returns (tb dataframe, closing balances dict) — the closing balances feed
    the following year's trial balance.
    """
    filing_by_group = (
        summary[summary['year'] == year]
        .groupby('Stats_Group', dropna=False)['amount']
        .sum()
    )
    filing_total = filing_by_group.sum()
    pension_amount = filing_by_group.get('Pension', 0)
    personal_amount = filing_by_group.get('Personal', 0)

    fixed_assets_val = prior['fixed_assets']
    stock_amount = stock_pct / 100 * prior['stock']
    bank_amount = -filing_total + prior['bank']
    loans_closing = prior['other_loans'] - personal_amount
    other_loans_amount = -loans_closing
    filing_ex_pension = filing_total - pension_amount
    drawings_amount = -(filing_ex_pension + fixed_assets_val + stock_amount + bank_amount + other_loans_amount)

    tb_rows = []
    ordered = sort_keys.sort_values(['PL_BS', 'Sorting'], ascending=[False, True])
    for _, row in ordered.iterrows():
        group = row['Stats_Group']
        if group == 'Pension':
            continue
        tb_rows.append({'description': group, 'PL_BS': row['PL_BS'], 'amount': filing_by_group.get(group, 0)})

    for desc, pl_bs, amt in [
        ('Fixed Assets',  'BS', fixed_assets_val),
        ('Stock',         'BS', stock_amount),
        ('Bank',          'BS', bank_amount),
        ('Other Loans',   'BS', other_loans_amount),
        ('Drawings',      'BS', drawings_amount),
    ]:
        tb_rows.append({'description': desc, 'PL_BS': pl_bs, 'amount': amt})

    closing = {
        'stock': stock_amount,
        'bank': bank_amount,
        'other_loans': loans_closing,
        'fixed_assets': fixed_assets_val,
    }
    return pd.DataFrame(tb_rows), closing


def resolve_prior_balances(year, years_with_data, summary, sort_keys, stock_pct):
    """Opening balances for `year`: seeded from config, or carried forward by
    computing the previous year's trial balance (recursively).

    Returns (balances dict or None, list of note strings describing the chain).
    """
    if year in SEED_PRIOR_BALANCES:
        return SEED_PRIOR_BALANCES[year], []
    prior_year = year - 1
    if prior_year in years_with_data:
        prior_opening, notes = resolve_prior_balances(prior_year, years_with_data, summary, sort_keys, stock_pct)
        if prior_opening is None:
            return None, notes
        _, closing = compute_trial_balance(prior_year, summary, sort_keys, prior_opening, stock_pct)
        notes = notes + [f'Opening balances for {year} carried forward from the {prior_year} closing trial balance.']
        return closing, notes
    return None, []


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def style_numbers(df):
    num_cols = [c for c in df.select_dtypes(include='number').columns if c != 'year']
    fmt = {col: '{:,.0f}' for col in num_cols}
    return (
        df.style
        .format(fmt, na_rep='')
        .map(lambda v: 'color: red' if isinstance(v, (int, float)) and v < 0 else '', subset=num_cols)
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

st.title('Hedgerows Analysis')

years = discover_years()
if not years:
    st.error(f'No data files found in {HERE}. Expected files named like bank_2024.xlsx / visa_2024.xlsx.')
    st.stop()

mapping = load_mapping()
sheet2 = load_sheet2()
combined, source_totals = load_all_years(years, mapping)
combined = apply_sales_mapping(combined)

still_nan = combined[combined['account_description'].isna()]

combined['amount'] = combined['debit'].fillna(0) - combined['credit'].fillna(0)
combined['year'] = combined['date'].dt.year
combined, rev_comm = apply_vat_reclasses(combined)

cheques = combined[
    combined['description'].str.contains('^500', na=False, regex=True) &
    (combined['account_description'] == 'Insurance')
]

summary = (
    combined
    .groupby(['year', 'account_description'], dropna=False)['amount']
    .sum()
    .reset_index()
    .merge(sheet2, on='account_description', how='left')
    .sort_values(['year', 'PL_BS', 'Sorting'], ascending=[True, False, True])
)

sort_keys = (
    summary.dropna(subset=['Stats_Group'])
    .groupby('Stats_Group', as_index=False)
    .agg(PL_BS=('PL_BS', 'first'), Sorting=('Sorting', 'min'))
)

filing = (
    summary.dropna(subset=['Stats_Group'])
    .pivot_table(index='Stats_Group', columns='year', values='amount', aggfunc='sum')
    .reset_index()
    .merge(sort_keys, on='Stats_Group', how='left')
    .sort_values(['PL_BS', 'Sorting'], ascending=[False, True])
    .reset_index(drop=True)
)
filing.columns.name = None

if not cheques.empty:
    cheque_lines = ', '.join(f'{row.description} ({row.amount:,.0f})' for _, row in cheques.iterrows())
    st.info(f'Coding note: {len(cheques)} cheque payment(s) beginning with "500" have been automatically coded to Insurance — {cheque_lines}')

if not rev_comm.empty:
    rev_lines = ', '.join(f'{row.description} ({row.amount:,.2f})' for _, row in rev_comm.iterrows())
    st.info(f'Coding note: {len(rev_comm)} VAT transaction(s) have been automatically coded to Revenue Commissioners — {rev_lines}')

st.subheader('Summary by Year & Account')

for year in years:
    year_total = summary.loc[summary['year'] == year, 'amount'].sum()
    source_total = source_totals.get(year, 0)
    if round(year_total, 2) == round(source_total, 2):
        st.success(f'{year} sum check passed: summary total ({year_total:,.0f}) matches source files total ({source_total:,.0f})')
    else:
        st.error(f'{year} sum check FAILED: summary total ({year_total:,.0f}) does not match source files total ({source_total:,.0f})')

st.dataframe(style_numbers(summary), use_container_width=True)

st.subheader('Filing Accounts Table')
st.dataframe(style_numbers(filing), use_container_width=True)

st.subheader('Trial Balance')

tb_year = st.selectbox('Trial balance year', options=years, index=len(years) - 1)
stock_pct = st.number_input('Stock % of prior year', min_value=0, max_value=100, value=DEFAULT_STOCK_PCT, step=1)

prior_balances, carry_notes = resolve_prior_balances(tb_year, set(years), summary, sort_keys, stock_pct)

if prior_balances is None:
    st.warning(
        f'No opening balances available for {tb_year}: it has no entry in SEED_PRIOR_BALANCES '
        f'and there is no {tb_year - 1} data to carry forward from. '
        'Add a seed entry for it in SEED_PRIOR_BALANCES at the top of this script.'
    )
else:
    for note in carry_notes:
        st.caption(note)
    st.caption(f'Stock = {stock_pct}% × prior year value of {prior_balances["stock"]:,.2f}')

    tb, _ = compute_trial_balance(tb_year, summary, sort_keys, prior_balances, stock_pct)
    tb_total = tb['amount'].sum()

    if abs(round(tb_total, 2)) == 0:
        st.success('Trial Balance sums to zero')
    else:
        st.error(f'Trial Balance does NOT sum to zero — total = {tb_total:,.2f}')

    st.dataframe(style_numbers(tb), use_container_width=True)

st.subheader('All Transactions')
st.dataframe(style_numbers(combined), use_container_width=True)

st.subheader(f'Unmapped Transactions ({len(still_nan)})')
st.dataframe(style_numbers(still_nan), use_container_width=True)

st.subheader('Transaction Drill-Down')
options = sorted(combined['account_description'].dropna().unique().tolist())
selected = st.multiselect('Filter by Account Description', options=options)
if selected:
    filtered = combined[combined['account_description'].isin(selected)]
    st.dataframe(style_numbers(filtered), use_container_width=True)
