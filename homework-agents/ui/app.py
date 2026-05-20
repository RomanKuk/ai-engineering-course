from __future__ import annotations

import httpx
import json
import streamlit as st
import uuid


def _cases_to_csv(cases: list[dict]) -> str:
    headers = [
        "id",
        "message",
        "expected_intent",
        "actual_intent",
        "expected_route",
        "actual_route",
        "latency_ms",
        "success",
        "tool_selection_ok",
        "groundedness",
        "required_tools",
        "tools_used",
    ]
    rows = [",".join(headers)]
    for case in cases:
        values = []
        for header in headers:
            value = case.get(header, "")
            if isinstance(value, list):
                value = "|".join(str(v) for v in value)
            text = str(value).replace('"', '""')
            values.append(f'"{text}"')
        rows.append(",".join(values))
    return "\n".join(rows)


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

chat_tab, eval_tab = st.tabs(["Chat", "Eval"])

with chat_tab:
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

with eval_tab:
    st.subheader("Golden Set Evaluation")
    max_cases = st.number_input("Max cases (0 = all)", min_value=0, max_value=100, value=0, step=1)
    if st.button("Run Eval"):
        try:
            payload = {}
            if max_cases > 0:
                payload["max_cases"] = int(max_cases)
            response = httpx.post(f"{api_base_url}/eval/run", json=payload, timeout=120.0)
            response.raise_for_status()
            data = response.json()

            st.success("Evaluation completed")
            st.write(f"Golden set size: {data.get('golden_set_size')}")

            baseline_summary = data.get("baseline", {}).get("summary", {})
            crew_summary = data.get("crew", {}).get("summary", {})

            st.markdown("### Summary")
            st.table(
                {
                    "metric": [
                        "latency_p50",
                        "latency_p95",
                        "cost_per_task",
                        "tokens_per_task",
                        "success_rate",
                        "tool_selection_accuracy",
                        "groundedness",
                        "inter_agent_overhead_pct",
                    ],
                    "baseline": [
                        baseline_summary.get("latency_p50"),
                        baseline_summary.get("latency_p95"),
                        baseline_summary.get("cost_per_task"),
                        baseline_summary.get("tokens_per_task"),
                        baseline_summary.get("success_rate"),
                        baseline_summary.get("tool_selection_accuracy"),
                        baseline_summary.get("groundedness"),
                        baseline_summary.get("inter_agent_overhead_pct"),
                    ],
                    "crew": [
                        crew_summary.get("latency_p50"),
                        crew_summary.get("latency_p95"),
                        crew_summary.get("cost_per_task"),
                        crew_summary.get("tokens_per_task"),
                        crew_summary.get("success_rate"),
                        crew_summary.get("tool_selection_accuracy"),
                        crew_summary.get("groundedness"),
                        crew_summary.get("inter_agent_overhead_pct"),
                    ],
                }
            )

            baseline_cases = data.get("baseline", {}).get("cases", [])
            crew_cases = data.get("crew", {}).get("cases", [])

            st.markdown("### Intent Breakdown")
            baseline_intents = baseline_summary.get("intent_breakdown", {})
            crew_intents = crew_summary.get("intent_breakdown", {})
            all_intents = sorted(set(baseline_intents.keys()) | set(crew_intents.keys()))
            if all_intents:
                st.table(
                    {
                        "intent": all_intents,
                        "baseline_success_rate": [
                            baseline_intents.get(intent, {}).get("success_rate") for intent in all_intents
                        ],
                        "crew_success_rate": [crew_intents.get(intent, {}).get("success_rate") for intent in all_intents],
                        "baseline_avg_latency_ms": [
                            baseline_intents.get(intent, {}).get("avg_latency_ms") for intent in all_intents
                        ],
                        "crew_avg_latency_ms": [crew_intents.get(intent, {}).get("avg_latency_ms") for intent in all_intents],
                    }
                )

            st.markdown("### Download Results")
            st.download_button(
                label="Download full eval JSON",
                data=json.dumps(data, indent=2),
                file_name="eval_results.json",
                mime="application/json",
            )
            st.download_button(
                label="Download baseline cases CSV",
                data=_cases_to_csv(baseline_cases),
                file_name="eval_baseline_cases.csv",
                mime="text/csv",
            )
            st.download_button(
                label="Download crew cases CSV",
                data=_cases_to_csv(crew_cases),
                file_name="eval_crew_cases.csv",
                mime="text/csv",
            )

            with st.expander("Baseline case results"):
                st.json(baseline_cases)
            with st.expander("Crew case results"):
                st.json(crew_cases)
        except Exception as exc:
            st.error(f"Could not run evaluation: {exc}")
