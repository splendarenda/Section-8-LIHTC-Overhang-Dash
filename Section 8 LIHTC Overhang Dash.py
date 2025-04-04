# section8_lihtc_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
import urllib.parse

st.set_page_config(page_title="LIHTC & Section 8 Rent Analysis", layout="centered")
st.title("LIHTC & Section 8 Overhang Risk Dashboard")

st.subheader("1. Select County and State to Load HUD Data")
hud_df = pd.read_csv("data/hud_counties.csv")  # Must include 'state' and 'county' columns
states = sorted(hud_df["state"].unique())
state = st.selectbox("Select State", states)
valid_counties = sorted(hud_df[hud_df["state"] == state]["county"].unique())
county = st.selectbox("Select County", valid_counties)

@st.cache_data
def get_hud_income_limits(state, county, year=2025):
    token = st.secrets["api"]["hud_token"]
    headers = {"Authorization": f"Bearer {token}"}
    state_param = urllib.parse.quote_plus(state.upper())
    county_param = urllib.parse.quote_plus(county.title())
    url = f"https://www.huduser.gov/hudapi/public/il?state={state_param}&county={county_param}&year={year}"
    st.text(f"Requesting: {url}")
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json()
    elif year == 2025:
        st.warning("2025 income limits not found, retrying 2024...")
        return get_hud_income_limits(state, county, year=2024)
    else:
        st.error(f"HUD API returned status {res.status_code}: {res.text}")
        return None

@st.cache_data
def get_hud_fmr(state, county):
    try:
        fmr_df = pd.read_excel("data/section8_fmr_fallback_2025.xlsx")
        row = fmr_df[(fmr_df["state"].str.upper() == state.upper()) & (fmr_df["county"].str.title() == county.title())]
        if not row.empty:
            return {
                "fmr_0br": row.iloc[0].get("fmr_0br", 0),
                "fmr_1br": row.iloc[0].get("fmr_1br", 0),
                "fmr_2br": row.iloc[0].get("fmr_2br", 0),
                "fmr_3br": row.iloc[0].get("fmr_3br", 0),
                "fmr_4br": row.iloc[0].get("fmr_4br", 0)
            }
    except Exception as e:
        st.warning("Could not load FMR fallback Excel file.")
    return {}

hud_data = get_hud_income_limits(state.strip(), county.strip()) if state and county else None
fmr_data = get_hud_fmr(state.strip(), county.strip())

if hud_data:
    try:
        median_income = hud_data['IncomeLimits']['median_income']
        ami_60_4person = hud_data['IncomeLimits']['income_limit_60']['4']
        st.success(f"Loaded HUD Income Limits for {county.title()}, {state.upper()}")
        st.write(f"Median Income: ${median_income}")
        st.write(f"60% AMI (4-person): ${ami_60_4person}")
    except Exception as e:
        st.warning("HUD API returned unexpected format, falling back to local data.")
        fallback_df = pd.read_csv("data/hud_fallback_incomes.csv")
        row = fallback_df[(fallback_df.state == state) & (fallback_df.county == county)]
        if not row.empty:
            median_income = row.iloc[0]['median_income']
            st.info("Using fallback HUD income limits.")
            st.write(f"Median Income: ${median_income}")
        else:
            st.warning("No fallback data found. Please enter income manually.")
            median_income = st.number_input("Manual 100% AMI income (4-person household)", value=80000)
else:
    st.warning("Unable to load real-time HUD income limits. Falling back to local data.")
    fallback_df = pd.read_csv("data/hud_fallback_incomes.csv")
    row = fallback_df[(fallback_df.state == state) & (fallback_df.county == county)]
    if not row.empty:
        median_income = row.iloc[0]['median_income']
        st.info("Using fallback HUD income limits.")
        st.write(f"Median Income: ${median_income}")
    else:
        st.warning("No fallback data found. Please enter income manually.")
        median_income = st.number_input("Manual 100% AMI income (4-person household)", value=80000)

# --- Unit Breakdown ---
st.subheader("2. Unit Input by AMI Level, Beds, and Baths")

unit_data = st.data_editor(pd.DataFrame({
    'AMI Level': ['60%', '50%', '30%'],
    'Beds': [1, 2, 3],
    'Baths': [1, 1, 2],
    'Units': [12, 20, 10],
    'Utility Allowance': [100, 120, 150],
    'Section 8 Rent': [fmr_data.get("fmr_1br", 1650), fmr_data.get("fmr_2br", 1850), fmr_data.get("fmr_3br", 2050)]
}), num_rows="dynamic")

bedroom_to_hhsize = {0: 1, 1: 1.5, 2: 3, 3: 4.5, 4: 6}

output = []
for _, row in unit_data.iterrows():
    try:
        beds_raw = row['Beds']
        if pd.isna(beds_raw) or not str(beds_raw).isdigit():
            st.warning(f"Missing or invalid bed count for row: {row.to_dict()}")
            beds = 1
        else:
            beds = int(beds_raw)
    except (ValueError, TypeError, KeyError):
        st.warning(f"Error processing 'Beds' value: {row.to_dict()}")
        beds = 1

    hh_size = bedroom_to_hhsize.get(beds, 1.5)
    ami_level = int(row['AMI Level'].replace('%', '')) / 100
    income = median_income * ami_level * (hh_size / 4)
    gross_rent = income * 0.3 / 12
    net_rent = gross_rent - row['Utility Allowance']
    overhang = row['Section 8 Rent'] - net_rent
    overhang_pct = overhang / net_rent if net_rent > 0 else 0

    output.append({
        'AMI Level': row['AMI Level'],
        'Beds': beds,
        'Baths': row['Baths'],
        'Units': row['Units'],
        'Max LIHTC Gross Rent': round(gross_rent),
        'Utility Allowance': row['Utility Allowance'],
        'Max LIHTC Net Rent': round(net_rent),
        'Section 8 Rent': row['Section 8 Rent'],
        'Overhang ($)': round(overhang),
        'Overhang (%)': f"{overhang_pct * 100:.1f}%"
    })

result_df = pd.DataFrame(output)
st.subheader("3. Rent Comparison Table")
st.dataframe(result_df)

# --- Chart ---
chart = px.bar(result_df, x='Beds', y='Overhang ($)', color='AMI Level', barmode='group', title="Overhang by Unit Type")
st.plotly_chart(chart)

# --- Export to Excel ---
st.subheader("4. Export to Excel")
excel_out = io.BytesIO()
with pd.ExcelWriter(excel_out, engine='xlsxwriter') as writer:
    unit_data.to_excel(writer, index=False, sheet_name='Input')
    result_df.to_excel(writer, index=False, sheet_name='Results')

st.download_button(
    label="Download Excel File",
    data=excel_out.getvalue(),
    file_name="lihtc_section8_overhang.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- Investor Summary ---
st.subheader("5. Investor Summary")
memo = f"""
### Summary of LIHTC vs Section 8 Rent Overhang

This dashboard analyzes max allowable LIHTC rents versus Section 8 rents per unit type.

- Based on HUD income data for {county}, {state} or manual entry.
- Rents are adjusted for utility allowances and household size.
- Overhang risk is calculated as Section 8 rent above LIHTC net rent.

Key Metrics:
- Highest overhang unit: {result_df.loc[result_df['Overhang ($)'].idxmax()]['Beds']}BR at {result_df.loc[result_df['Overhang ($)'].idxmax()]['Overhang ($)']}$
- Average overhang: {result_df['Overhang ($)'].mean():.0f}$

Use this data to evaluate project subsidy exposure and underwrite downside rent risk.
"""
st.markdown(memo)
