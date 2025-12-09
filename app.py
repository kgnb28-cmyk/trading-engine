import streamlit as st
import pandas as pd
import time
import requests
import math
from datetime import datetime, timedelta

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Straddle Command", layout="wide", page_icon="⚡")

# Professional Dark UI CSS
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 0rem;}
        /* Hide default Streamlit menu/footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Ticker Tape Styling */
        .ticker-box {
            background-color: #1E1E1E;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #333;
            text-align: center;
            margin-bottom: 10px;
        }
        .ticker-label { font-size: 12px; color: #888; }
        .ticker-price { font-size: 18px; color: #00FF00; font-weight: bold; }
        
        /* Center Control Styling */
        .control-deck {
            background-color: #0E1117;
            border-bottom: 1px solid #333;
            padding: 10px 0px;
            margin-bottom: 20px;
            text-align: center;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL STATE ---
if 'data_store' not in st.session_state:
    st.session_state['data_store'] = {} # Stores chart data per symbol

# --- 3. UPSTOX API HANDLERS ---
INDICES_MAP = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "step": 100}
}

def get_expiry_format(date_obj):
    # Upstox Format: 26DEC24
    return date_obj.strftime("%d%b%y").upper()

def construct_symbol(index, expiry, strike, type_):
    exch = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{exch}|{index}{expiry}{strike}{type_}"

def fetch_ltp(token, symbols):
    if not token or not symbols: return {}
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = requests.get(url, headers=headers, params={'instrument_key': ",".join(symbols)}, timeout=2)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return {k: v['last_price'] for k, v in data.items()}
    except:
        pass
    return {}

# --- 4. DATA PROCESSING LOGIC ---
def process_market_data(token, index_name, expiry_tag):
    """
    Core Logic: Fetches Spot -> Calculates Strikes -> Fetches Premiums -> Returns Row
    """
    cfg = INDICES_MAP[index_name]
    
    # 1. Get Spot
    spot_map = fetch_ltp(token, [cfg['key']])
    spot_price = spot_map.get(cfg['key'], 0)
    
    if spot_price == 0:
        return None # Market data failed

    # 2. Calculate ATM & Fetch Straddle
    atm_strike = round(spot_price / cfg['step']) * cfg['step']
    ce_atm = construct_symbol(index_name, expiry_tag, atm_strike, "CE")
    pe_atm = construct_symbol(index_name, expiry_tag, atm_strike, "PE")
    
    # Fetch ATM first to determine SD Width
    atm_data = fetch_ltp(token, [ce_atm, pe_atm])
    atm_prem = atm_data.get(ce_atm, 0) + atm_data.get(pe_atm, 0)
    
    if atm_prem == 0:
        return None # Option data failed
        
    # 3. Dynamic Strike Selection (Based on Straddle Premium)
    sd_val = atm_prem
    
    strikes = {
        "ATM Straddle": {"c": atm_strike, "p": atm_strike},
        "1.0 SD": {"c": round((spot_price + sd_val)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val)/cfg['step'])*cfg['step']},
        "1.5 SD": {"c": round((spot_price + sd_val*1.5)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val*1.5)/cfg['step'])*cfg['step']},
        "2.0 SD": {"c": round((spot_price + sd_val*2.0)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val*2.0)/cfg['step'])*cfg['step']}
    }
    
    # 4. Fetch All Required Premiums
    batch_symbols = []
    for k, v in strikes.items():
        batch_symbols.append(construct_symbol(index_name, expiry_tag, v['c'], "CE"))
        batch_symbols.append(construct_symbol(index_name, expiry_tag, v['p'], "PE"))
        
    prem_map = fetch_ltp(token, batch_symbols)
    
    # 5. Build Result Row
    timestamp = datetime.now().strftime("%H:%M:%S")
    row = {"Time": timestamp}
    
    for level_name, s in strikes.items():
        c_sym = construct_symbol(index_name, expiry_tag, s['c'], "CE")
        p_sym = construct_symbol(index_name, expiry_tag, s['p'], "PE")
        combined = prem_map.get(c_sym, 0) + prem_map.get(p_sym, 0)
        row[level_name] = combined
        
    return row, spot_price

# --- 5. UI COMPONENT: CHART WIDGET ---
def render_chart_widget(title, data_key, height=500):
    """Renders a single chart container"""
    st.markdown(f"### {title}")
    chart_spot = st.empty() # Placeholder for chart
    
    if data_key in st.session_state['data_store']:
        df = st.session_state['data_store'][data_key]
        if not df.empty:
            # Reformat for multi-line chart
            chart_data = df.set_index("Time")
            
            # Custom Color Palette
            st.line_chart(
                chart_data,
                height=height,
                color=["#FFFFFF", "#FFFF00", "#FFA500", "#FF0000"] # White, Yellow, Orange, Red
            )
    else:
        st.info("Waiting for data...")

