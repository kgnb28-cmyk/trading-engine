import streamlit as st
import pandas as pd
import time
import requests
import random
from datetime import datetime, date, timedelta

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="Straddle Terminal", layout="wide", page_icon="⚡")

# Custom CSS to match the 'StraddleChart' Professional Look
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 2rem;}
        
        /* The Info Deck Cards (Spot, ATM, Price) */
        .metric-card {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px 10px;
            text-align: center;
        }
        .metric-label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
        .metric-value { font-size: 22px; color: #fff; font-weight: 700; }
        .highlight-green { color: #00e676; }
        .highlight-yellow { color: #ffea00; }
        
        /* Ticker Tape at Top */
        .ticker-text { font-size: 14px; font-weight: bold; color: #aaa; margin-right: 15px; }
        .ticker-up { color: #00e676; }
    </style>
""", unsafe_allow_html=True)

# --- 2. GLOBAL SETTINGS ---
INDICES = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "step": 100},
    "FINNIFTY": {"key": "NSE_INDEX|Nifty Fin Service", "step": 50},
}

if 'chart_store' not in st.session_state:
    st.session_state['chart_store'] = {} # Stores data frames

# --- 3. DATA ENGINE (ROBUST) ---

def get_upstox_fmt(d):
    return d.strftime("%d%b%y").upper()

def construct_symbol(index, expiry, strike, type_):
    exch = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{exch}|{index}{expiry}{strike}{type_}"

def fetch_live_data(token, symbols):
    if not token: return {}
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = requests.get(url, headers=headers, params={'instrument_key': ",".join(symbols)}, timeout=2)
        if resp.status_code == 200:
            d = resp.json().get('data', {})
            return {k: v['last_price'] for k, v in d.items()}
    except:
        pass
    return {}

def run_strategy_logic(token, index, expiry_date, use_sim=False):
    """
    Returns: (Spot, ATM_Strike, Straddle_Price, Chart_Row_Dict, Error_Msg)
    CRITICAL: Handles 'None' data to prevent crashes.
    """
    cfg = INDICES[index]
    exp_tag = get_upstox_fmt(expiry_date)
    
    # --- SIMULATION MODE (For testing when market is closed) ---
    if use_sim:
        # Generate fake realistic data so you can see the chart working
        base_spot = 24500 if index == "NIFTY" else 52000
        spot = base_spot + random.randint(-50, 50)
        atm = round(spot / cfg['step']) * cfg['step']
        straddle = 200 + random.randint(-5, 5)
        
        row = {
            "Time": datetime.now().strftime("%H:%M:%S"),
            "ATM Straddle": straddle,
            "1.0 SD": straddle * 0.8,
            "1.5 SD": straddle * 0.6,
            "2.0 SD": straddle * 0.4
        }
        return spot, atm, straddle, row, None

    # --- REAL LIVE MODE ---
    if not token: return 0, 0, 0, None, "Token Missing"

    # 1. Fetch Spot
    spot_data = fetch_live_data(token, [cfg['key']])
    spot_price = spot_data.get(cfg['key'])
    
    # SAFETY CHECK: If API returns None, stop here.
    if spot_price is None:
        return 0, 0, 0, None, "No Data (Check Token/Market)"

    # 2. Calculate Strikes
    atm_strike = round(spot_price / cfg['step']) * cfg['step']
    
    # 3. Fetch ATM Straddle
    ce_sym = construct_symbol(index, exp_tag, atm_strike, "CE")
    pe_sym = construct_symbol(index, exp_tag, atm_strike, "PE")
    
    atm_res = fetch_live_data(token, [ce_sym, pe_sym])
    c_ltp = atm_res.get(ce_sym)
    p_ltp = atm_res.get(pe_sym)
    
    # SAFETY CHECK: If Options data is missing
    if c_ltp is None or p_ltp is None:
        return spot_price, atm_strike, 0, None, "Options Data Missing"
        
    atm_prem = c_ltp + p_ltp
    
    # 4. Calculate SD Strikes
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
    
    # 5. Fetch All SD Premiums
    all_syms = []
    for s in strikes.values():
        all_syms.append(construct_symbol(index, exp_tag, s['c'], "CE"))
        all_syms.append(construct_symbol(index, exp_tag, s['p'], "PE"))
        
    all_data = fetch_live_data(token, all_syms)
    
    # 6. Build Chart Row
    row = {"Time": datetime.now().strftime("%H:%M:%S")}
    for name, s in strikes.items():
        c = construct_symbol(index, exp_tag, s['c'], "CE")
        p = construct_symbol(index, exp_tag, s['p'], "PE")
        val_c = all_data.get(c, 0) or 0 # Default to 0 if None
        val_p = all_data.get(p, 0) or 0
        row[name] = val_c + val_p
        
    return spot_price, atm_strike, atm_prem, row, None

# --- 4. COMPONENT: SINGLE CHART PANEL ---
def render_terminal_panel(panel_id, default_idx):
    """
    Renders one full trading chart block (Header -> Info Deck -> Chart)
    """
    # Unique container
    with st.container(border=True):
        
        # A. HEADER (Controls)
        c_idx, c_date, c_status = st.columns([2, 2, 4])
        with c_idx:
            sel_idx = st.selectbox("Index", list(INDICES.keys()), index=list(INDICES.keys()).index(default_idx), key=f"i_{panel_id}", label_visibility="collapsed")
        with c_date:
            sel_date = st.date_input("Expiry", min_value=date.today(), key=f"d_{panel_id}", label_visibility="collapsed")
        with c_status:
             st.caption(f"LIVE • {get_upstox_fmt(sel_date)} • {sel_idx}")

        # B. RUN LOGIC
        spot, atm, straddle, row, err = run_strategy_logic(token, sel_idx, sel_date, use_sim=is_sim)
        
        # C. INFO DECK (The 4 Boxes)
        if err:
            st.warning(f"⚠️ {err}")
        else:
            k1, k2, k3, k4 = st.columns(4)
            dte = (sel_date - date.today()).days
            
            # HTML Injection for "Card" Look
            k1.markdown(f'<div class="metric-card"><div class="metric-label">DTE</div><div class="metric-value">{dte}</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="metric-card"><div class="metric-label">SPOT PRICE</div><div class="metric-value">{spot}</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="metric-card"><div class="metric-label">ATM STRIKE</div><div class="metric-value highlight-yellow">{atm}</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="metric-card"><div class="metric-label">STRADDLE</div><div class="metric-value highlight-green">{straddle:.2f}</div></div>', unsafe_allow_html=True)

            # D. UPDATE & DRAW CHART
            key = f"data_{panel_id}"
            if key not in st.session_state['chart_store']:
                st.session_state['chart_store'][key] = pd.DataFrame()
            
            if row:
                st.session_state['chart_store'][key] = pd.concat(
                    [st.session_state['chart_store'][key], pd.DataFrame([row])], ignore_index=True
                ).tail(300)
            
            df = st.session_state['chart_store'][key].set_index("Time")
            
            # Professional Chart Colors: White(ATM), Yellow(1SD), Orange(1.5SD), Red(2SD)
            st.line_chart(df, height=400, color=["#ffffff", "#ffff00", "#ffa500", "#ff4b4b"])


# --- 5. MAIN LAYOUT EXECUTION ---

# SIDEBAR: Minimal (Token Only)
with st.sidebar:
    st.header("🔐 Auth")
    token = st.text_input("Token", type="password", placeholder="Paste Upstox Token", label_visibility="collapsed")
    st.divider()
    
    st.subheader("Testing")
    is_sim = st.toggle("🛠 Simulation Mode", value=False, help="Turn ON to test charts with fake data if market is closed.")
    
    st.divider()
    view_mode = st.radio("View", ["Single Panel", "Dual Panel (2x1)"])
    
    st.divider()
    active = st.toggle("ACTIVATE FEED", value=False)
    if st.button("Clear History"):
        st.session_state['chart_store'] = {}

# TOP TICKER TAPE
st.markdown(f"""
    <div style="background:#0e1117; padding:10px; border-bottom:1px solid #333; margin-bottom:20px;">
        <span class="ticker-text">NIFTY <span class="ticker-up">LIVE</span></span>
        <span class="ticker-text">BANKNIFTY <span class="ticker-up">LIVE</span></span>
        <span class="ticker-text">SENSEX <span class="ticker-up">LIVE</span></span>
    </div>
""", unsafe_allow_html=True)

# DASHBOARD RENDER
if view_mode == "Single Panel":
    render_terminal_panel("p1", "NIFTY")
else:
    c_left, c_right = st.columns(2)
    with c_left:
        render_terminal_panel("p1", "NIFTY")
    with c_right:
        render_terminal_panel("p2", "SENSEX")

# LOOP TRIGGER
if active:
    time.sleep(2)
    st.rerun()