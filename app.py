import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. KYOTO CAPITAL: VISUAL IDENTITY ---
st.set_page_config(
    page_title="Kyoto Capital | Live Straddle Engine",
    page_icon="♟️",
    layout="wide"
)

# Custom CSS: "Alta" Font styling + Modern Dark Theme
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;800&family=Lato:wght@300;400;700&display=swap');
        
        /* DARK MODE OVERRIDES */
        .stApp {
            background-color: #0F172A; /* Midnight Blue */
            color: #E2E8F0;
        }
        
        /* HEADERS */
        h1, h2, h3, h4 {
            font-family: 'Cinzel', serif !important;
            font-weight: 600;
            color: #F8FAFC !important;
        }
        
        /* METRICS CARDS */
        div[data-testid="stMetric"] {
            background-color: #1E293B;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #334155;
        }
        div[data-testid="stMetricLabel"] {
            font-family: 'Lato', sans-serif;
            color: #94A3B8 !important;
            font-size: 13px;
        }
        div[data-testid="stMetricValue"] {
            font-family: 'Cinzel', serif;
            color: #38BDF8 !important;
            font-size: 26px;
        }
        
        /* LIVE INDICATOR */
        .live-badge {
            color: #ef4444;
            font-weight: bold;
            font-family: 'Lato', sans-serif;
            border: 1px solid #ef4444;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 12px;
            margin-bottom: 10px;
            display: inline-block;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE LOGIC (NO GUESSING) ---

def get_next_thursday():
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead <= 0: days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def round_to_strike(price, step):
    return round(price / step) * step

def fetch_market_data(access_token, symbol, expiry_date):
    """
    Fetches Spot -> Calculates ATM -> Finds SD Width -> Returns Premiums
    """
    if symbol == "NIFTY":
        spot_key = "NSE_INDEX|Nifty 50"
        step = 50
    else:
        spot_key = "NSE_INDEX|Nifty Bank"
        step = 100

    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}

    # 1. Get Spot Price
    try:
        url_spot = "https://api.upstox.com/v2/market-quote/ltp"
        resp_spot = requests.get(url_spot, headers=headers, params={'instrument_key': spot_key})
        spot_data = resp_spot.json()
        
        if spot_data.get('status') != 'success':
            return None, "Spot Fetch Failed"
            
        spot_val = spot_data['data'][spot_key.replace('|', ':')]['last_price']
        
    except Exception as e:
        return None, f"API Error: {e}"

    # 2. Calculate ATM Strike
    atm_strike = round_to_strike(spot_val, step)

    # 3. Fetch Option Chain
    try:
        url_chain = "https://api.upstox.com/v2/option/chain"
        params_chain = {'instrument_key': spot_key, 'expiry_date': expiry_date}
        resp_chain = requests.get(url_chain, headers=headers, params=params_chain)
        chain_data = resp_chain.json()
        
        if chain_data.get('status') != 'success':
            return None, "Option Chain Failed (Check Expiry)"
            
        options_list = chain_data['data']
        
        # 4. Map Strikes
        strike_map = {} 
        for item in options_list:
            strike = item['strike_price']
            strike_map[strike] = {
                'CE_LTP': item['call_options']['market_data']['ltp'],
                'PE_LTP': item['put_options']['market_data']['ltp']
            }

        if atm_strike not in strike_map:
            return None, "ATM Strike not found in chain"

        # 5. SD LOGIC: Width = ATM Straddle Premium
        atm_premium = strike_map[atm_strike]['CE_LTP'] + strike_map[atm_strike]['PE_LTP']
        
        width_1sd = round_to_strike(atm_premium, step)
        width_15sd = round_to_strike(atm_premium * 1.5, step)
        width_2sd = round_to_strike(atm_premium * 2.0, step)

        # 6. Helper to get combined premium
        def get_strangle_prem(upper, lower):
            if upper in strike_map and lower in strike_map:
                return strike_map[upper]['CE_LTP'] + strike_map[lower]['PE_LTP']
            return 0

        # Calculate Strangle Values
        val_1sd = get_strangle_prem(atm_strike + width_1sd, atm_strike - width_1sd)
        val_15sd = get_strangle_prem(atm_strike + width_15sd, atm_strike - width_15sd)
        val_2sd = get_strangle_prem(atm_strike + width_2sd, atm_strike - width_2sd)

        return {
            "spot": spot_val,
            "atm_strike": atm_strike,
            "atm_straddle": atm_premium,
            "width_base": width_1sd,
            "1sd_val": val_1sd,
            "1.5sd_val": val_15sd,
            "2sd_val": val_2sd,
            "strikes": {
                "1sd": f"{int(atm_strike - width_1sd)}PE & {int(atm_strike + width_1sd)}CE",
                "1.5sd": f"{int(atm_strike - width_15sd)}PE & {int(atm_strike + width_15sd)}CE",
                "2sd": f"{int(atm_strike - width_2sd)}PE & {int(atm_strike + width_2sd)}CE"
            }
        }, None

    except Exception as e:
        return None, f"Calculation Error: {e}"

