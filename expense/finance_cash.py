import json
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st
from difflib import get_close_matches

import bank_exports


st.set_page_config(layout="wide",page_title = "Finance Cash Flow Analysis")

# -----------------------
# Data folder
# -----------------------
# Everything personal lives in this folder, outside the repo (the repo is public):
#   exports/              every Transaction_Export_*.csv ever downloaded, Visa and current account
#                         together. Never edit or delete them: they hold the history the bank drops
#   coding_mapping.xlsx   Sheet1 Description -> Coding, Sheet2 Coding -> Alt_Coding
#   finance_config.json   fixed start date, opening balances at that date, latest Visa balance
# README.md has the routine for each visit to the bank.
MY_DATA_DIR = Path('C:/Users/Darragh/Documents/Finance')
SAMPLE_DATA_DIR = Path(__file__).resolve().parent / 'sample_data'

use_sample_data = st.sidebar.checkbox('Use sample data', value=not MY_DATA_DIR.exists())
DATA_DIR = SAMPLE_DATA_DIR if use_sample_data else MY_DATA_DIR
if use_sample_data:
    st.info(f"Showing made-up sample data from {SAMPLE_DATA_DIR}")

config_path = DATA_DIR / 'finance_config.json'
if not config_path.exists():
    st.error(f"No finance_config.json in {DATA_DIR}. Copy the one in sample_data and put in your own "
             "start date and opening balances (see README.md).")
    st.stop()
config = json.loads(config_path.read_text())
START_DATE = pd.Timestamp(config['start_date'])

# -----------------------
# Load every export and stitch the downloads together
# -----------------------
# The bank only exports the last 24 months, so each download starts on a different day.
# Instead of reading one file per account, every download in exports/ is read and
# bank_exports rebuilds one continuous history from them all, counting the overlaps once.
# Everything before START_DATE is then dropped, so the opening balances never move.
exports, export_files = bank_exports.load_exports(DATA_DIR / 'exports')

st.subheader("Bank Exports Used")
st.write(f"Fixed start date: **{START_DATE:%d %b %Y}** (from finance_config.json)")
st.dataframe(export_files, hide_index=True, column_config={
    'First date': st.column_config.DateColumn(format='D MMM YYYY'),
    'Last date': st.column_config.DateColumn(format='D MMM YYYY'),
    'Downloaded': st.column_config.DatetimeColumn(format='D MMM YYYY HH:mm'),
})

if export_files['Account'].str.startswith('skipped').any():
    st.warning("Some files in exports/ were skipped - see the Account column above")

account_labels = {bank_exports.VISA: 'Visa', bank_exports.CURRENT_ACCOUNT: 'Current account'}
for account, label in account_labels.items():
    files = export_files[export_files['Account'] == account]
    if files.empty:
        st.error(f"No {label} exports found in {DATA_DIR / 'exports'}")
        st.stop()
    if files['First date'].min() > START_DATE:
        st.warning(f"{label} exports only go back to {files['First date'].min():%d %b %Y}, after the start date. "
                   "Any transactions in between are missing, so the opening balance won't hold.")
    for covered_to, resumes in bank_exports.coverage_gaps(files):
        st.warning(f"{label}: no export covers {covered_to:%d %b %Y} to {resumes:%d %b %Y}. "
                   "If there were transactions in between, they are missing.")

last_dates = export_files.groupby('Account')['Last date'].max()
if abs(last_dates[bank_exports.VISA] - last_dates[bank_exports.CURRENT_ACCOUNT]) > pd.Timedelta(days=3):
    st.warning(f"Visa runs to {last_dates[bank_exports.VISA]:%d %b %Y} but the current account to "
               f"{last_dates[bank_exports.CURRENT_ACCOUNT]:%d %b %Y} - download both so the months line up")

visa_transactions = bank_exports.stitch(exports[bank_exports.VISA])
current_acc_transactions = bank_exports.stitch(exports[bank_exports.CURRENT_ACCOUNT])

visa_transactions = visa_transactions[visa_transactions['Date'] >= START_DATE].copy()
current_acc_transactions = current_acc_transactions[current_acc_transactions['Date'] >= START_DATE].copy()


mapping = pd.read_excel(DATA_DIR / 'coding_mapping.xlsx',usecols=['Description','Coding'], sheet_name='Sheet1')