# --- 6. MAIN APP LAYOUT ---

# A. SIDEBAR (Token Only)
with st.sidebar:
    st.header("🔐 Access")
    token = st.text_input("Token", type="password", label_visibility="collapsed", placeholder="Paste Upstox Token")
    
    st.divider()
    st.subheader("Layout")
    view_mode = st.radio("Grid", ["Single View", "Split View (2x1)"], label_visibility="collapsed")
    
    st.divider()
    run_feed = st.toggle("ACTIVATE SYSTEM", value=False)
    refresh_rate = st.slider("Speed", 1, 5, 2)

# B. TOP RIGHT: TICKER TAPE
c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
spot_placeholders = {}

with c2: 
    st.markdown('<div class="ticker-box"><div class="ticker-label">NIFTY</div><div class="ticker-price" id="nifty-spot">--</div></div>', unsafe_allow_html=True)
    spot_placeholders["NIFTY"] = st.empty()
with c3: 
    st.markdown('<div class="ticker-box"><div class="ticker-label">BANKNIFTY</div><div class="ticker-price" id="bn-spot">--</div></div>', unsafe_allow_html=True)
    spot_placeholders["BANKNIFTY"] = st.empty()
with c4: 
    st.markdown('<div class="ticker-box"><div class="ticker-label">SENSEX</div><div class="ticker-price" id="sensex-spot">--</div></div>', unsafe_allow_html=True)
    spot_placeholders["SENSEX"] = st.empty()

# C. CENTER CONTROL DECK
st.markdown("---")
ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([1, 2, 1])
with ctrl_col2:
    # The "Hover Down" Buttons (Dropdowns)
    col_idx, col_exp = st.columns(2)
    with col_idx:
        selected_index = st.selectbox("Select Contract", ["NIFTY", "BANKNIFTY", "SENSEX"])
    with col_exp:
        # Defaults to Thursday of current week roughly
        today = datetime.today()
        selected_date = st.date_input("Select Expiry", min_value=today)
        expiry_tag = get_expiry_format(selected_date)

# D. CHART RENDERING AREA
st.markdown("---")

if view_mode == "Single View":
    # 1 Big Chart
    render_chart_widget(f"{selected_index} • {expiry_tag}", "MAIN_CHART", height=600)
else:
    # 2 Charts Side by Side (Example: Selected vs BankNifty)
    g1, g2 = st.columns(2)
    with g1:
        render_chart_widget(f"{selected_index} (Main)", "MAIN_CHART", height=450)
    with g2:
        # Second chart defaults to BankNifty if Main is Nifty, else Nifty
        sec_idx = "BANKNIFTY" if selected_index == "NIFTY" else "NIFTY"
        render_chart_widget(f"{sec_idx} (Compare)", "SEC_CHART", height=450)

# --- 7. ENGINE LOOP ---
if run_feed and token:
    
    # 1. Update Spots (All Indices)
    # We fetch all spot keys to update the Top Right Ticker
    spot_keys = [v['key'] for v in INDICES_MAP.values()]
    all_spots = fetch_ltp(token, spot_keys)
    
    # Update Ticker Display
    # Note: Streamlit doesn't support direct JS updates easily, so we use metrics or overwrite
    # For this version, we will just print to console log to save UI renders, 
    # or you can add st.metric logic here if you want them to flash.
    
    # 2. Update MAIN CHART Data
    main_data, main_spot = process_market_data(token, selected_index, expiry_tag)
    
    if main_data:
        if "MAIN_CHART" not in st.session_state['data_store']:
            st.session_state['data_store']["MAIN_CHART"] = pd.DataFrame()
        
        # Append and Keep last 200 rows
        st.session_state['data_store']["MAIN_CHART"] = pd.concat(
            [st.session_state['data_store']["MAIN_CHART"], pd.DataFrame([main_data])], ignore_index=True
        ).tail(200)

    # 3. Update SECONDARY CHART (If Split View is On)
    if view_mode != "Single View":
        sec_idx = "BANKNIFTY" if selected_index == "NIFTY" else "NIFTY"
        sec_data, _ = process_market_data(token, sec_idx, expiry_tag)
        if sec_data:
            if "SEC_CHART" not in st.session_state['data_store']:
                st.session_state['data_store']["SEC_CHART"] = pd.DataFrame()
            st.session_state['data_store']["SEC_CHART"] = pd.concat(
                [st.session_state['data_store']["SEC_CHART"], pd.DataFrame([sec_data])], ignore_index=True
            ).tail(200)

    # 4. Loop Control
    time.sleep(refresh_rate)
    st.rerun()

elif not token:
    st.warning("⚠️ Please enter Access Token in Sidebar to start.")