# --- 3. UI LAYOUT ---

# Sidebar
with st.sidebar:
    st.header("KYOTO CAPITAL")
    ACCESS_TOKEN = st.text_input("API Token", type="password")
    symbol = st.selectbox("Instrument", ["NIFTY", "BANKNIFTY"])
    
    d_date = datetime.strptime(get_next_thursday(), "%Y-%m-%d")
    expiry = st.date_input("Expiry", value=d_date)
    
    st.markdown("---")
    st.subheader("🔴 LIVE CONTROL")
    run_live = st.toggle("START LIVE FEED", value=False)
    refresh_rate = st.slider("Refresh Speed (Sec)", 1, 10, 1)

# Main Title
st.title(f"♟️ {symbol} STRADDLE DECODER")

# Initialize Session State
if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])

# --- 4. THE RENDER LOOP ---

def render_dashboard():
    # 1. Fetch Data
    data, error = fetch_market_data(ACCESS_TOKEN, symbol, expiry.strftime("%Y-%m-%d"))
    
    if data:
        # Update History
        now_str = datetime.now().strftime("%H:%M:%S")
        new_row = pd.DataFrame([{
            'Time': now_str,
            'ATM': data['atm_straddle'],
            '1SD': data['1sd_val'],
            '1.5SD': data['1.5sd_val'],
            '2SD': data['2sd_val']
        }])
        st.session_state.history = pd.concat([st.session_state.history, new_row], ignore_index=True)
        # Keep only last 50 points to keep chart fast
        if len(st.session_state.history) > 50:
            st.session_state.history = st.session_state.history.tail(50)

        # 2. Render Metrics
        if run_live:
            st.markdown(f'<span class="live-badge">● LIVE FEED ACTIVE ({refresh_rate}s)</span>', unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spot Price", f"{data['spot']}")
        c2.metric("ATM Strike", f"{int(data['atm_strike'])}")
        c3.metric("ATM Premium", f"₹{data['atm_straddle']:.2f}")
        c4.metric("SD Width (Auto)", f"±{data['width_base']} pts")

        # 3. Render Chart
        st.markdown("### 📈 Live Premium Trends")
        fig = go.Figure()
        
        # ATM (Cyan)
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
        # 2 SD (Pink)
        fig.add_trace(go.Scatter(
            x=st.session_state.history['Time'], y=st.session_state.history['2SD'],
            mode='lines', name=f'2 SD ({data["strikes"]["2sd"]})',
            line=dict(color='#F472B6', width=2)
        ))

        fig.update_layout(
            paper_bgcolor='#0F172A',
            plot_bgcolor='#1E293B',
            font=dict(family="Lato", color="#94A3B8"),
            xaxis=dict(showgrid=False, gridcolor='#334155'),
            yaxis=dict(showgrid=True, gridcolor='#334155'),
            legend=dict(orientation="h", y=1.1, font=dict(color="white")),
            height=500,
            margin=dict(l=10, r=10, t=10, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.error(error)

# --- 5. EXECUTION ---
if ACCESS_TOKEN:
    # Create a placeholder for the entire dashboard
    dashboard_placeholder = st.empty()

    if run_live:
        # Loop forever (until user toggles off)
        while True:
            with dashboard_placeholder.container():
                render_dashboard()
            time.sleep(refresh_rate)
    else:
        # Run once (Static Mode)
        with dashboard_placeholder.container():
            render_dashboard()
else:
    st.info("👋 Enter API Token to start.")