# Bring the visa_transactions and current_acc_trasactions together
# Next merge the mapping file into this dataframe to get the coding
# Please make sure that the 'cash_in' and 'cash_out' columns are numeric and not object type
# Next add an 'amount' column that is cash_in - cash_out
# Generate a test so that we can be satfishied that the merge worked as intended
# what i like to do is a sum-preservation test, so please write a test that checks that the 'amount' column is the same before and after the merge
# Providing the test passes, the next thing is to examine the dataframe after the merge to look at the dataframe filtered on the coding column where coding is null
# to see what code next needs to be generated to categorise these transactions


# -----------------------
# Combine transactions
# -----------------------

visa_transactions['source'] = 'Visa'
current_acc_transactions['source'] = 'Current_Account'


# -----------------------
# Parsing to numeric and fillna
# -----------------------

# Done in bank_exports.read_export: the thousand separators ("6,941.59") are stripped
# from cash_in, cash_out and Balance before converting to numbers.


visa_transactions['amount'] = visa_transactions['cash_in'] - visa_transactions['cash_out']
current_acc_transactions['amount'] = current_acc_transactions['cash_in'] - current_acc_transactions['cash_out']

# st.write(f"Sum of visa transactions amount: {visa_transactions['amount'].sum():,.0f}")
# st.write(f"Sum of current account transactions amount: {current_acc_transactions['amount'].sum():,.0f}")
# st.write('current account', current_acc_transactions)

transactions = pd.concat(
    [visa_transactions, current_acc_transactions],
    ignore_index=True
)

# -----------------------
# Ensure numeric types
# -----------------------
transactions['cash_in'] = pd.to_numeric(transactions['cash_in'], errors='coerce').fillna(0)
transactions['cash_out'] = pd.to_numeric(transactions['cash_out'], errors='coerce').fillna(0)



# -----------------------
# Add amount column
# -----------------------
# transactions['amount'] = transactions['cash_in'] - transactions['cash_out']
# st.write('sum of transactions amount:', transactions['amount'].sum())

# -----------------------
# CHECK mapping uniqueness
# -----------------------
duplicate_descriptions = (
    mapping['Description']
    .value_counts()
    .loc[lambda x: x > 1]
)

# -----------------------
# Deduplicate mapping (KEEP LAST)
# -----------------------
mapping_deduped = mapping.drop_duplicates(
    subset='Description',
    keep='last'
)

# -----------------------
# Sum before merge
# -----------------------
amount_sum_before_merge = transactions['amount'].sum()

# -----------------------
# Merge with deduped mapping
# -----------------------
transactions_merged = transactions.merge(
    mapping_deduped,
    on='Description',
    how='left',
    validate='many_to_one'   # 🔒 prevents silent duplication
)

# -----------------------
# Sum-preservation test
# -----------------------
amount_sum_after_merge = transactions_merged['amount'].sum()

assert np.isclose(
    amount_sum_before_merge,
    amount_sum_after_merge
), "❌ Sum-preservation test failed: row duplication detected"
# A duplicated row can leave the sum unchanged when it nets to zero, so check the row count too
assert len(transactions_merged) == len(transactions), "❌ Row count changed in the merge"

st.success("✅ Sum-preservation test passed")




# -----------------------
# Examine uncoded transactions
# -----------------------
uncoded_transactions = transactions_merged[
    transactions_merged['Coding'].isna()
].sort_values('Description')


