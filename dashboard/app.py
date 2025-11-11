import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(page_title="IGFX-Bot Dashboard", layout="wide")
st.title("📈 IGFX-Bot — Monitoring Dashboard")

st.markdown("""
This simple dashboard is a placeholder. In live usage, you can stream logs or read from a database.
""")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Equity Curve (Sample)")
    df = pd.DataFrame({"step": range(50), "equity": [10000 + i*3 for i in range(50)]})
    st.line_chart(df.set_index("step"))

with col2:
    st.subheader("Open Positions (Sample)")
    st.table(pd.DataFrame([
        {"symbol":"EURUSD","side":"BUY","size":10000,"entry":1.0710,"sl":1.0700,"tp":1.0730}
    ]))
