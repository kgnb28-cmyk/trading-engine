import streamlit as st
import pandas as pd
import time
import requests
import os
import random
from datetime import datetime, date
@st.cache_resource
def load_master_contract():
    """Loads the mini_master.json file with Cloud-Proof Pathing."""
    
    # 1. Get the folder where THIS script (app.py) is located
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Construct the full path to the JSON file
    file_path = os.path.join(current_dir, "mini_master.json")
    
    # 3. DEBUG: If not found, list all files so you see what is wrong
    if not os.path.exists(file_path):
        st.error(f"❌ CRITICAL ERROR: Could not find 'mini_master.json'")
        st.warning(f"I looked in this folder: {current_dir}")
        st.info(f"📂 Files actually found here: {os.listdir(current_dir)}")
        st.write("👉 Please check if the file name in GitHub matches EXACTLY (Case Sensitive!)")
        return None

    try:
        df = pd.read_json(file_path)
        return df
    except Exception as e:
        st.error(f"Error reading JSON: {e}")
        return None
# ==========================================
# 1. CONFIGURATION & STYLES
# ==========================================
st.set_page_config(page_title="Straddle Terminal", layout="wide", page_icon="⚡")

# Professional UI CSS
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        .metric-card {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px 10px;
            text-align: center;
        }
        .metric-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
        .metric-value { font-size: 22px; color: #fff; font-weight: 700; }
        .highlight-green { color: #00e676; }
        .highlight-yellow { color: #ffea00; }
        .error-box { color: #ff4b4b; background: #290000; padding: 10px; border-radius: 5px; border: 1px solid #ff4b4b; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. GLOBAL SETTINGS & DATA LOADING
# ==========================================

# ✅ CORRECTED KEYS (Title Case for Sensex is critical)
INDICES = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50, "segment": "NSE_FO"},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100, "segment": "NSE_FO"},
    "SENSEX": {"key": "BSE_INDEX|Sensex", "step": 100, "segment": "BSE_FO"}, 
    "BANKEX": {"key": "BSE_INDEX|BANKEX", "step": 100, "segment": "BSE_FO"}
}

@st.cache_resource
def load_master_contract():
    """Loads the mini_master.json file."""
    # Looks for file in the same directory as this script
    file_path = "mini_master.json"
    
    if not os.path.exists(file_path):
        return None
    try:
        df = pd.read_json(file_path)
        return df
    except Exception as e:
        st.error(f"Error reading mini_master.json: {e}")
        return None

# Load Data on Startup
MASTER_DF = load_master_contract()

if 'chart_store' not in st.session_state:
    st.session_state['chart_store'] = {}

# ==========================================
# 3. CORE LOGIC ENGINE
# ==========================================

def find_instrument_key(index_name, expiry_date, strike, option_type):
    """
    Finds the specific instrument_key from mini_master.json
    """
    if MASTER_DF is None:
        return None, "Master File Missing (mini_master.json)"

    cfg = INDICES[index_name]
    segment = cfg["segment"]
    
    # Adjust search name if needed
    search_name = index_name 
    if index_name == "NIFTY": search_name = "NIFTY" 
    if index_name == "SENSEX": search_name = "SENSEX"

    try:
        # Convert date to string format common in Upstox JSON (YYYY-MM-DD)
        exp_str = expiry_date.strftime("%Y-%m-%d")

        mask = (
            (MASTER_DF['segment'] == segment) &
            (MASTER_DF['name'] == search_name) &
            (MASTER_DF['strike_price'] == strike) &
            (MASTER_DF['instrument_type'] == option_type) &
            (MASTER_DF['expiry'].astype(str).str.contains(exp_str))
        )
        
        result = MASTER_DF[mask]
        
        if not result.empty:
            return result.iloc[0]['instrument_key'], "OK"
        else:
            return None, f"Not Found: {index_name} {strike} {option_type}"
            
    except Exception as e:
        return None, f"Lookup Error: {str(e)}"

def fetch_live_data(token, instrument_keys):
    """Fetches LTP for a list of instrument keys."""
    if not token: return {}, "No Token"
    
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        params = {'instrument_key': ",".join(instrument_keys)}
        resp = requests.get(url, headers=headers, params=params, timeout=3)
        
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            # Return Dict: {instrument_key: price}
            return {k: v['last_price'] for k, v in data.items()}, "OK"
        else:
            return {}, f"API {resp.status_code}: {resp.text}"
    except Exception as e:
        return {}, f"Conn Err: {str(e)}"

def run_strategy_logic(token, index, expiry_date, use_sim=False):
    debug_log = []
    cfg = INDICES[index]
    
    # --- SIMULATION ---
    if use_sim:
        base = 24500 if index == "NIFTY" else 80000
        spot = base + random.randint(-50, 50)
        atm = round(spot / cfg['step']) * cfg['step']
        straddle = 300 + random.randint(-10, 10)
        row = {"Time": datetime.now().strftime("%H:%M:%S"), "ATM Straddle": straddle}
        return spot, atm, straddle, row, None, ["Simulation Mode"]

    # --- REAL DATA ---
    
    # 1. Fetch Spot Price
    spot_key = cfg['key']
    spot_res, msg = fetch_live_data(token, [spot_key])
    spot_price = spot_res.get(spot_key)
    
    debug_log.append(f"1. Spot Request: {spot_key}")
    debug_log.append(f"   Result: {spot_price} ({msg})")
    
    if not spot_price:
        return 0, 0, 0, None, f"Spot Data Missing. Check Token.", debug_log

    # 2. Calculate ATM
    atm_strike = round(spot_price / cfg['step']) * cfg['step']
    
    # 3. Lookup Option Keys (CE & PE)
    ce_key, ce_err = find_instrument_key(index, expiry_date, atm_strike, "CE")
    pe_key, pe_err = find_instrument_key(index, expiry_date, atm_strike, "PE")
    
    debug_log.append(f"2. Option Keys: CE={ce_key} | PE={pe_key}")
    
    if not ce_key or not pe_key:
        return spot_price, atm_strike, 0, None, f"Key Lookup Failed: {ce_err or pe_err}", debug_log
        
    # 4. Fetch Option Prices
    opt_res, opt_msg = fetch_live_data(token, [ce_key, pe_key])
    ce_ltp = opt_res.get(ce_key)
    pe_ltp = opt_res.get(pe_key)
    
    debug_log.append(f"3. Option Prices: CE={ce_ltp} | PE={pe_ltp}")
    
    if ce_ltp is None or pe_ltp is None:
        return spot_price, atm_strike, 0, None, "Option Prices Missing", debug_log
        
    straddle_price = ce_ltp + pe_ltp
    
    # 5. Build Chart Data
    row = {
        "Time": datetime.now().strftime("%H:%M:%S"),
        "ATM Straddle": straddle_price
    }
    
    return spot_price, atm_strike, straddle_price, row, None, debug_log

# ==========================================
# 4. COMPONENT: PANEL RENDER
# ==========================================
def render_panel(panel_id, default_idx):
    with st.container(border=True):
        
        # Header
        c1, c2, c3 = st.columns([2, 2, 4])
        with c1: 
            sel_idx = st.selectbox("Index", list(INDICES.keys()), index=list(INDICES.keys()).index(default_idx), key=f"i_{panel_id}", label_visibility="collapsed")
        with c2: 
            sel_date = st.date_input("Expiry", min_value=date.today(), key=f"d_{panel_id}", label_visibility="collapsed")
        with c3: 
            st.caption(f"LIVE • {sel_date.strftime('%d-%b-%Y')}")

        # Check for Master File
        if MASTER_DF is None:
            st.error("❌ 'mini_master.json' not found. Please run the shrink script and place the file here.")
            return

        # Execution
        spot, atm, straddle, row, err, debug_info = run_strategy_logic(token, sel_idx, sel_date, use_sim=is_sim)
        
        # Display
        if err:
            st.markdown(f'<div class="error-box">⚠️ {err}</div>', unsafe_allow_html=True)
            with st.expander("🔍 Debug Logs"):
                for line in debug_info: st.text(line)
        else:
            # Stats Grid
            k1, k2, k3, k4 = st.columns(4)
            dte = (sel_date - date.today()).days
            k1.markdown(f'<div class="metric-card"><div class="metric-label">DTE</div><div class="metric-value">{dte}</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="metric-card"><div class="metric-label">SPOT</div><div class="metric-value">{spot}</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="metric-card"><div class="metric-label">ATM</div><div class="metric-value highlight-yellow">{atm}</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="metric-card"><div class="metric-label">PREMIUM</div><div class="metric-value highlight-green">{straddle:.2f}</div></div>', unsafe_allow_html=True)
            
            # Charting
            key = f"data_{panel_id}"
            if key not in st.session_state['chart_store']: 
                st.session_state['chart_store'][key] = pd.DataFrame()
            
            if row:
                st.session_state['chart_store'][key] = pd.concat([st.session_state['chart_store'][key], pd.DataFrame([row])], ignore_index=True).tail(100)
            
            chart_df = st.session_state['chart_store'][key]
            if not chart_df.empty:
                st.line_chart(chart_df.set_index("Time"), height=350, color=["#00e676"])

# ==========================================
# 5. MAIN LAYOUT & SIDEBAR
# ==========================================
with st.sidebar:
    st.header("⚡ Settings")
    token = st.text_input("API Token", type="password", placeholder="Paste access token here")
    st.divider()
    is_sim = st.toggle("🛠 Simulation Mode", value=False)
    view_mode = st.radio("Layout", ["Single Panel", "Dual Panel"])
    st.divider()
    active = st.toggle("🔴 ACTIVATE FEED", value=False)
    if st.button("🗑️ Clear Charts"): st.session_state['chart_store'] = {}

# Layout Logic
if view_mode == "Single Panel":
    render_panel("p1", "SENSEX")
else:
    c_left, c_right = st.columns(2)
    with c_left: render_panel("p1", "NIFTY")
    with c_right: render_panel("p2", "SENSEX")

# Auto-Refresh Loop
if active:
    time.sleep(2)
    st.rerun()