"""[Member 3] Streamlit dashboard: forecasts + intervals, actuals, MAE/RMSE, model version,
latest pipeline run, and drift reports produced by Member 1 (reports/monitoring/*.json).

Run locally: streamlit run src/solarcast/dashboard/app.py
"""

import streamlit as st

st.set_page_config(page_title="SolarCast", layout="wide")
st.title("SolarCast - next-day solar forecast (Lahore)")
st.info("Skeleton - charts coming in week 2.")
