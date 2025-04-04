# section8_lihtc_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import io

st.set_page_config(page_title="LIHTC & Section 8 Rent Analysis", layout="centered")
st.title("LIHTC & Section 8 Overhang Risk Dashboard")

st.subheader("1. Unit Input by AMI Level, Beds, and Baths")

unit_data = st.data_editor(pd.DataFrame({
    'AMI Level': ['60%', '50%', '30%'],
    'Beds': [1, 2, 3],
    'Baths': [1, 1, 2],
    'Units': [12, 20, 10],
    'Utility Allowance': [100, 120, 150],
    'Section 8 Rent': [1650, 1850, 2050]
}), num_rows="dynamic")

# Assume HUD income limits for a 4-person household at 100% AMI
ami_100_income = st.number_input("Enter 100% AMI for 4-person household (HUD published)", value=80000)

# Household size by number of bedrooms
bedroom_to_hhsize = {0: 1, 1: 1.5, 2: 3, 3: 4.5, 4: 6}

# Calculate LIHTC Rents and Overhang
def parse_ami(ami_str):
    return int(ami_str.replace('%', '')) / 100

output = []
for _, row in unit_data.iterrows():
    try:
        beds_raw = row['Beds']
        if pd.isna(beds_raw) or not str(beds_raw).isdigit():
            st.warning(f"Missing or invalid bed count for row: {row.to_dict()}")
            beds = 1  # default fallback
        else:
            beds = int(beds_raw)
    except (ValueError, TypeError, KeyError):
        st.warning(f"Error processing 'Beds' value: {row.to_dict()}")
        beds = 1  # fallback again
    hh_size = bedroom_to_hhsize.get(beds, 1.5)
    ami_level = parse_ami(row['AMI Level'])
    income = ami_100_income * ami_level * (hh_size / 4)
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
st.subheader("2. Rent Comparison Table")
st.dataframe(result_df)

# Plot
chart = px.bar(result_df, x='Beds', y='Overhang ($)', color='AMI Level', barmode='group', title="Overhang by Unit Type")
st.plotly_chart(chart)

# Export to Excel
st.subheader("3. Export to Excel")
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

# Investor Summary
st.subheader("4. Investor Summary")
memo = f"""
### Summary of LIHTC vs Section 8 Rent Overhang

This dashboard analyzes max allowable LIHTC rents versus Section 8 rents per unit type.

- Based on a 100% AMI of ${ami_100_income:,}
- Rents are adjusted for utility allowances and household size.
- Overhang risk is calculated as Section 8 rent above LIHTC net rent.

Key Metrics:
- Highest overhang unit: {result_df.loc[result_df['Overhang ($)'].idxmax()]['Beds']}BR at {result_df.loc[result_df['Overhang ($)'].idxmax()]['Overhang ($)']}$
- Average overhang: {result_df['Overhang ($)'].mean():.0f}$

Use this data to evaluate project subsidy exposure and underwrite downside rent risk.
"""
st.markdown(memo)
