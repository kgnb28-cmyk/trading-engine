import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. KYOTO CAPITAL: CONFIG & STYLING ---
st.set_page_config(
    page_title="Kyoto Capital | Multi-Strategy Engine",
    page_icon="♟️",
    layout="wide"
)

# Custom CSS for "Alta" Font & Split Screen Layout
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;800&family=Lato:wght@300;400;700&display=swap');
        
        .stApp { background-color: #0F172A; color: #E2E8F0; }
        
        /* HEADERS */
        h1, h2, h3, h4 { font-family: 'Cinzel', serif !important; color: #F8FAFC !important; }
        
        /* CARDS */
        div[data-testid="stMetric"] {
            background-color: #1E293B;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 10px;
        }
        div[data-testid="stMetricValue"] {
            color: #38BDF8 !important; /* Neon Blue */
            font-size: 24px;
            font-family: 'Cinzel', serif;
        }
        div[data-testid="stMetricLabel"] { color: #94A3B8 !important; font-family: 'Lato', sans-serif; }

        /* LIVE BADGE */
        .live-badge {
            color: #22c55e;
            border: 1px solid #22c55e;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-family: 'Lato', sans-serif;
            letter-spacing: 1px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. CORE LOGIC ---

def get_next_thursday():
    today = datetime.now()
    days_ahead = 3 - today.weekday()
    if days_ahead <= 0: days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

def round_to_strike(price, step):
    return round(price / step) * step

def fetch_market_data(access_token, symbol, expiry_date):
    """
    Fetches Spot -> Calculates ATM -> Returns Straddle/Strangle Premiums
    """
    # 1. DEFINE MAPPINGS (Now including SENSEX)
    if symbol == "NIFTY":
        spot_key = "NSE_INDEX|Nifty 50"
        step = 50
    elif symbol == "BANKNIFTY":
        spot_key = "NSE_INDEX|Nifty Bank"
        step = 100
    elif symbol == "SENSEX":
        spot_key = "BSE_INDEX|SENSEX" #
        step = 100 
    else:
        return None, "Invalid Symbol"

    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}

    # 2. Get Spot Price
    try:
        url_spot = "https://api.upstox.com/v2/market-quote/ltp"
        resp_spot = requests.get(url_spot, headers=headers, params={'instrument_key': spot_key})
        spot_data = resp_spot.json()
        
        if spot_data.get('status') != 'success':
            return None, "Spot Fetch Failed"
        
        # Handle | vs : swap
        spot_val = spot_data['data'][spot_key.replace('|', ':')]['last_price']
        
    except Exception as e:
        return None, f"Spot API Error: {e}"

    # 3. Calculate ATM Strike
    atm_strike = round_to_strike(spot_val, step)

    # 4. Fetch Option Chain
    try:
        url_chain = "https://api.upstox.com/v2/option/chain"
        params_chain = {'instrument_key': spot_key, 'expiry_date': expiry_date}
        resp_chain = requests.get(url_chain, headers=headers, params=params_chain)
        chain_data = resp_chain.json()
        
        if chain_data.get('status') != 'success':
            return None, "Chain Failed (Check Expiry)"
            
        options_list = chain_data['data']
        
        # Map Strikes for fast lookup
        strike_map = {} 
        for item in options_list:
            strike = item['strike_price']
            strike_map[strike] = {
                'CE_LTP': item['call_options']['market_data']['ltp'],
                'PE_LTP': item['put_options']['market_data']['ltp']
            }

        if atm_strike not in strike_map:
            return None, f"ATM {atm_strike} not in chain"

        # 5. SD LOGIC (Width = ATM Premium)
        atm_premium = strike_map[atm_strike]['CE_LTP'] + strike_map[atm_strike]['PE_LTP']
        
        width_1sd = round_to_strike(atm_premium, step)
        width_15sd = round_to_strike(atm_premium * 1.5, step)
        width_2sd = round_to_strike(atm_premium * 2.0, step)

        # Helper for Strangle Sum
        def get_strangle(upper, lower):
            if upper in strike_map and lower in strike_map:
                return strike_map[upper]['CE_LTP'] + strike_map[lower]['PE_LTP']
            return 0

        val_1sd = get_strangle(atm_strike + width_1sd, atm_strike - width_1sd)
        val_15sd = get_strangle(atm_strike + width_15sd, atm_strike - width_15sd)
        val_2sd = get_strangle(atm_strike + width_2sd, atm_strike - width_2sd)

        return {
            "spot": spot_val,
            "atm_strike": atm_strike,
            "atm_straddle": atm_premium,
            "width_base": width_1sd,
            "1sd_val": val_1sd,
            "1.5sd_val": val_15sd,
            "2sd_val": val_2sd,
            "desc_1sd": f"±{width_1sd}",
        }, None

    except Exception as e:
        return None, f"Calc Error: {e}"

# --- 3. UI COMPONENTS ---

def render_pane(pane_id, access_token, history_key):
    """
    Renders a single strategy pane (Selector -> Metrics -> Chart)
    """
    # 1. Selectors (Unique keys per pane)
    c1, c2 = st.columns([1, 1])
    with c1:
        symbol = st.selectbox(f"Index", ["NIFTY", "BANKNIFTY", "SENSEX"], key=f"sym_{pane_id}")
    with c2:
        # Default expiry logic
        d_date = datetime.strptime(get_next_thursday(), "%Y-%m-%d")
        expiry = st.date_input(f"Expiry", value=d_date, key=f"exp_{pane_id}")

    # 2. Fetch Data
    data, error = fetch_market_data(access_token, symbol, expiry.strftime("%Y-%m-%d"))
    
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
        
        # Append to specific history key
        st.session_state[history_key] = pd.concat([st.session_state[history_key], new_row], ignore_index=True).tail(50)

        # 3. Metrics
        m1, m2, m3 = st.columns(3)
        m1.metric("Spot", f"{data['spot']}")
        m2.metric("ATM Straddle", f"₹{data['atm_straddle']:.0f}")
        m3.metric("1SD Width", f"{data['desc_1sd']}")

        # 4. Chart
        fig = go.Figure()
        
        # ATM (Cyan)
        fig.add_trace(go.Scatter(
            x=st.session_state[history_key]['Time'], y=st.session_state[history_key]['ATM'],
            mode='lines', name='ATM', line=dict(color='#22D3EE', width=3)
        ))
        # 1SD (Green)
        fig.add_trace(go.Scatter(
            x=st.session_state[history_key]['Time'], y=st.session_state[history_key]['1SD'],
            mode='lines', name='1SD', line=dict(color='#4ADE80', width=2)
        ))
        # 2SD (Pink)
        fig.add_trace(go.Scatter(
            x=st.session_state[history_key]['Time'], y=st.session_state[history_key]['2SD'],
            mode='lines', name='2SD', line=dict(color='#F472B6', width=2)
        ))

        fig.update_layout(
            paper_bgcolor='#1E293B', plot_bgcolor='#0F172A',
            font=dict(family="Lato", color="#94A3B8"),
            xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#334155'),
            margin=dict(l=10, r=10, t=10, b=10), height=300,
            showlegend=True, legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error(f"{error}")

# --- 4. MAIN LAYOUT & EXECUTION ---

# Sidebar
with st.sidebar:
    st.header("KYOTO CONFIG")
    ACCESS_TOKEN = st.text_input("API Token", type="password")
    
    st.markdown("---")
    view_mode = st.radio("Display Mode", ["Single Window", "Split Window (Multi)"])
    
    st.markdown("---")
    st.subheader("🔴 Live Control")
    run_live = st.toggle("Start Feed", value=False)
    refresh_rate = st.slider("Speed (sec)", 1, 10, 2)

# Title
st.title("♟️ KYOTO: MULTI-STRATEGY ENGINE")

# Initialize Session States for History
if 'hist_1' not in st.session_state: st.session_state.hist_1 = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])
if 'hist_2' not in st.session_state: st.session_state.hist_2 = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])

# Render Function
def run_dashboard():
    if ACCESS_TOKEN:
        if view_mode == "Single Window":
            render_pane("main", ACCESS_TOKEN, "hist_1")
        else:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 📺 WINDOW A")
                render_pane("win_a", ACCESS_TOKEN, "hist_1")
            with col_b:
                st.markdown("#### 📺 WINDOW B")
                render_pane("win_b", ACCESS_TOKEN, "hist_2")
    else:
        st.info("Enter API Token to begin.")

# Execution Loop
placeholder = st.empty()

if run_live:
    while True:
        with placeholder.container():
            run_dashboard()
        time.sleep(refresh_rate)
else:
    with placeholder.container():
        run_dashboard()