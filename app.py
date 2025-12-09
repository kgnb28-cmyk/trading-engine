import streamlit as st
import pandas as pd
import time
from datetime import datetime

# --- 1. UI CONFIGURATION (Ultra Light) ---
st.set_page_config(
    page_title="Algo Command",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed" # Collapsed to save RAM/Space
)

# --- 2. FAST CSS (Removes Padding & Bloat) ---
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 0rem;}
        div[data-testid="stMetricValue"] {font-size: 28px; color: #00ff00;}
        .stButton>button {width: 100%; border-radius: 5px; height: 3em;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# --- 3. SESSION STATE SETUP ---
if 'run_engine' not in st.session_state:
    st.session_state['run_engine'] = False
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

# --- 4. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("Control Panel")
    
    # Large Toggle Buttons
    col_start, col_stop = st.columns(2)
    if col_start.button("🟢 START"):
        st.session_state['run_engine'] = True
    if col_stop.button("🔴 STOP"):
        st.session_state['run_engine'] = False

    st.divider()
    
    # Speed Control
    refresh_rate = st.slider("Refresh Speed (s)", 0.5, 5.0, 1.0)
    
    # Status Badge
    status = "RUNNING" if st.session_state['run_engine'] else "STOPPED"
    st.write(f"**Engine Status:** {status}")

# --- 5. MAIN DASHBOARD UI (The "View") ---

# Row A: Headline Metrics (The most important data)
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
spot_display = kpi1.empty()
ce_display = kpi2.empty()
pe_display = kpi3.empty()
pnl_display = kpi4.empty()

st.divider()

# Row B: Logs & Signals
st.subheader("⚡ Live Trade Logs")
log_table = st.empty()

# --- 6. THE LOOP (Where You Paste Your Logic) ---
if st.session_state['run_engine']:
    
    # This loop keeps running while the dashboard is open
    while st.session_state['run_engine']:
        
        # =========================================================
        # [YOUR AREA] PASTE YOUR LOGIC & API CALLS HERE
        # =========================================================
        
        # 1. Get your data (Replace 0 with your variable)
        my_ltp = 24100      # <--- Input: Current Market Price
        my_ce_strike = 24300 # <--- Input: Your selected CE Strike
        my_pe_strike = 23900 # <--- Input: Your selected PE Strike
        my_pnl = 1500.50    # <--- Input: Total MTM
        
        # 2. Add a log entry (Replace strings with your signals)
        new_log = {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "Signal": "WAITING", # <--- Input: Your Decision
            "Message": "Monitoring OTM premiums..." # <--- Input: Your Context
        }
        
        # =========================================================
        # [END USER AREA] UI UPDATES BELOW
        # =========================================================

        # Update Session Log (Keep only last 10 rows for memory efficiency)
        st.session_state['logs'].append(new_log)
        if len(st.session_state['logs']) > 10:
            st.session_state['logs'].pop(0)

        # Update Metrics (Instant visual update)
        spot_display.metric("SPOT PRICE", my_ltp)
        ce_display.metric("CE STRIKE", my_ce_strike)
        pe_display.metric("PE STRIKE", my_pe_strike)
        pnl_display.metric("TOTAL P&L", f"₹ {my_pnl}")

        # Update Table
        df_logs = pd.DataFrame(st.session_state['logs'])
        # Sort so newest is on top
        log_table.dataframe(df_logs.iloc[::-1], use_container_width=True, hide_index=True)

        # Sleep to prevent CPU spike
        time.sleep(refresh_rate)

else:
    st.info("System is Offline. Press START in Sidebar.")