# -----------------------
# Keyword-based coding rules and in lowercase for matching
# -----------------------
KEYWORD_RULES = {
    'tesco': 'Groceries',
    'aldi': 'Groceries',
    'dunnes': 'Groceries',
    'lidl': 'Groceries',
    'centra': 'Groceries',
    'supervalu': 'Groceries',
    'sv': 'Groceries',
    'netflix': 'netflix',
    'spotify': 'Spotify/Computer/Newspaper',
    'uber': 'Transport',
    'bolt': 'Transport',
    'fuel': 'Transport',
    'luas': 'Transport',
    'electric': 'Utilities',
    'gas': 'Utilities',
    'internet': 'Utilities',
    'greyhound': 'Utilities',
    'phone': 'phone',
    'amazon': 'amazon',
    'amzn': 'amazon',
    'claude': 'amazon',
    ' car ': 'Car',
    'car': 'Car',
    'maxol': 'Car',
    'mizuno': 'Clothes',
    'autoservice': 'Car',
    'butlers': 'Café',
    'brewery': 'Social',
    'cafe': 'Café',
    'fee-qtr': 'Bank/Visa Charges',
    'independent.ie': 'Spotify/Computer/Newspaper',
    'garden': 'Household Sundries',
    'point cash': 'ATM Withdrawal',
    'bus stop': 'Café',
    'penneys': 'Clothes',
    'wimbledon' : 'UK',
    'golf' : 'Golf',
    'pierced' : 'Anna',
    'cloud picker' : 'Café',
    'mangan' : 'Social',
    'regatta' : 'Clothes',
    'organic' : 'Groceries',
    'ryanair' : 'Holidays',
    'gatwick' : 'UK',
    'coffee' : 'Café',
    'armour' : 'Clothes',
    'temple hair' : 'Beauty/Hair',
    'temple' : 'Take-Away',
    'art and hobby' : 'Anna',
    'supermac' : 'Take-Away',
    'smyths toys' : 'Presents',
    'revolut' : 'Social',
    'hubbard' : 'Café',
    'kildare village' : 'Clothes',
    'symths' : 'Social',
    'blooming' : 'Presents',
    'searsons' : 'Social',
    'puma' : 'Clothes',
    'account fee' : 'Bank/Visa Charges',
    'gran canaria' : 'Holidays',
    'aeropuerto' : 'Holidays',
    'wildlands' : 'Holidays',
    'aer lingus' : 'Holidays',
    'youtube' : 'TV',
    'debbie' : 'Andrew',
    'brownes' : 'Café',
    'sourdough' : 'Café',
    'jewellers' : 'Present',
    'third space' : 'Café',
    'irish rail' : 'Social',
    'harvey norman' : 'Household Sundries',
    'river island' : 'Clothes',
    
}


# So focus on the uncoded transactions dataframe
# for the above keywords, if any of them appear in the description (case insensitive)
# then we can assign the corresponding coding to that transaction
# can you then display the dataframe where the Coding is blank so I can focus on that further
# Can you make the change so that this coding is applied, so it's just the uncoded transactions that I need to look at 

def keyword_based_coding(description):
    """Apply keyword-based coding rules to a description."""
    if not isinstance(description, str):
        return None

    desc = description.lower()
    for keyword, coding in KEYWORD_RULES.items():
        if keyword in desc:
            return coding
    return None


# -----------------------
# Apply keyword-based coding to uncoded transactions
# -----------------------
mask_uncoded = transactions_merged['Coding'].isna()

transactions_merged.loc[mask_uncoded, 'Coding'] = (
    transactions_merged.loc[mask_uncoded, 'Description']
    .apply(keyword_based_coding)
)

# -----------------------
# Display only transactions that are still uncoded
# -----------------------
still_uncoded = transactions_merged[
    transactions_merged['Coding'].isna()
].sort_values('Description')

st.subheader("Transactions Still Missing Coding (After Keyword Rules)")
st.dataframe(still_uncoded)


st.subheader("All Transactions")
st.dataframe(transactions_merged)

# Now we are going to do get a reconciliation of the transactions_merged dataframe
# First information is that we have two Opening Balances, one from Visa and one from Current Account
# The Opening Balances are at the fixed start date and come from finance_config.json
# The net Closing Balance is the amount in the 'Current_acc_Balance' column for the most recent date plus
# Now sum up the total of the amounts in the 'amount' column
# Finally we can do a test to check that Opening Balance + sum of amounts = Closing Balance
# If the test passes, we can display a message saying that the reconciliation passed, otherwise we display a message saying that it failed
# If it fails, please show the Opening Balance, the sum of amounts, the Closing Balance and difference so it can be debugged

# -----------------------
# Reconciliation
# -----------------------
st.subheader("Reconciliation")

# Opening balances at the start of START_DATE. Set once in finance_config.json, never changed.
visa_opening_balance = config['opening_balances'][bank_exports.VISA]
current_acc_opening_balance = config['opening_balances'][bank_exports.CURRENT_ACCOUNT]
net_opening_balance = visa_opening_balance + current_acc_opening_balance

