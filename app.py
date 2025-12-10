import streamlit as st
import pandas as pd
import time
import requests
import random
from datetime import datetime, date

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Straddle Terminal", layout="wide", page_icon="⚡")

# Professional UI CSS (StraddleChart Clone)
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
        .debug-box { font-family: monospace; font-size: 12px; color: #ff4b4b; background: #111; padding: 10px; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL SETTINGS ---
INDICES = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "step": 100},
}

if 'chart_store' not in st.session_state:
    st.session_state['chart_store'] = {} 

# --- 3. DATA ENGINE ---

def get_upstox_fmt(d):
    # Converts 16 Dec 2025 -> 16DEC25
    return d.strftime("%d%b%y").upper()

def construct_symbol(index, expiry, strike, type_):
    exch = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{exch}|{index}{expiry}{strike}{type_}"

def fetch_live_data(token, symbols):
    if not token: return {}, "No Token"
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        # Request Data
        resp = requests.get(url, headers=headers, params={'instrument_key': ",".join(symbols)}, timeout=2)
        
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            # Return Data and Success Message
            return {k: v['last_price'] for k, v in d.items()}, "OK"
        else:
            # Return Error Code
            return {}, f"API Error {resp.status_code}: {resp.text}"
    except Exception as e:
        return {}, f"Connection Error: {str(e)}"

def run_strategy_logic(token, index, expiry_date, use_sim=False):
    """
    Returns: (Spot, ATM, Straddle, Row, ErrorMsg, DebugInfo)
    """
    cfg = INDICES[index]
    exp_tag = get_upstox_fmt(expiry_date)
    debug_log = [] # To store details for the Debug Panel
    
    # --- SIMULATION (For Testing) ---
    if use_sim:
        base = 24500 if index == "NIFTY" else 52000
        spot = base + random.randint(-50, 50)
        atm = round(spot / cfg['step']) * cfg['step']
        straddle = 200 + random.randint(-5, 5)
        row = {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "ATM Straddle": straddle,
            "1.0 SD": straddle * 0.8, "1.5 SD": straddle * 0.6, "2.0 SD": straddle * 0.4
        }
        return spot, atm, straddle, row, None, ["Simulation Active"]

    # --- REAL LIVE DATA ---
    
    # 1. Fetch Spot
    spot_data, status = fetch_live_data(token, [cfg['key']])
    spot_price = spot_data.get(cfg['key'])
    
    debug_log.append(f"1. Spot Request: {cfg['key']}")
    debug_log.append(f"   Result: {spot_price} (Status: {status})")

    if spot_price is None:
        return 0, 0, 0, None, "Spot Data Missing", debug_log

    # 2. Calculate ATM
    atm_strike = round(spot_price / cfg['step']) * cfg['step']
    
    # 3. Fetch ATM Straddle
    ce_sym = construct_symbol(index, exp_tag, atm_strike, "CE")
    pe_sym = construct_symbol(index, exp_tag, atm_strike, "PE")
    
    atm_res, status_opt = fetch_live_data(token, [ce_sym, pe_sym])
    c_ltp = atm_res.get(ce_sym)
    p_ltp = atm_res.get(pe_sym)
    
    debug_log.append(f"2. Option Request: {ce_sym} & {pe_sym}")
    debug_log.append(f"   Result: CE={c_ltp}, PE={p_ltp}")
    
    if c_ltp is None or p_ltp is None:
        return spot_price, atm_strike, 0, None, "Invalid Symbol/Expiry", debug_log
        
    atm_prem = c_ltp + p_ltp
    
    # 4. Fetch SD Levels
    sd_val = atm_prem
    strikes = {
        "ATM Straddle": {"c": atm_strike, "p": atm_strike},
        "1.0 SD": {"c": round((spot_price + sd_val)/cfg['step'])*cfg['step'], "p": round((spot_price - sd_val)/cfg['step'])*cfg['step']},
        "1.5 SD": {"c": round((spot_price + sd_val*1.5)/cfg['step'])*cfg['step'], "p": round((spot_price - sd_val*1.5)/cfg['step'])*cfg['step']},
        "2.0 SD": {"c": round((spot_price + sd_val*2.0)/cfg['step'])*cfg['step'], "p": round((spot_price - sd_val*2.0)/cfg['step'])*cfg['step']}
    }
    
    all_syms = []
    for s in strikes.values():
        all_syms.append(construct_symbol(index, exp_tag, s['c'], "CE"))
        all_syms.append(construct_symbol(index, exp_tag, s['p'], "PE"))
        
    all_data, _ = fetch_live_data(token, all_syms)
    
    row = {"Time": datetime.now().strftime("%H:%M:%S")}
    for name, s in strikes.items():
        c = construct_symbol(index, exp_tag, s['c'], "CE")
        p = construct_symbol(index, exp_tag, s['p'], "PE")
        v_c = all_data.get(c, 0) or 0
        v_p = all_data.get(p, 0) or 0
        row[name] = v_c + v_p
        
    return spot_price, atm_strike, atm_prem, row, None, debug_log

