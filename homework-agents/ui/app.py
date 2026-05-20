from __future__ import annotations

import httpx
import streamlit as st
import uuid


st.set_page_config(page_title="Personal Finance Coach", layout="wide")
st.title("Personal Finance Coach Demo")

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

api_base_url = st.sidebar.text_input("API base URL", value="http://127.0.0.1:8000")

architecture = st.sidebar.selectbox("Architecture", ["baseline", "crew"], index=0)
st.sidebar.caption("Baseline and crew paths are both active.")
st.sidebar.write(f"Session ID: {st.session_state['session_id']}")

if st.sidebar.button("New Session"):
    st.session_state["session_id"] = str(uuid.uuid4())
    st.rerun()

prompt = st.text_area("Your query", placeholder="How much did I spend on coffee last week?")

if st.button("Submit"):
    if not prompt.strip():
        st.warning("Please enter a question.")
    else:
        payload = {
            "message": prompt,
            "architecture": architecture,
            "session_id": st.session_state["session_id"],
        }
        try:
            response = httpx.post(f"{api_base_url}/chat", json=payload, timeout=20.0)
            response.raise_for_status()
            data = response.json()

            st.success("Response received")
            st.write(f"Architecture: {data.get('architecture', architecture)}")
            st.write(f"Answer: {data.get('answer', '')}")

            with st.expander("Trace"):
                st.json(
                    {
                        "session_id": data.get("session_id"),
                        "intent": data.get("intent"),
                        "intent_reason": data.get("intent_reason"),
                        "route": data.get("route"),
                        "guardrail_applied": data.get("guardrail_applied"),
                        "resolved_category": data.get("resolved_category"),
                        "resolved_period": data.get("resolved_period"),
                        "context": data.get("context", {}),
                        "tools_used": data.get("tools_used", []),
                        "tool_outputs": data.get("tool_outputs", {}),
                    }
                )
        except Exception as exc:
            st.error(f"Could not call chat API: {exc}")

if st.button("Load Step 2 Summary"):
    try:
        response = httpx.get(f"{api_base_url}/debug/summary", timeout=10.0)
        response.raise_for_status()
        st.json(response.json())
    except Exception as exc:
        st.error(f"Could not load summary: {exc}")
