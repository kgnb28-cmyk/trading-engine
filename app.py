import streamlit as st
import pandas as pd
import time
import requests
import math
from datetime import datetime

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="Upstox Algo Deck", page_icon="📈", layout="wide")

# Custom CSS for a "Trader's Dark Mode" look
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        div[data-testid="stMetricValue"] {font-size: 20px;}
        .stTabs [data-baseweb="tab-list"] {gap: 10px;}
        .stTabs [data-baseweb="tab"] {height: 50px; white-space: pre-wrap; background-color: #0e1117; border-radius: 5px;}
        .stTabs [aria-selected="true"] {background-color: #262730;}
    </style>
""", unsafe_allow_html=True)

# --- 2. HELPERS: UPSTOX API HANDLERS ---

def fetch_ltp(token, symbols):
    """
    Fetches LTP for a list of symbols from Upstox.
    Format: "NSE_INDEX|Nifty 50" or "NSE_FO|NIFTY24DEC21000CE"
    """
    if not token:
        return {}
    
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    # Join symbols with commas
    params = {'instrument_key': ",".join(symbols)}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=2)
        data = response.json()
        if 'data' in data:
            # Return a simple dict: {'Symbol': Price}
            return {k: v['last_price'] for k, v in data['data'].items()}
    except Exception as e:
        st.error(f"API Error: {e}")
    return {}

def get_strike_step(index_name):
    if "NIFTY" in index_name and "BANK" not in index_name: return 50
    if "BANKNIFTY" in index_name: return 100
    if "SENSEX" in index_name: return 100
    return 50

def round_to_strike(price, step):
    return round(price / step) * step

def construct_symbol(index, expiry, strike, opt_type):
    """
    Constructs the Upstox Trading Symbol.
    Format example: NSE_FO|NIFTY28DEC21500CE
    """
    # Standard Format: EXCHANGE|INDEX + EXPIRY + STRIKE + TYPE
    prefix = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{prefix}|{index}{expiry}{strike}{opt_type}"

# --- 3. SESSION STATE ---
if 'history' not in st.session_state:
    st.session_state['history'] = {
        'NIFTY': pd.DataFrame(),
        'BANKNIFTY': pd.DataFrame(),
        'SENSEX': pd.DataFrame()
    }

# --- 4. SIDEBAR CONTROLS ---
with st.sidebar:
    st.header("🔐 Access")
    
    # ✅ CORRECTED LINE: Using text_input instead of text_area for password masking
    access_token = st.text_input("Daily Access Token", type="password", help="Paste generated Upstox access token here")
    
    st.divider()
    
    st.header("⚙️ Settings")
    expiry_date = st.text_input("Expiry Tag", value="26DEC24", help="Format: DDMMMYY (e.g., 26DEC24)")
    refresh_rate = st.slider("Update Speed (sec)", 1, 10, 2)
    
    run_engine = st.toggle("ACTIVATE FEED", value=False)
    
    if st.button("Clear Charts"):
        st.session_state['history'] = {
        'NIFTY': pd.DataFrame(),
        'BANKNIFTY': pd.DataFrame(),
        'SENSEX': pd.DataFrame()
    }

# --- 5. MAIN LOGIC ---

# Defined Indices and their Spot Instrument Keys
indices_config = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "step": 100} 
}

st.title("⚡ Dynamic Straddle Monitor")

# Create Tabs
tab1, tab2, tab3 = st.tabs(["🟦 NIFTY 50", "🟩 BANK NIFTY", "🟪 SENSEX"])

def render_index_tab(index_name):
    """
    Renders the UI and Logic for a single index tab.
    """
    cfg = indices_config[index_name]
    
    # 1. Placeholders for Layout
    col_spot, col_straddle, col_iv = st.columns([1,2,1])
    chart_container = st.empty()
    table_container = st.empty()

    if run_engine and access_token:
        # A. Get Spot Price
        ltp_data = fetch_ltp(access_token, [cfg['key']])
        spot_price = ltp_data.get(cfg['key'], 0)
        
        if spot_price > 0:
            # B. Calculate ATM and Strikes
            atm_strike = round_to_strike(spot_price, cfg['step'])
            
            # Construct ATM Symbols to get Straddle Price first
            ce_atm_sym = construct_symbol(index_name, expiry_date, atm_strike, "CE")
            pe_atm_sym = construct_symbol(index_name, expiry_date, atm_strike, "PE")
            
            # Fetch ATM Premiums
            opt_data = fetch_ltp(access_token, [ce_atm_sym, pe_atm_sym])
            ce_price = opt_data.get(ce_atm_sym, 0)
            pe_price = opt_data.get(pe_atm_sym, 0)
            straddle_price = ce_price + pe_price
            
            # C. Dynamic SD Calculation 
            sd_range = straddle_price 
            
            strikes = {
                "ATM": {"ce": atm_strike, "pe": atm_strike},
                "1.0 SD": {"ce": round_to_strike(spot_price + sd_range, cfg['step']), 
                           "pe": round_to_strike(spot_price - sd_range, cfg['step'])},
                "1.5 SD": {"ce": round_to_strike(spot_price + (sd_range*1.5), cfg['step']), 
                           "pe": round_to_strike(spot_price - (sd_range*1.5), cfg['step'])},
                "2.0 SD": {"ce": round_to_strike(spot_price + (sd_range*2.0), cfg['step']), 
                           "pe": round_to_strike(spot_price - (sd_range*2.0), cfg['step'])},
            }
            
            # Construct ALL symbols to fetch in one batch
            batch_symbols = []
            for k, v in strikes.items():
                batch_symbols.append(construct_symbol(index_name, expiry_date, v['ce'], "CE"))
                batch_symbols.append(construct_symbol(index_name, expiry_date, v['pe'], "PE"))
            
            # Fetch All SD Premiums
            premium_data = fetch_ltp(access_token, batch_symbols)
            
            # D. Organize Data for Display
            display_rows = []
            timestamp = datetime.now().strftime("%H:%M:%S")
            chart_updates = {"Time": timestamp}
            
            for sd_level, s in strikes.items():
                ce_s = construct_symbol(index_name, expiry_date, s['ce'], "CE")
                pe_s = construct_symbol(index_name, expiry_date, s['pe'], "PE")
                
                c_ltp = premium_data.get(ce_s, 0)
                p_ltp = premium_data.get(pe_s, 0)
                combined = c_ltp + p_ltp
                
                display_rows.append({
                    "Level": sd_level,
                    "CE Strike": s['ce'],
                    "CE LTP": c_ltp,
                    "PE Strike": s['pe'],
                    "PE LTP": p_ltp,
                    "Combined Premium": combined
                })
                
                # Add to Chart Data (Tracking Combined Premiums)
                chart_updates[f"{sd_level} Premium"] = combined

            # E. Update UI
            with col_spot:
                st.metric("Spot Price", spot_price)
            with col_straddle:
                st.metric("ATM Straddle", f"{straddle_price:.2f}", delta=None)

            # Update History for Chart
            new_row = pd.DataFrame([chart_updates])
            if not new_row.empty:
                st.session_state['history'][index_name] = pd.concat(
                    [st.session_state['history'][index_name], new_row]
                ).tail(100) # Keep last 100 points to save RAM
            
            # Render Table
            df_display = pd.DataFrame(display_rows)
            table_container.dataframe(df_display, use_container_width=True, hide_index=True)
            
            # Render Line Chart
            chart_df = st.session_state['history'][index_name].set_index("Time")
            chart_container.line_chart(chart_df)

    else:
        st.info("Waiting for Token & Start...")

# --- 6. RENDER ALL TABS ---

with tab1:
    render_index_tab("NIFTY")
    
with tab2:
    render_index_tab("BANKNIFTY")

with tab3:
    render_index_tab("SENSEX")

# Loop Trigger (Simulates Live Feed in Streamlit)
if run_engine:
    time.sleep(refresh_rate)
    st.rerun()