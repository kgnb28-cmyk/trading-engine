import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. KYOTO CAPITAL: CONFIG & STYLING ---
st.set_page_config(
    page_title="Kyoto Capital | Multi-Straddle Engine",
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
        
        /* METRIC CARDS */
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
    New Logic: 
    1. Fetch Spot & ATM Straddle.
    2. Calculate SD values using multipliers (0.33, 0.2, 0.15).
    """
    # 1. DEFINE MAPPINGS
    if symbol == "NIFTY":
        spot_key = "NSE_INDEX|Nifty 50"
        step = 50
    elif symbol == "BANKNIFTY":
        spot_key = "NSE_INDEX|Nifty Bank"
        step = 100
    elif symbol == "SENSEX":
        spot_key = "BSE_INDEX|SENSEX"
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
        
        spot_val = spot_data['data'][spot_key.replace('|', ':')]['last_price']
        
    except Exception as e:
        return None, f"Spot API Error: {e}"

    # 3. Calculate ATM Strike
    atm_strike = round_to_strike(spot_val, step)

    # 4. Fetch Option Chain (Only to get ATM Straddle Premium)
    try:
        url_chain = "https://api.upstox.com/v2/option/chain"
        params_chain = {'instrument_key': spot_key, 'expiry_date': expiry_date}
        resp_chain = requests.get(url_chain, headers=headers, params=params_chain)
        chain_data = resp_chain.json()
        
        if chain_data.get('status') != 'success':
            return None, "Chain Failed (Check Expiry)"
            
        options_list = chain_data['data']
        
        # Find ATM Premiums
        atm_ce = 0
        atm_pe = 0
        found = False

        for item in options_list:
            if item['strike_price'] == atm_strike:
                atm_ce = item['call_options']['market_data']['ltp']
                atm_pe = item['put_options']['market_data']['ltp']
                found = True
                break
        
        if not found:
            return None, f"ATM {atm_strike} not found"

        # 5. NEW MATH LOGIC
        atm_premium = atm_ce + atm_pe
        
        # Calculated purely from ATM Premium multipliers
        val_1sd = atm_premium * 0.33
        val_15sd = atm_premium * 0.20
        val_2sd = atm_premium * 0.15

        return {
            "spot": spot_val,
            "atm_strike": atm_strike,
            "atm_straddle": atm_premium,
            "1sd_val": val_1sd,
            "1.5sd_val": val_15sd,
            "2sd_val": val_2sd,
        }, None

    except Exception as e:
        return None, f"Calc Error: {e}"

# --- 3. UI HELPER: THE CHART RENDERER ---

def render_chart(history_df, data_metrics):
    """
    Draws metrics and chart using the NEW math logic.
    """
    # Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Spot", f"{data_metrics['spot']}")
    m2.metric("ATM Straddle", f"₹{data_metrics['atm_straddle']:.0f}")
    m3.metric("1SD (0.33x)", f"₹{data_metrics['1sd_val']:.1f}")
    m4.metric("2SD (0.15x)", f"₹{data_metrics['2sd_val']:.1f}")

    # Plotly Chart
    fig = go.Figure()
    
    # ATM (Cyan)
    fig.add_trace(go.Scatter(
        x=history_df['Time'], y=history_df['ATM'],
        mode='lines', name='ATM Straddle', line=dict(color='#22D3EE', width=3)
    ))
    # 1SD (Green) - 0.33x
    fig.add_trace(go.Scatter(
        x=history_df['Time'], y=history_df['1SD'],
        mode='lines', name='1SD (0.33x)', line=dict(color='#4ADE80', width=2)
    ))
    # 1.5SD (Yellow) - 0.20x
    fig.add_trace(go.Scatter(
        x=history_df['Time'], y=history_df['1.5SD'],
        mode='lines', name='1.5SD (0.20x)', line=dict(color='#FACC15', width=2)
    ))
    # 2SD (Pink) - 0.15x
    fig.add_trace(go.Scatter(
        x=history_df['Time'], y=history_df['2SD'],
        mode='lines', name='2SD (0.15x)', line=dict(color='#F472B6', width=2)
    ))

    fig.update_layout(
        paper_bgcolor='#1E293B', plot_bgcolor='#0F172A',
        font=dict(family="Lato", color="#94A3B8"),
        xaxis=dict(showgrid=False), yaxis=dict(showgrid=True, gridcolor='#334155'),
        margin=dict(l=10, r=10, t=10, b=10), height=350,
        showlegend=True, legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig, use_container_width=True)

# --- 4. MAIN APP LAYOUT ---

with st.sidebar:
    st.header("KYOTO CAPITAL")
    ACCESS_TOKEN = st.text_input("API Token", type="password")
    
    st.markdown("---")
    view_mode = st.radio("Display Mode", ["Single Window", "Split Window (Multi)"])
    
    # --- INPUTS FOR WINDOW A ---
    st.markdown("#### 📺 Window A Settings")
    sym_a = st.selectbox("Index A", ["NIFTY", "BANKNIFTY", "SENSEX"], key="s_a")
    d_date = datetime.strptime(get_next_thursday(), "%Y-%m-%d")
    exp_a = st.date_input("Expiry A", value=d_date, key="e_a")

    # --- INPUTS FOR WINDOW B ---
    sym_b = None
    exp_b = None
    if view_mode == "Split Window (Multi)":
        st.markdown("#### 📺 Window B Settings")
        sym_b = st.selectbox("Index B", ["NIFTY", "BANKNIFTY", "SENSEX"], key="s_b")
        exp_b = st.date_input("Expiry B", value=d_date, key="e_b")
    
    st.markdown("---")
    st.subheader("🔴 Live Control")
    run_live = st.toggle("Start Feed", value=False)
    refresh_rate = st.slider("Speed (sec)", 1, 10, 2)

# --- 5. STATE MANAGEMENT ---

st.title("♟️ KYOTO: MULTI-Straddle ENGINE")

if 'hist_a' not in st.session_state: st.session_state.hist_a = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])
if 'hist_b' not in st.session_state: st.session_state.hist_b = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD'])

# Track Last Symbol to prevent SPIKES
if 'last_sym_a' not in st.session_state: st.session_state.last_sym_a = sym_a
if 'last_sym_b' not in st.session_state: st.session_state.last_sym_b = sym_b

# Reset history on symbol change
if st.session_state.last_sym_a != sym_a:
    st.session_state.hist_a = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD']) 
    st.session_state.last_sym_a = sym_a 

if sym_b and st.session_state.last_sym_b != sym_b:
    st.session_state.hist_b = pd.DataFrame(columns=['Time', 'ATM', '1SD', '1.5SD', '2SD']) 
    st.session_state.last_sym_b = sym_b 

# --- 6. EXECUTION LOOP ---

if view_mode == "Single Window":
    container_a = st.empty()
    container_b = None
else:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**WINDOW A: {sym_a}**")
        container_a = st.empty()
    with col2:
        st.markdown(f"**WINDOW B: {sym_b}**")
        container_b = st.empty()

def update_dashboard():
    if not ACCESS_TOKEN:
        return

    # Process Window A
    data_a, err_a = fetch_market_data(ACCESS_TOKEN, sym_a, exp_a.strftime("%Y-%m-%d"))
    if data_a:
        now_str = datetime.now().strftime("%H:%M:%S")
        new_row = pd.DataFrame([{
            'Time': now_str,
            'ATM': data_a['atm_straddle'],
            '1SD': data_a['1sd_val'],
            '1.5SD': data_a['1.5sd_val'],
            '2SD': data_a['2sd_val']
        }])
        st.session_state.hist_a = pd.concat([st.session_state.hist_a, new_row], ignore_index=True).tail(50)
        
        with container_a.container():
            render_chart(st.session_state.hist_a, data_a)
    elif err_a:
        container_a.error(err_a)

    # Process Window B
    if view_mode == "Split Window (Multi)" and container_b:
        data_b, err_b = fetch_market_data(ACCESS_TOKEN, sym_b, exp_b.strftime("%Y-%m-%d"))
        if data_b:
            now_str = datetime.now().strftime("%H:%M:%S")
            new_row = pd.DataFrame([{
                'Time': now_str,
                'ATM': data_b['atm_straddle'],
                '1SD': data_b['1sd_val'],
                '1.5SD': data_b['1.5sd_val'],
                '2SD': data_b['2sd_val']
            }])
            st.session_state.hist_b = pd.concat([st.session_state.hist_b, new_row], ignore_index=True).tail(50)
            
            with container_b.container():
                render_chart(st.session_state.hist_b, data_b)
        elif err_b:
            container_b.error(err_b)

# --- 7. START ---

if ACCESS_TOKEN:
    if run_live:
        while True:
            update_dashboard()
            time.sleep(refresh_rate)
    else:
        update_dashboard()
else:
    st.info("👋 Enter API Token to begin.")