# Current account closing balance: the last balance the bank printed
current_acc_daily = bank_exports.daily_balance_check(current_acc_transactions, current_acc_opening_balance)
bank_balances = current_acc_daily['bank_balance'].dropna()
if bank_balances.empty:
    st.error("⚠️ No Current Account Balance found in the data")
    st.stop()
closing_balance_current_account = bank_balances.iloc[-1]
closing_date = bank_balances.index[-1]

# The Visa export has no balance column, so its closing balance is typed in (update the default in finance_config.json)
closing_balance_visa = st.number_input("Visa Closing Balance", value=float(config['visa_closing_balance']), format="%.2f")

# Each account reconciled separately, so a shortfall on one can't hide behind the other
reconciliation = pd.DataFrame({
    'Opening Balance': [visa_opening_balance, current_acc_opening_balance],
    'Transactions': [visa_transactions['amount'].sum(), current_acc_transactions['amount'].sum()],
    'Actual Closing Balance': [closing_balance_visa, closing_balance_current_account],
}, index=['Visa', 'Current Account'])
reconciliation.loc['Total'] = reconciliation.sum()
reconciliation['Expected Closing Balance'] = reconciliation['Opening Balance'] + reconciliation['Transactions']
reconciliation['Difference'] = reconciliation['Actual Closing Balance'] - reconciliation['Expected Closing Balance']
reconciliation = reconciliation[['Opening Balance', 'Transactions', 'Expected Closing Balance',
                                 'Actual Closing Balance', 'Difference']]

st.write(f"Opening balances at {START_DATE:%d %b %Y}. Current account closing balance: the last one "
         f"the bank printed, on {closing_date:%d %b %Y}.")
st.dataframe(reconciliation.style.format(lambda v: '-' if abs(v) < 0.005 else f'{v:,.2f}'))

if np.isclose(reconciliation['Difference'], 0, atol=0.01).all():
    st.success(f"✅ Reconciliation PASSED - Balances match!")
else:
    st.error(f"❌ Reconciliation FAILED")
    for account in ['Visa', 'Current Account']:
        row = reconciliation.loc[account]
        if not np.isclose(row['Difference'], 0, atol=0.01):
            st.write(f"- {account} is out by €{row['Difference']:,.2f}. If its closing balance is right, "
                     f"its opening balance at {START_DATE:%d %b %Y} would have to be "
                     f"€{row['Actual Closing Balance'] - row['Transactions']:,.2f}.")

# The current account can also be checked day by day: the bank prints its balance at the
# end of each day, so the first day that disagrees is where a transaction is missing or doubled
mismatched_days = current_acc_daily[current_acc_daily['difference'].abs() > 0.005]
if mismatched_days.empty:
    st.success(f"✅ Current account agrees with the bank's balance at the end of all {len(bank_balances)} days")
else:
    st.error(f"❌ Current account first disagrees with the bank's balance on {mismatched_days.index[0]:%d %b %Y}")
    implied_opening = (current_acc_daily['bank_balance'] - current_acc_daily['movement'].cumsum()).dropna().iloc[0]
    st.write(f"The bank's balance on {bank_balances.index[0]:%d %b %Y} implies an opening balance of "
             f"€{implied_opening:,.2f} at {START_DATE:%d %b %Y} (finance_config.json has €{current_acc_opening_balance:,.2f}). "
             "If every day is out by the same amount, the opening balance is the problem; "
             "if the difference starts on a later day, a transaction around that day is missing or counted twice.")
    st.dataframe(mismatched_days.head(20).style.format('{:,.2f}'))

# Now display a new dataframe that uses the All Transactions dataframe but has columns be the Month and have the rows be the Coding
# Add a total column at the end that sums up the amounts for each coding category across all months
# Have the rows sorted by the total amount but in absolute value descending (noting that this order will be important later on for the graphing)
# Obviously the values will be the 'amount'
# For the dataframe and any subsequent dataframes, can you format negative values in red, and any zero values as a dash, format to 0 decimal places.  
# Do not use currency symbols
# Please note that styler.applymap is deprecated, so use styler.apply instead 

# I will want a way of digging into each coding category later on so so i can see what makes it up.  
# It will also serve as a sense check that i have got the coding mapping done correctly

