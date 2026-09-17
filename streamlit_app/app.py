import streamlit as st
import requests
import pandas as pd
from pathlib import Path

# --- Configuration ---
API_URL = "https://munahl5923--longitudinal-study-api-fastapi-app.modal.run/query"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = PROJECT_ROOT / "nfti.jpeg"

# --- Page Setup & Styling ---
st.set_page_config(
    page_title="Natview Longitudinal Study Analytic Agent",
    page_icon="🏥",
    layout="centered"
)

# Custom CSS for Natview Blue/White branding
st.markdown("""
<style>
    /* Primary brand colors */
    :root {
        --natview-blue: #0056b3;
        --natview-light-blue: #e6f0fa;
    }
    
    /* Main header styling */
    .main-header {
        color: var(--natview-blue);
        font-weight: 700;
        text-align: center;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# --- Header ---
col1, col2 = st.columns([1, 4])
with col1:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=80)
with col2:
    st.markdown("<h2 class='main-header'>Natview Longitudinal Study Analytic Agent</h2>", unsafe_allow_html=True)

st.markdown("Ask natural language questions about the health facility survey data.")
st.divider()

# --- Chat State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Render Chat History ---
for msg in st.session_state.messages:
    if msg["role"] == "user":
        # Custom HTML for right-aligned user message
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-end; margin-bottom: 1rem;">
            <div style="background-color: var(--natview-light-blue); color: #1E1E1E; padding: 10px 15px; border-radius: 15px 15px 0px 15px; max-width: 80%; border: 1px solid var(--natview-blue); text-align: left;">
                {msg["content"]}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "sql" in msg and msg["sql"]:
                with st.expander("🔍 View SQL Query"):
                    st.code(msg["sql"], language="sql")
            if "data" in msg and msg["data"] is not None:
                with st.expander("📊 View Raw Data"):
                    st.dataframe(pd.DataFrame(msg["data"]))

# --- Chat Input & Logic ---
if prompt := st.chat_input("Ask a question (e.g. 'How many facilities are in kaduna north?')"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message using custom HTML
    st.markdown(f"""
    <div style="display: flex; justify-content: flex-end; margin-bottom: 1rem;">
        <div style="background-color: var(--natview-light-blue); color: #1E1E1E; padding: 10px 15px; border-radius: 15px 15px 0px 15px; max-width: 80%; border: 1px solid var(--natview-blue); text-align: left;">
            {prompt}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Call API and stream response
    with st.chat_message("assistant"):
        with st.spinner("Analyzing data..."):
            try:
                response = requests.post(API_URL, json={"question": prompt}, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    answer = result.get("answer", "No answer provided.")
                    data = result.get("raw_data", None)
                    sql = result.get("generated_sql", None)
                    
                    st.write(answer)
                    
                    if sql:
                        with st.expander("🔍 View SQL Query"):
                            st.code(sql, language="sql")
                    
                    if data:
                        with st.expander("📊 View Raw Data"):
                            st.dataframe(pd.DataFrame(data))
                            
                    # Save assistant response to state
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": answer,
                        "data": data,
                        "sql": sql
                    })
                else:
                    error_msg = f"API Error ({response.status_code}): {response.text}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
                    
            except Exception as e:
                error_msg = f"Connection failed: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