# --- 4. COMPONENT: PANEL RENDER ---
def render_panel(panel_id, default_idx):
    with st.container(border=True):
        
        # Header Controls
        c1, c2, c3 = st.columns([2, 2, 4])
        with c1: sel_idx = st.selectbox("Index", list(INDICES.keys()), index=list(INDICES.keys()).index(default_idx), key=f"i_{panel_id}", label_visibility="collapsed")
        with c2: sel_date = st.date_input("Expiry", min_value=date.today(), key=f"d_{panel_id}", label_visibility="collapsed")
        with c3: st.caption(f"LIVE • {get_upstox_fmt(sel_date)}")

        # Execution
        spot, atm, straddle, row, err, debug_info = run_strategy_logic(token, sel_idx, sel_date, use_sim=is_sim)
        
        # Visuals
        if err:
            st.error(f"⚠️ {err}")
            # DEBUG EXPANDER (Only shows if there is an error)
            with st.expander("🔍 Debug: Why did this fail?"):
                st.write(f"**Generated Expiry Tag:** {get_upstox_fmt(sel_date)}")
                for log in debug_info:
                    st.text(log)
                st.info("Check if the Date selected matches the exact Expiry Date of the contract.")
        else:
            # Stats Deck
            k1, k2, k3, k4 = st.columns(4)
            dte = (sel_date - date.today()).days
            k1.markdown(f'<div class="metric-card"><div class="metric-label">DTE</div><div class="metric-value">{dte}</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="metric-card"><div class="metric-label">SPOT</div><div class="metric-value">{spot}</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="metric-card"><div class="metric-label">ATM</div><div class="metric-value highlight-yellow">{atm}</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="metric-card"><div class="metric-label">STRADDLE</div><div class="metric-value highlight-green">{straddle:.2f}</div></div>', unsafe_allow_html=True)

            # Chart Logic
            key = f"data_{panel_id}"
            if key not in st.session_state['chart_store']: st.session_state['chart_store'][key] = pd.DataFrame()
            if row:
                st.session_state['chart_store'][key] = pd.concat([st.session_state['chart_store'][key], pd.DataFrame([row])], ignore_index=True).tail(300)
            
            # Draw Chart
            st.line_chart(st.session_state['chart_store'][key].set_index("Time"), height=400, color=["#ffffff", "#ffff00", "#ffa500", "#ff4b4b"])

# --- 5. MAIN LAYOUT ---
with st.sidebar:
    st.header("🔐 Auth")
    token = st.text_input("Token", type="password", placeholder="Paste Upstox Token", label_visibility="collapsed")
    st.divider()
    is_sim = st.toggle("🛠 Simulation Mode", value=False)
    view_mode = st.radio("View", ["Single Panel", "Dual Panel"])
    st.divider()
    active = st.toggle("ACTIVATE FEED", value=False)
    if st.button("Clear History"): st.session_state['chart_store'] = {}

# Layout
if view_mode == "Single Panel":
    render_panel("p1", "NIFTY")
else:
    c_left, c_right = st.columns(2)
    with c_left: render_panel("p1", "NIFTY")
    with c_right: render_panel("p2", "SENSEX")

# Loop
if active:
    time.sleep(2)
    st.rerun()