# Can you also show the subtotal of the dataframe which will be the monthly cash movement of the 'amount' column
# Also bring in the opening balance to show that
# Then show the movement for the movement
# Then show the closing balance for the month, then do this for each month in the data

# Display a graph with the x-axis as the Month and the y-axis as the amount
# We only want to display the expense categories which is everything in the coding column except for 'Salary'
# Note that in the dataframe above, we used absolute values to sort the field, can we have the graph use the same sorting in the stacked bar chart
# For example, lets say 'Groceries' is the biggest expense category and 'Social' is the second biggest expense category, then in the stacked bar chart, 
# 'Groceries' should be at the bottom of the stack and 'Social' should be above it

# -----------------------
# Monthly Cash Reconciliation
# -----------------------
st.subheader("Monthly Cash Movement by Category")

# pivot_table drops rows whose Coding is blank, which would leave anything not yet coded out
# of Net Cash Movement and Closing Balance, so give those rows a coding of their own
transactions_merged['Coding'] = transactions_merged['Coding'].fillna('Uncoded')

# Create a Month column for grouping
transactions_merged['Month'] = transactions_merged['Date'].dt.to_period('M')

# Create pivot table: Coding as rows, Month as columns, values are amounts
pivot_df = transactions_merged.pivot_table(
    index='Coding',
    columns='Month',
    values='amount',
    aggfunc='sum',
    fill_value=0
)

# Add a Total column
pivot_df['Total'] = pivot_df.sum(axis=1)

# Sort by absolute value of Total (descending)
pivot_df = pivot_df.reindex(pivot_df['Total'].abs().sort_values(ascending=False).index)

# Store the category order for the chart (excluding Salary)
expense_categories_ordered = [cat for cat in pivot_df.index if cat != 'Salary (Income)']

# Add subtotal row (sum of all categories = monthly cash movement)
subtotal_row = pivot_df.sum(axis=0)
subtotal_row.name = 'Net Cash Movement'

# Calculate opening and closing balances for each month
months = [col for col in pivot_df.columns if col != 'Total']

# Build balance rows
opening_balances = {}
closing_balances = {}

running_balance = net_opening_balance
for month in months:
    opening_balances[month] = running_balance
    monthly_movement = subtotal_row[month]
    closing_balances[month] = running_balance + monthly_movement
    running_balance = closing_balances[month]

# Add Total column for balance rows
opening_balances['Total'] = net_opening_balance  # Opening balance at start
closing_balances['Total'] = running_balance       # Final closing balance

opening_row = pd.Series(opening_balances, name='Opening Balance')
closing_row = pd.Series(closing_balances, name='Closing Balance')

# Combine all into final display dataframe
display_df = pd.concat([pivot_df, pd.DataFrame([subtotal_row, opening_row, closing_row])])

# Reorder rows: Opening Balance first, then categories, then Net Cash Movement, then Closing Balance
category_rows = [idx for idx in display_df.index if idx not in ['Opening Balance', 'Net Cash Movement', 'Closing Balance']]
row_order = ['Opening Balance'] + category_rows + ['Net Cash Movement', 'Closing Balance']
display_df = display_df.reindex(row_order)

# Convert Period columns to string for display
display_df.columns = [str(col) for col in display_df.columns]

# -----------------------
# Styling functions
# -----------------------
def format_values(val):
    """Format values: negative in red, zero as dash, no decimals"""
    if pd.isna(val):
        return '-'
    elif val == 0:
        return '-'
    else:
        return f'{val:,.0f}'

def color_negative(val):
    """Return CSS for negative values (red)"""
    if pd.isna(val) or val == 0:
        return ''
    elif val < 0:
        return 'color: red'
    return ''

def apply_color_negative(series):
    """Apply color styling to a series"""
    return [color_negative(v) for v in series]

# Apply styling
styled_df = display_df.style.format(format_values).apply(apply_color_negative, axis=1)

st.dataframe(styled_df, width='stretch')

# -----------------------
# Drill-down by Category
# -----------------------
st.subheader("Drill Down by Category")

# Get unique coding categories (excluding None/NaN)
categories = transactions_merged['Coding'].dropna().unique()
categories = sorted(categories)

selected_category = st.selectbox("Select a category to view transactions:", categories)

