import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math

# --- 1. KYOTO CAPITAL: VISUAL IDENTITY ---
st.set_page_config(
    page_title="Kyoto Capital | Straddle Engine",
    page_icon="♟️",
    layout="wide"
)

# Custom CSS: "Alta" Font styling + Modern Dark Theme
st.markdown("""
    <style>
        /* Import Fonts: Cinzel (Luxury/Alta-like) and Lato (Readability) */
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;800&family=Lato:wght@300;400;700&display=swap');
        
        /* DARK MODE OVERRIDES */
        .stApp {
            background-color: #0F172A; /* Midnight Blue/Black */
            color: #E2E8F0;
        }
        
        /* HEADERS (Alta Style) */
        h1, h2, h3, h4 {
            font-family: 'Cinzel', serif !important;
            font-weight: 600;
            color: #F8FAFC !important;
            letter-spacing: 1px;
        }
        
        /* METRICS CARDS */
        div[data-testid="stMetric"] {
            background-color: #1E293B; /* Slate Card */
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #334155;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }
        div[data-testid="stMetricLabel"] {
            font-family: 'Lato', sans-serif;
            color: #94A3B8 !important;
            font-size: 14px;
        }
        div[data-testid="stMetricValue"] {
            font-family: 'Cinzel', serif;
            color: #38BDF8 !important; /* Neon Blue */
            font-size: 28px;
        }

        /* INPUT FIELDS */
        .stTextInput > div > div > input {
            background-color: #1E293B;
            color: white;
            border: 1px solid #475569;
        }
        .stSelectbox > div > div > div {
            background-color: #1E293B;
            color: white;
        }
        
        /* SIDEBAR */
        section[data-testid="stSidebar"] {
            background-color: #1E293B;
            border-right: 1px solid #334155;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE LOGIC (NO GUESSING) ---

def get_next_thursday():
    """Calculates upcoming weekly expiry."""
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead <= 0: days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def round_to_strike(price, step):
    """Rounds any number to the nearest strike step (e.g. 234 -> 250 for Nifty)."""
    return round(price / step) * step

def fetch_market_data(access_token, symbol, expiry_date):
    """
    MASTER FUNCTION:
    1. Fetches Spot Price.
    2. Fetches Option Chain.
    3. Calculates ATM Premium.
    4. Calculates 1SD, 1.5SD, 2SD Distances based on ATM Premium.
    5. Returns ALL combined premiums.
    """
    # 1. Configuration
    if symbol == "NIFTY":
        spot_key = "NSE_INDEX|Nifty 50"
        step = 50
    else:
        spot_key = "NSE_INDEX|Nifty Bank"
        step = 100

    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}

    # 2. Get Spot Price
    try:
        url_spot = "https://api.upstox.com/v2/market-quote/ltp"
        resp_spot = requests.get(url_spot, headers=headers, params={'instrument_key': spot_key})
        spot_data = resp_spot.json()
        
        if spot_data.get('status') != 'success':
            return None, "Spot Fetch Failed"
            
        # Handle the | to : swap
        spot_val = spot_data['data'][spot_key.replace('|', ':')]['last_price']
        
    except Exception as e:
        return None, f"API Error: {e}"

    # 3. Calculate ATM Strike
    atm_strike = round_to_strike(spot_val, step)

    # 4. Fetch Option Chain to find premiums
    try:
        url_chain = "https://api.upstox.com/v2/option/chain"
        params_chain = {'instrument_key': spot_key, 'expiry_date': expiry_date}
        resp_chain = requests.get(url_chain, headers=headers, params=params_chain)
        chain_data = resp_chain.json()
        
        if chain_data.get('status') != 'success':
            return None, "Option Chain Failed (Check Expiry)"
            
        options_list = chain_data['data']
        
        # 5. Extract ATM Keys & Premium FIRST (Crucial for SD Logic)
        atm_ce_key = None
        atm_pe_key = None
        
        # Helper dictionary to store all strikes for fast lookup
        strike_map = {} 
        
        for item in options_list:
            strike = item['strike_price']
            strike_map[strike] = {
                'CE_Key': item['call_options']['instrument_key'],
                'PE_Key': item['put_options']['instrument_key'],
                'CE_LTP': item['call_options']['market_data']['ltp'],
                'PE_LTP': item['put_options']['market_data']['ltp']
            }
            if strike == atm_strike:
                atm_ce_key = item['call_options']['instrument_key']
                atm_pe_key = item['put_options']['instrument_key']

        if atm_strike not in strike_map:
            return None, "ATM Strike not found in chain"

        # 6. CALCULATE AUTOMATED SD DISTANCES
        # Logic: Width = ATM Straddle Premium (CE + PE)
        atm_premium = strike_map[atm_strike]['CE_LTP'] + strike_map[atm_strike]['PE_LTP']
        
        # Round the premium to nearest step (e.g., 213 -> 200) to find valid strikes
        width_1sd = round_to_strike(atm_premium, step)
        width_15sd = round_to_strike(atm_premium * 1.5, step)
        width_2sd = round_to_strike(atm_premium * 2.0, step)

        # 7. Identify Strangle Strikes
        # 1 SD Strangle
        s1_upper = atm_strike + width_1sd
        s1_lower = atm_strike - width_1sd
        
        # 1.5 SD Strangle
        s15_upper = atm_strike + width_15sd
        s15_lower = atm_strike - width_15sd
        
        # 2 SD Strangle
        s2_upper = atm_strike + width_2sd
        s2_lower = atm_strike - width_2sd

        # 8. Retrieve Premiums for these Strikes
        # Helper to safely get premium sum
        def get_strangle_prem(upper, lower):
            if upper in strike_map and lower in strike_map:
                return strike_map[upper]['CE_LTP'] + strike_map[lower]['PE_LTP']
            return 0

        val_1sd = get_strangle_prem(s1_upper, s1_lower)
        val_15sd = get_strangle_prem(s15_upper, s15_lower)
        val_2sd = get_strangle_prem(s2_upper, s2_lower)

        return {
            "spot": spot_val,
            "atm_strike": atm_strike,
            "atm_straddle": atm_premium,
            "width_base": width_1sd,
            "1sd_val": val_1sd,
            "1.5sd_val": val_15sd,
            "2sd_val": val_2sd,
            "strikes": {
                "1sd": f"{int(s1_lower)} PE & {int(s1_upper)} CE",
                "1.5sd": f"{int(s15_lower)} PE & {int(s15_upper)} CE",
                "2sd": f"{int(s2_lower)} PE & {int(s2_upper)} CE"
            }
        }, None

    except Exception as e:
        return None, f"Calculation Error: {e}"

# --- 3. UI LAYOUT ---

# Sidebar
with st.sidebar:
    st.header("KYOTO CONFIG")
    ACCESS_TOKEN = st.text_input("API Token", type="password")
    symbol = st.selectbox("Instrument", ["NIFTY", "BANKNIFTY"])
    
    # Auto-date
    d_date = datetime.strptime(get_next_thursday(), "%Y-%m-%d")
    expiry = st.date_input("Expiry", value=d_date)
    
    if st.button("RUN ANALYSIS", type="primary"):
        st.rerun()

# Main Area
st.title(f"♟️ {symbol} STRADDLE DECODER")

if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])

if ACCESS_TOKEN:
    # Fetch Data
    data, error = fetch_market_data(ACCESS_TOKEN, symbol, expiry.strftime("%Y-%m-%d"))
    
    if data:
        # A. METRICS ROW
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot Price", f"{data['spot']}")
        c2.metric("ATM Strike", f"{int(data['atm_strike'])}")
        c3.metric("ATM Premium (Width)", f"₹{data['atm_straddle']:.2f}")
        c4.metric("Calculated SD", f"±{data['width_base']} pts")

        # B. UPDATE CHART HISTORY
        now_str = datetime.now().strftime("%H:%M:%S")
        new_row = pd.DataFrame([{
            'Time': now_str,
            'ATM': data['atm_straddle'],
            '1SD': data['1sd_val'],
            '1.5SD': data['1.5sd_val'],
            '2SD': data['2sd_val']
        }])
        st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)

        # C. PLOTLY CHART (The FinanceDeft Look)
        st.markdown("### 📈 Straddle & Strangle Premiums")
        
        fig = go.Figure()
        
        # Style: Thin neon lines, glowing effect
        # ATM Straddle (Cyan)
        fig.add_trace(go.Scatter(
            x=st.session_state.history['Time'], y=st.session_state.history['ATM'],
            mode='lines', name='ATM Straddle',
            line=dict(color='#22D3EE', width=3) 
        ))
        # 1 SD (Green)
        fig.add_trace(go.Scatter(
            x=st.session_state.history['Time'], y=st.session_state.history['1SD'],
            mode='lines', name=f'1 SD ({data["strikes"]["1sd"]})',
            line=dict(color='#4ADE80', width=2)
        ))
        # 1.5 SD (Yellow)
        fig.add_trace(go.Scatter(
            x=st.session_state.history['Time'], y=st.session_state.history['1.5SD'],
            mode='lines', name=f'1.5 SD ({data["strikes"]["1.5sd"]})',
            line=dict(color='#FACC15', width=2)
        ))
        # 2 SD (Pink/Red)
        fig.add_trace(go.Scatter(
            x=st.session_state.history['Time'], y=st.session_state.history['2SD'],
            mode='lines', name=f'2 SD ({data["strikes"]["2sd"]})',
            line=dict(color='#F472B6', width=2)
        ))

        fig.update_layout(
            paper_bgcolor='#0F172A', # Matches App Background
            plot_bgcolor='#1E293B',  # Slightly lighter for grid
            font=dict(family="Lato", color="#94A3B8"),
            xaxis=dict(showgrid=False, gridcolor='#334155'),
            yaxis=dict(showgrid=True, gridcolor='#334155', title="Combined Premium (₹)"),
            legend=dict(orientation="h", y=1.1, font=dict(color="white")),
            height=550,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

        # D. LIVE STRIKE TABLE
        with st.expander("🔍 View Live Strike Details"):
            st.dataframe(pd.DataFrame([
                {"Strategy": "ATM Straddle", "Strikes": f"{int(data['atm_strike'])} CE/PE", "Premium": data['atm_straddle']},
                {"Strategy": "1 SD Strangle", "Strikes": data['strikes']['1sd'], "Premium": data['1sd_val']},
                {"Strategy": "1.5 SD Strangle", "Strikes": data['strikes']['1.5sd'], "Premium": data['1.5sd_val']},
                {"Strategy": "2 SD Strangle", "Strikes": data['strikes']['2sd'], "Premium": data['2sd_val']},
            ]), use_container_width=True)

    else:
        st.error(f"⚠️ {error}")
else:
    st.info("Waiting for Access Token...")