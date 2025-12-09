import streamlit as st
import pandas as pd
import time
import requests
import math
from datetime import datetime, date

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Straddle Monitor", layout="wide", page_icon="⚡")

# --- 2. PROFESSIONAL STYLING (StraddleChart Clone) ---
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        
        /* Card Styling for Info Deck */
        .info-card {
            background-color: #1e1e1e;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #333;
            text-align: center;
        }
        .info-label { font-size: 11px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }
        .info-value { font-size: 18px; color: #fff; font-weight: 600; }
        .highlight-value { color: #00e676; } /* Green for Price */
        
        /* Chart Container Border */
        .chart-box {
            border: 1px solid #333;
            border-radius: 5px;
            padding: 5px;
            margin-top: 10px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 3. GLOBAL STATE & CONFIG ---
if 'store' not in st.session_state:
    st.session_state['store'] = {} # Stores dataframe per panel

INDICES = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "step": 100},
    "FINNIFTY": {"key": "NSE_INDEX|Nifty Fin Service", "step": 50},
}

# --- 4. UPSTOX API HELPERS ---
def get_upstox_expiry(date_obj):
    # Formats date to '26DEC24'
    return date_obj.strftime("%d%b%y").upper()

def construct_symbol(index, expiry, strike, type_):
    exch = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{exch}|{index}{expiry}{strike}{type_}"

def fetch_data(token, symbols):
    if not token or not symbols: return {}
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = requests.get(url, headers=headers, params={'instrument_key': ",".join(symbols)}, timeout=2)
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return {k: v['last_price'] for k, v in data.items()}
    except:
        return {}
    return {}

# --- 5. THE CORE ENGINE (Calculations) ---
def run_panel_logic(token, index_name, expiry_date):
    """
    Returns: (SpotPrice, ATMStrike, StraddlePrice, ChartDataDict, ErrorMsg)
    """
    if not token: return 0, 0, 0, None, "Token Missing"
    
    cfg = INDICES[index_name]
    expiry_tag = get_upstox_expiry(expiry_date)
    
    # 1. Fetch Spot
    spot_map = fetch_data(token, [cfg['key']])
    spot_price = spot_map.get(cfg['key'])
    
    # --- CRASH FIX: CHECK IF SPOT IS NONE ---
    if spot_price is None or spot_price == 0:
        return 0, 0, 0, None, "Waiting for Market Data..."

    # 2. Calculate Strikes
    atm_strike = round(spot_price / cfg['step']) * cfg['step']
    
    # 3. Fetch ATM Straddle (To get SD Width)
    ce_atm = construct_symbol(index_name, expiry_tag, atm_strike, "CE")
    pe_atm = construct_symbol(index_name, expiry_tag, atm_strike, "PE")
    
    atm_data = fetch_data(token, [ce_atm, pe_atm])
    atm_prem = atm_data.get(ce_atm, 0) + atm_data.get(pe_atm, 0)
    
    if atm_prem == 0:
        return spot_price, atm_strike, 0, None, "Options Data Unavailable"

    # 4. Define SD Strikes (Dynamic)
    sd_val = atm_prem
    targets = {
        "ATM Straddle": {"c": atm_strike, "p": atm_strike},
        "1.0 SD": {"c": round((spot_price + sd_val)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val)/cfg['step'])*cfg['step']},
        "1.5 SD": {"c": round((spot_price + sd_val*1.5)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val*1.5)/cfg['step'])*cfg['step']},
        "2.0 SD": {"c": round((spot_price + sd_val*2.0)/cfg['step'])*cfg['step'], 
                   "p": round((spot_price - sd_val*2.0)/cfg['step'])*cfg['step']}
    }
    
    # 5. Fetch All SD Premiums
    symbols_to_fetch = []
    for t in targets.values():
        symbols_to_fetch.append(construct_symbol(index_name, expiry_tag, t['c'], "CE"))
        symbols_to_fetch.append(construct_symbol(index_name, expiry_tag, t['p'], "PE"))
        
    premium_map = fetch_data(token, symbols_to_fetch)
    
    # 6. Build Result
    chart_row = {"Time": datetime.now().strftime("%H:%M:%S")}
    for name, t in targets.items():
        c_s = construct_symbol(index_name, expiry_tag, t['c'], "CE")
        p_s = construct_symbol(index_name, expiry_tag, t['p'], "PE")
        chart_row[name] = premium_map.get(c_s, 0) + premium_map.get(p_s, 0)
        
    return spot_price, atm_strike, atm_prem, chart_row, None