if selected_category:
    category_transactions = transactions_merged[
        transactions_merged['Coding'] == selected_category
    ].sort_values('Date', ascending=False)
    
    st.write(f"**{selected_category}** - {len(category_transactions)} transactions, Total: €{category_transactions['amount'].sum():,.2f}")
    st.dataframe(
        category_transactions[['Date', 'Description', 'amount', 'source']],
        width='stretch'
    )

# -----------------------
# Prepare expense data for chart
# -----------------------

# Filter to expense categories only (exclude 'Salary (Income)' and 'Salary')
expense_df = pivot_df.drop(index=['Salary (Income)', 'Salary'], errors='ignore')
expense_df = expense_df.drop(columns='Total', errors='ignore')

# Also filter from the ordered categories list
expense_categories_ordered_filtered = [cat for cat in expense_categories_ordered if cat not in ['Salary (Income)', 'Salary']]

# Convert expenses to positive values for display (expenses are typically negative)
expense_df_positive = expense_df.abs()

# Get months as strings for x-axis
month_labels = [str(col) for col in expense_df_positive.columns]



# -----------------------
# in the display_df, I would like to merge in the Alt_Coding against the Coding column and then display the Alt_Coding instead of the Coding
# So the Alt_Coding is just a more user friendly version of the Coding
# so display the dataframe with the Alt_Coding instead of the Coding
# then show 5 different versions of the graph using a different graphing library each time so i can compare them
# for the graphs, please use the Alt_Coding as the category names instead of the Coding

# -----------------------
# Alt_Coding Integration and Multiple Graph Libraries
# -----------------------
# Add this code starting at line 508 in finance_cash.py

alt_mapping = pd.read_excel(DATA_DIR / 'coding_mapping.xlsx', usecols=['Coding', 'Alt_Coding'], sheet_name='Sheet2')

# Remove duplicates from alt_mapping (keep last if any duplicates exist)
alt_mapping_deduped = alt_mapping.drop_duplicates(subset='Coding', keep='last')

# -----------------------
# Merge Alt_Coding into display_df
# -----------------------
# Reset index to make Coding a column for merging
display_df_reset = display_df.reset_index().rename(columns={'index': 'Coding'})

# Merge with alt_mapping to get Alt_Coding
display_df_with_alt = display_df_reset.merge(
    alt_mapping_deduped,
    on='Coding',
    how='left'
)

# For rows without Alt_Coding (like 'Opening Balance', 'Net Cash Movement', 'Closing Balance'), use the original Coding
display_df_with_alt['Alt_Coding'] = display_df_with_alt['Alt_Coding'].fillna(display_df_with_alt['Coding'])

# Handle duplicate Alt_Coding values by aggregating (sum) the numeric columns
# First, identify which columns are numeric (the month columns and Total)
numeric_cols = [col for col in display_df_with_alt.columns if col not in ['Coding', 'Alt_Coding']]

# Group by Alt_Coding and sum the numeric values (this handles cases where multiple Coding map to same Alt_Coding)
display_df_with_alt = display_df_with_alt.groupby('Alt_Coding', as_index=False)[numeric_cols].sum()

# Set Alt_Coding as the index
display_df_with_alt = display_df_with_alt.set_index('Alt_Coding')

# Reorder rows: Opening Balance first, then categories sorted by absolute Total, then Net Cash Movement, then Closing Balance
special_rows = ['Opening Balance', 'Net Cash Movement', 'Closing Balance']
category_rows = [idx for idx in display_df_with_alt.index if idx not in special_rows]

# Sort category rows by absolute Total descending
if 'Total' in display_df_with_alt.columns:
    category_totals = display_df_with_alt.loc[category_rows, 'Total'].abs().sort_values(ascending=False)
    category_rows_sorted = category_totals.index.tolist()
else:
    category_rows_sorted = category_rows

# Build final row order
row_order = []
if 'Opening Balance' in display_df_with_alt.index:
    row_order.append('Opening Balance')
row_order.extend(category_rows_sorted)
if 'Net Cash Movement' in display_df_with_alt.index:
    row_order.append('Net Cash Movement')
if 'Closing Balance' in display_df_with_alt.index:
    row_order.append('Closing Balance')

display_df_with_alt = display_df_with_alt.reindex(row_order)

