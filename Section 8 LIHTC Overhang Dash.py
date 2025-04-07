# section8_lihtc_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import io
import urllib.parse
import datetime

st.set_page_config(page_title="LIHTC & Section 8 Rent Analysis", layout="centered")
st.title("LIHTC & Section 8 Overhang Risk Dashboard")

st.subheader("1. Select State and County to Load HUD Data")
section8_df = pd.read_excel("Section8-FY25.xlsx")

# Ensure all data is clean and formatted
section8_df["state"] = section8_df["state"].astype(str).str.strip().str.upper()
section8_df["county"] = section8_df["county"].astype(str).str.strip().str.title()

# Load FIPS state and county name mapping
fips_df = pd.read_csv("hud_counties.csv")
fips_df["state_name"] = fips_df["State"].astype(str).str.upper()
fips_df["county_name"] = fips_df["County"].astype(str).str.title()

# Dropdowns
states = sorted(fips_df["state_name"].unique())
selected_state = st.selectbox("Select State", states)
counties = sorted(fips_df[fips_df["state_name"] == selected_state]["county_name"].unique())
selected_county = st.selectbox("Select County", counties)

# Get FIPS from lookup
@st.cache_data
def get_entity_id(state_name, county_name):
    match = fips_df[
        (fips_df['state_name'] == state_name) &
        (fips_df['county_name'] == county_name)
    ]
    if not match.empty:
        return str(match.iloc[0]['fips']).zfill(5)
    return None

@st.cache_data
def get_hud_income_limits(entity_id, year=2025):
    token = st.secrets["api"]["hud_token"]
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://www.huduser.gov/hudapi/public/il/data?geoid={entity_id}&year={year}"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            return res.json(), year
        elif year == 2025:
            st.warning("2025 income limits not found, retrying 2024...")
            return get_hud_income_limits(entity_id, year=2024)
        else:
            st.error(f"HUD API returned status {res.status_code}")
            log_error(f"HUD API error {res.status_code}: {res.text}", entity_id, year)
            return None, None
    except Exception as e:
        log_error(f"Request failed: {str(e)}", entity_id, year)
        return None, None

@st.cache_data
def get_hud_fmr(state, county):
    try:
        fmr_df = pd.read_excel("section8_fmr_fallback_2025.xlsx")
        row = fmr_df[(fmr_df["state"].str.upper() == state.upper()) & (fmr_df["county"].str.strip().str.lower() == county.strip().lower())]
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

# Error logging function
def log_error(message, entity_id, year):
    with open("hud_api_errors.log", "a") as f:
        f.write(f"[{datetime.datetime.now()}] Entity: {entity_id}, Year: {year} - {message}\n")

entity_id = get_entity_id(selected_state, selected_county)
st.write("Selected:", selected_state, selected_county)
st.write("Entity ID:", entity_id)

hud_data, hud_year = get_hud_income_limits(entity_id) if entity_id else (None, None)
fmr_data = get_hud_fmr(selected_state, selected_county)

if hud_data and 'IncomeLimits' in hud_data:
    try:
        median_income = hud_data['IncomeLimits']['median_income']
        ami_60_4person = hud_data['IncomeLimits']['income_limit_60']['4']
        st.success(f"Loaded HUD Income Limits for {selected_county}, {selected_state} ({hud_year})")
        st.write(f"Median Income ({hud_year}): ${median_income}")
        st.write(f"60% AMI (4-person): ${ami_60_4person}")

        st.subheader("Raw Income Limits Table")
        raw_table = pd.DataFrame(hud_data['IncomeLimits']['income_limit_60'], index=["60% AMI"]).T
        for level in ['income_limit_30', 'income_limit_50', 'income_limit_80']:
            if level in hud_data['IncomeLimits']:
                tmp_df = pd.DataFrame(hud_data['IncomeLimits'][level], index=[level.replace('income_limit_', '') + '%']).T
                raw_table = pd.concat([raw_table, tmp_df])
        st.dataframe(raw_table)

    except Exception as e:
        st.warning("HUD API returned unexpected format, falling back to local data.")
        log_error(f"Unexpected HUD format: {str(e)}", entity_id, hud_year)
        hud_data = None

if not hud_data or 'IncomeLimits' not in hud_data:
    st.warning("Unable to load real-time HUD income limits. Falling back to local data.")
    row = section8_df[
        (section8_df.state.str.upper() == selected_state.upper()) &
        (section8_df.county.str.strip().str.lower() == selected_county.strip().lower())
    ]
    if not row.empty:
        median_income = row.iloc[0]['median2025']
        st.info("Using fallback Section 8 income limits.")
        st.write(f"Median Income: ${median_income}")
    else:
        st.warning("No fallback data found. Please enter income manually.")
        median_income = st.number_input("Manual 100% AMI income (4-person household)", value=80000)


# Above was patched to log HUD API failures. Above was patched to have state and counties translate from numbers to real readable. Above was patched to use FIPS within HUD API calls. Remainder of dashboard continues unchanged...

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

- Based on HUD income data for {county}, {state} (Year: {hud_year}) or manual entry.
- Rents are adjusted for utility allowances and household size.
- Overhang risk is calculated as Section 8 rent above LIHTC net rent.

Key Metrics:
- Highest overhang unit: {result_df.loc[result_df['Overhang ($)'].idxmax()]['Beds']}BR at {result_df.loc[result_df['Overhang ($)'].idxmax()]['Overhang ($)']}$
- Average overhang: {result_df['Overhang ($)'].mean():.0f}$

Use this data to evaluate project subsidy exposure and underwrite downside rent risk.
"""
st.markdown(memo)
