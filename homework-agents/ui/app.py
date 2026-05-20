from __future__ import annotations

import streamlit as st


st.set_page_config(page_title="Personal Finance Coach", layout="wide")
st.title("Personal Finance Coach Demo")

architecture = st.sidebar.selectbox("Architecture", ["baseline", "crew"], index=0)
st.sidebar.caption("Crew path is a placeholder at this stage.")

prompt = st.text_area("Your query", placeholder="How much did I spend on coffee last week?")

if st.button("Submit"):
    if not prompt.strip():
        st.warning("Please enter a question.")
    else:
        st.success("Placeholder response")
        st.write(f"Architecture: {architecture}")
        st.write("Answer: API wiring comes in the next step.")
        with st.expander("Trace"):
            st.write("No trace yet.")