# -----------------------
# Display the styled dataframe with Alt_Coding
# -----------------------
st.subheader("Monthly Cash Movement by Category (User-Friendly Names)")

styled_df_alt = display_df_with_alt.style.format(format_values).apply(apply_color_negative, axis=1)
st.dataframe(styled_df_alt, width='stretch')

# -----------------------
# Prepare data for charts with Alt_Coding
# -----------------------
# Create a mapping dictionary from Coding to Alt_Coding
coding_to_alt = dict(zip(alt_mapping_deduped['Coding'], alt_mapping_deduped['Alt_Coding']))

# Create expense dataframe with Alt_Coding as index
expense_df_alt = expense_df_positive.copy()
expense_df_alt['Alt_Coding'] = expense_df_alt.index.map(lambda x: coding_to_alt.get(x, x))

# Group by Alt_Coding to handle cases where multiple Coding map to the same Alt_Coding
expense_df_alt = expense_df_alt.groupby('Alt_Coding').sum()

# Convert column names from Period to string for JSON serialization
expense_df_alt.columns = [str(col) for col in expense_df_alt.columns]

# Map the expense categories to their Alt_Coding names and remove duplicates while preserving order
expense_categories_alt_raw = [coding_to_alt.get(cat, cat) for cat in expense_categories_ordered_filtered]
# Remove duplicates while preserving order
seen = set()
expense_categories_alt = []
for cat in expense_categories_alt_raw:
    if cat not in seen:
        seen.add(cat)
        expense_categories_alt.append(cat)

# Get month labels
month_labels = [str(col) for col in expense_df_alt.columns]

# =============================================================================
# Altair Stacked Bar Chart
# =============================================================================
st.subheader("Monthly Expenses by Category")

import altair as alt

# Prepare long format data for Altair
expense_long_alt = expense_df_alt.reset_index().melt(
    id_vars='Alt_Coding',
    var_name='Month',
    value_name='Amount'
).rename(columns={'Alt_Coding': 'Category'})

# Convert Month to string (Period objects are not JSON serializable)
expense_long_alt['Month'] = expense_long_alt['Month'].astype(str)

# Create Altair chart with explicit category order
chart_altair = alt.Chart(expense_long_alt).mark_bar().encode(
    x=alt.X('Month:N', title='Month', sort=month_labels),
    y=alt.Y('Amount:Q', title='Amount (€)', stack='zero'),
    color=alt.Color('Category:N', 
                    title='Category',
                    sort=expense_categories_alt,
                    scale=alt.Scale(scheme='tableau20')),
    order=alt.Order('category_order:Q'),
    tooltip=['Category', 'Month', alt.Tooltip('Amount:Q', format=',.0f')]
).transform_calculate(
    category_order=f"indexof({expense_categories_alt}, datum.Category)"
).properties(
    title='Monthly Expenses by Category - Altair',
    width='container',
    height=500
).configure_legend(
    orient='right',
    labelLimit=200
)

st.altair_chart(chart_altair, width='stretch')

# =============================================================================
# Faceted Bar Charts - One per Category
# =============================================================================
st.subheader("Monthly Spend by Category (Faceted)")

# Reuse expense_long_alt which has Category, Month, Amount
# Filter out categories with zero total spend
facet_data = expense_long_alt.copy()
facet_data = facet_data[facet_data.groupby('Category')['Amount'].transform('sum') > 0]

# Sort categories by total spend descending so the biggest categories appear first
category_totals = facet_data.groupby('Category')['Amount'].sum().sort_values(ascending=False)
category_order = category_totals.index.tolist()

chart_faceted = alt.Chart(facet_data).mark_bar().encode(
    x=alt.X('Month:N', title='Month', sort=month_labels),
    y=alt.Y('Amount:Q', title='Amount (€)'),
    color=alt.Color('Category:N',
                    sort=category_order,
                    scale=alt.Scale(scheme='tableau20'),
                    legend=None),
    tooltip=['Category', 'Month', alt.Tooltip('Amount:Q', format=',.0f')]
).properties(
    width=200,
    height=150
).facet(
    facet=alt.Facet('Category:N', title=None, sort=category_order),
    columns=3
).resolve_scale(
    y='independent'
)

st.altair_chart(chart_faceted, width='stretch')