# --- 6. UI COMPONENT: THE PANEL ---
def render_panel(panel_id, default_index):
    """
    Renders a single "StraddleChart" style panel.
    """
    # Unique keys for widgets using panel_id
    with st.container(border=True):
        
        # A. HEADER CONTROLS (Index | Expiry)
        c1, c2, c3 = st.columns([1.5, 1.5, 2])
        with c1:
            sel_index = st.selectbox(f"Index", list(INDICES.keys()), index=list(INDICES.keys()).index(default_index), key=f"idx_{panel_id}", label_visibility="collapsed")
        with c2:
            sel_date = st.date_input(f"Expiry", min_value=date.today(), key=f"date_{panel_id}", label_visibility="collapsed")
        with c3:
            st.caption(f"LIVE • {get_upstox_expiry(sel_date)}")

        # B. RUN LOGIC
        spot, atm, straddle, row_data, err = run_panel_logic(token, sel_index, sel_date)
        
        # C. INFO DECK (Stats Row)
        # Layout: DTE | SPOT | ATM STRIKE | STRADDLE PRICE
        dte = (sel_date - date.today()).days
        
        k1, k2, k3, k4 = st.columns(4)
        
        # HTML Cards for precise styling
        k1.markdown(f"""<div class="info-card"><div class="info-label">DTE</div><div class="info-value">{dte}</div></div>""", unsafe_allow_html=True)
        
        if err:
            st.warning(err)
        else:
            k2.markdown(f"""<div class="info-card"><div class="info-label">SPOT</div><div class="info-value">{spot}</div></div>""", unsafe_allow_html=True)
            k3.markdown(f"""<div class="info-card"><div class="info-label">ATM STRIKE</div><div class="info-value">{atm}</div></div>""", unsafe_allow_html=True)
            k4.markdown(f"""<div class="info-card"><div class="info-label">STRADDLE</div><div class="info-value highlight-value">{straddle:.2f}</div></div>""", unsafe_allow_html=True)

            # D. CHART UPDATE
            store_key = f"data_{panel_id}"
            if store_key not in st.session_state['store']:
                st.session_state['store'][store_key] = pd.DataFrame()
            
            if row_data:
                # Add new row
                st.session_state['store'][store_key] = pd.concat(
                    [st.session_state['store'][store_key], pd.DataFrame([row_data])], ignore_index=True
                ).tail(300) # Keep last 300 points
            
            # E. RENDER CHART
            chart_df = st.session_state['store'][store_key].set_index("Time")
            st.line_chart(chart_df, height=350, color=["#ffffff", "#ffff00", "#ffa500", "#ff0000"])

# --- 7. MAIN LAYOUT ---

# SIDEBAR (Token Only)
with st.sidebar:
    st.header("🔐 Access")
    token = st.text_input("Token", type="password", placeholder="Paste Upstox Token", label_visibility="collapsed")
    st.divider()
    layout_mode = st.radio("View Mode", ["Single Panel", "Dual Panel (Side-by-Side)"])
    st.divider()
    active = st.toggle("ACTIVATE FEED", value=False)
    
    if st.button("Clear History"):
        st.session_state['store'] = {}

# MAIN AREA
st.title("Dynamic Straddle Monitor")

if layout_mode == "Single Panel":
    render_panel("p1", "NIFTY")
else:
    # 2x1 Grid (Side by Side)
    col_left, col_right = st.columns(2)
    with col_left:
        render_panel("p1", "NIFTY")
    with col_right:
        render_panel("p2", "SENSEX")

# LOOP
if active and token:
    time.sleep(2)
    st.rerun()
elif not token:
    st.info("👈 Paste Access Token in Sidebar to start.")