import streamlit as st
import pandas as pd
import time
import requests
from datetime import datetime

# --- 1. SETUP & STYLE (Chart-Focused) ---
st.set_page_config(page_title="Straddle Master", layout="wide", page_icon="📈")

# Clean, minimal CSS to mimic professional charting tools
st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        /* Make the Chart Container stand out */
        .element-container iframe {border: 1px solid #333; border-radius: 5px;}
        /* Metrics styling */
        div[data-testid="stMetricValue"] {font-size: 18px; color: #00e676;}
        div[data-testid="stMetricLabel"] {font-size: 12px; color: #888;}
    </style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURATION & STATE ---
if 'data_history' not in st.session_state:
    st.session_state['data_history'] = {}  # Stores dataframe per index

# Indices Configuration (Tick Size & Spot Keys)
INDICES = {
    "NIFTY": {"spot_key": "NSE_INDEX|Nifty 50", "step": 50},
    "BANKNIFTY": {"spot_key": "NSE_INDEX|Nifty Bank", "step": 100},
    "SENSEX": {"spot_key": "BSE_INDEX|SENSEX", "step": 100}
}

# --- 3. HELPER FUNCTIONS ---

def get_upstox_format(date_obj):
    # Converts Date Picker to Upstox Format (e.g., 26DEC24)
    # Upstox Format: DDMMMYY (e.g. 26 + DEC + 24)
    return date_obj.strftime("%d%b%y").upper()

def construct_symbol(index, expiry_str, strike, type_):
    # Example: NSE_FO|NIFTY26DEC2424500CE
    exchange = "BSE_FO" if index == "SENSEX" else "NSE_FO"
    return f"{exchange}|{index}{expiry_str}{strike}{type_}"

def fetch_market_data(token, symbols):
    if not symbols: return {}
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        response = requests.get(url, headers=headers, params={'instrument_key': ",".join(symbols)}, timeout=3)
        if response.status_code == 200:
            data = response.json()
            # Return simple Map: {Symbol: Price}
            return {k: v['last_price'] for k, v in data.get('data', {}).items()}
        else:
            return {"error": f"API {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

# --- 4. SIDEBAR (One-Time Setup) ---
with st.sidebar:
    st.title("⚙️ Engine Room")
    
    # Token Input (Hidden)
    token = st.text_input("Upstox Access Token", type="password", placeholder="Paste daily token here...")
    
    # Global Expiry Picker (User picks date, we format it)
    expiry_input = st.date_input("Select Expiry Date", min_value=datetime.today())
    expiry_tag = get_upstox_format(expiry_input) # Converts to 12DEC25 automatically
    
    st.info(f"Generated Expiry Tag: **{expiry_tag}**")
    
    refresh_rate = st.slider("Chart Update (sec)", 1, 5, 1)
    active = st.toggle("🔴 LIVE FEED", value=False)
    
    if st.button("Clear Chart History"):
        st.session_state['data_history'] = {}

# --- 5. MAIN UI (StraddleChart Style) ---

# Top Bar: Index Selection (Horizontal Tabs)
selected_index = st.radio("Select Index", ["NIFTY", "BANKNIFTY", "SENSEX"], horizontal=True, label_visibility="collapsed")

col_main, col_debug = st.columns([4, 1])

with col_main:
    st.subheader(f"{selected_index} • {expiry_tag} • LIVE")
    chart_placeholder = st.empty()

# --- 6. THE ENGINE LOOP ---
if active and token:
    
    # A. FETCH SPOT
    idx_cfg = INDICES[selected_index]
    spot_data = fetch_market_data(token, [idx_cfg['spot_key']])
    
    if "error" in spot_data:
        st.error(f"❌ Connection Failed: {spot_data['error']}")
    elif not spot_data:
        st.warning("⚠️ No Data. Token might be invalid or Market Closed.")
    else:
        # B. CALCULATE STRIKES
        spot_price = spot_data.get(idx_cfg['spot_key'])
        atm_strike = round(spot_price / idx_cfg['step']) * idx_cfg['step']
        
        # 1. Generate ATM Symbols
        ce_atm = construct_symbol(selected_index, expiry_tag, atm_strike, "CE")
        pe_atm = construct_symbol(selected_index, expiry_tag, atm_strike, "PE")
        
        # 2. Fetch ATM Premiums (To calculate SD Width)
        atm_data = fetch_market_data(token, [ce_atm, pe_atm])
        atm_premium = atm_data.get(ce_atm, 0) + atm_data.get(pe_atm, 0)
        
        if atm_premium > 0:
            # C. DEFINE SD LEVELS (Dynamic)
            # StraddleChart Logic: 
            # 1.0 SD = Spot +/- StraddlePrice
            # 0.5 SD = Spot +/- (StraddlePrice * 0.5) 
            
            levels = {
                "ATM": {"c": atm_strike, "p": atm_strike},
                "0.5 SD": {"c": round( (spot_price + (atm_premium * 0.5)) / idx_cfg['step']) * idx_cfg['step'],
                           "p": round( (spot_price - (atm_premium * 0.5)) / idx_cfg['step']) * idx_cfg['step']},
                "1.0 SD": {"c": round( (spot_price + atm_premium) / idx_cfg['step']) * idx_cfg['step'],
                           "p": round( (spot_price - atm_premium) / idx_cfg['step']) * idx_cfg['step']},
            }
            
            # D. FETCH ALL OPTION PREMIUMS
            all_symbols = []
            for k, v in levels.items():
                all_symbols.append(construct_symbol(selected_index, expiry_tag, v['c'], "CE"))
                all_symbols.append(construct_symbol(selected_index, expiry_tag, v['p'], "PE"))
                
            opt_prices = fetch_market_data(token, all_symbols)
            
            # E. PREPARE PLOT DATA
            timestamp = datetime.now().strftime("%H:%M:%S")
            new_record = {"Time": timestamp}
            
            # Debug Box (Right Side)
            with col_debug:
                st.metric("SPOT", spot_price)
                st.metric("ATM STRADDLE", f"{atm_premium:.2f}")
                with st.expander("Show Symbols (Debug)"):
                    st.write(all_symbols) # Check if symbols look correct here
            
            for name, strikes in levels.items():
                c_sym = construct_symbol(selected_index, expiry_tag, strikes['c'], "CE")
                p_sym = construct_symbol(selected_index, expiry_tag, strikes['p'], "PE")
                
                c_val = opt_prices.get(c_sym, 0)
                p_val = opt_prices.get(p_sym, 0)
                
                # We plot the COMBINED PREMIUM (Straddle/Strangle Price)
                new_record[name] = c_val + p_val

            # F. UPDATE CHART
            # Initialize DF if not exists
            if selected_index not in st.session_state['data_history']:
                st.session_state['data_history'][selected_index] = pd.DataFrame()
            
            # Append new row
            df_new = pd.DataFrame([new_record])
            st.session_state['data_history'][selected_index] = pd.concat(
                [st.session_state['data_history'][selected_index], df_new], ignore_index=True
            ).tail(300) # Keep last 300 points
            
            # Draw Line Chart
            chart_df = st.session_state['data_history'][selected_index].set_index("Time")
            chart_placeholder.line_chart(chart_df, height=500)

        else:
            st.error(f"Could not fetch ATM Premium. Symbol requested: {ce_atm}")
            with col_debug:
                st.write("Raw Response:", atm_data)

    time.sleep(refresh_rate)
    st.rerun()

elif not token:
    st.info("👋 Welcome. Please enter your Upstox Token in the Sidebar to start.")