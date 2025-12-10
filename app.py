import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. CONFIGURATION & BRANDING ---
st.set_page_config(
    page_title="Kyoto Capital | Quant Dashboard",
    page_icon="📈",
    layout="wide"
)

# Custom CSS for "Alta" Font & Theme Colors
st.markdown("""
    <style>
        /* Import a font that looks like Alta or use fallback */
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Lato:wght@300;400;700&display=swap');
        
        /* Main Background */
        .stApp {
            background-color: #1E293B; /* Brand Color: Slate */
            color: #FFFFFF;
        }
        
        /* Typography */
        h1, h2, h3, h4, .stMetricLabel, .stSelectbox label, .stDateInput label {
            font-family: 'Cinzel', serif !important; /* Alta substitute */
            color: #FFFFFF !important;
        }
        
        p, div, span, .stMetricValue {
            font-family: 'Lato', sans-serif; /* Clean readable font for data */
            color: #E2E8F0 !important;
        }

        /* Metrics Styling */
        div[data-testid="stMetricValue"] {
            font-size: 36px;
            color: #38BDF8 !important; /* Light Blue accent */
        }
        
        /* Inputs */
        .stSelectbox div[data-baseweb="select"] > div {
            background-color: #334155;
            color: white;
            border: 1px solid #475569;
        }
        
        /* Buttons */
        .stButton button {
            background-color: #FFFFFF;
            color: #1E293B;
            font-weight: bold;
            border-radius: 4px;
        }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
# Initialize session state for storing chart history
if 'chart_data' not in st.session_state:
    st.session_state.chart_data = pd.DataFrame(columns=['Time', 'ATM_Straddle', 'Strangle_1SD', 'Strangle_2SD'])

# --- 3. HELPER FUNCTIONS ---

def get_next_thursday():
    """Calculates the next Thursday's date for default expiry."""
    today = datetime.now()
    days_ahead = 3 - today.weekday()  # Thursday is 3
    if days_ahead <= 0: 
        days_ahead += 7
    next_thursday = today + timedelta(days=days_ahead)
    return next_thursday.strftime("%Y-%m-%d")

def fetch_spot_price(access_token, symbol):
    """Fetches the underlying spot price."""
    # Mapping for Underlying Keys
    symbol_map = {
        "NIFTY": "NSE_INDEX|Nifty 50",
        "BANKNIFTY": "NSE_INDEX|Nifty Bank"
    }
    instrument_key = symbol_map.get(symbol)
    
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}
    params = {'instrument_key': instrument_key}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if data.get('status') == 'success':
            # Handle the | vs : swap in response keys
            key_in_response = instrument_key.replace('|', ':')
            return data['data'][key_in_response]['last_price']
    except Exception as e:
        st.error(f"Error fetching Spot: {e}")
    return None

def get_option_chain_keys(access_token, symbol, expiry_date, spot_price, step_size):
    """
    Fetches option chain, finds ATM, 1SD, 2SD strikes, and returns their Instrument Keys.
    """
    # 1. Map Symbol to Key for Chain API
    underlying_key = "NSE_INDEX|Nifty 50" if symbol == "NIFTY" else "NSE_INDEX|Nifty Bank"
    
    url = "https://api.upstox.com/v2/option/chain"
    params = {'instrument_key': underlying_key, 'expiry_date': expiry_date}
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if data.get('status') != 'success':
            st.error("Failed to fetch Option Chain. Check Expiry Date.")
            return None

        chain_data = data['data']
        
        # 2. Calculate Target Strikes
        # ATM: Round spot to nearest Step Size
        atm_strike = round(spot_price / step_size) * step_size
        
        strikes = {
            'ATM': atm_strike,
            '1SD_UP': atm_strike + (1 * step_size), # 1 Step OTM Call
            '1SD_DN': atm_strike - (1 * step_size), # 1 Step OTM Put
            '2SD_UP': atm_strike + (2 * step_size),
            '2SD_DN': atm_strike - (2 * step_size),
        }
        
        # 3. Find Keys for these strikes
        # We need CE for UP strikes and PE for DOWN strikes, 
        # BUT for Strangles, we usually take OTM PE (Low Strike) and OTM CE (High Strike).
        
        found_keys = {}
        
        for item in chain_data:
            s_price = item['strike_price']
            
            # Capture ATM Straddle (ATM CE + ATM PE)
            if s_price == strikes['ATM']:
                found_keys['ATM_CE'] = item['call_options']['instrument_key']
                found_keys['ATM_PE'] = item['put_options']['instrument_key']
            
            # Capture 1SD Strangle (Low PE + High CE)
            if s_price == strikes['1SD_DN']:
                found_keys['1SD_PE'] = item['put_options']['instrument_key']
            if s_price == strikes['1SD_UP']:
                found_keys['1SD_CE'] = item['call_options']['instrument_key']

            # Capture 2SD Strangle (Lower PE + Higher CE)
            if s_price == strikes['2SD_DN']:
                found_keys['2SD_PE'] = item['put_options']['instrument_key']
            if s_price == strikes['2SD_UP']:
                found_keys['2SD_CE'] = item['call_options']['instrument_key']
                
        return found_keys, strikes

    except Exception as e:
        st.error(f"Chain Error: {e}")
        return None, None

def get_premiums(access_token, keys_dict):
    """
    Fetches LTP for all option keys found.
    """
    if not keys_dict: return None
    
    # Construct comma-separated string of all keys
    all_keys = list(keys_dict.values())
    keys_str = ",".join(all_keys)
    
    url = "https://api.upstox.com/v2/market-quote/ltp"
    params = {'instrument_key': keys_str}
    headers = {'Accept': 'application/json', 'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        if data.get('status') == 'success':
            prices = {}
            for k, v in keys_dict.items():
                # Handle | vs :
                resp_key = v.replace('|', ':')
                price = data['data'].get(resp_key, {}).get('last_price', 0)
                prices[k] = price
            return prices
    except Exception as e:
        st.error(f"Premium Fetch Error: {e}")
    return None

# --- 4. MAIN APP LAYOUT ---

# Sidebar Controls
with st.sidebar:
    st.header("KYOTO CONFIG")
    
    # API Token
    ACCESS_TOKEN = st.text_input("API Token", type="password")
    
    # Index Selection
    symbol = st.selectbox("Select Index", ["NIFTY", "BANKNIFTY"])
    
    # Expiry Date
    default_date = datetime.strptime(get_next_thursday(), "%Y-%m-%d")
    expiry = st.date_input("Expiry Date", value=default_date)
    
    # Step Size (Proxy for SD)
    # Allows user to define what "1 SD" means (e.g. 50 pts or 100 pts)
    default_step = 50 if symbol == "NIFTY" else 100
    step_size = st.number_input("Strike Step (SD Width)", value=default_step, step=50)

    # Refresh Button
    if st.button("Refresh Data", type="primary"):
        st.rerun()

# Main Logic
st.title(f"📊 {symbol} | STRADDLE & STRANGLE TRACKER")

if ACCESS_TOKEN:
    # 1. Get Spot
    spot_price = fetch_spot_price(ACCESS_TOKEN, symbol)
    
    if spot_price:
        # Display Spot & ATM
        col1, col2, col3 = st.columns(3)
        col1.metric("Spot Price", f"{spot_price}")
        
        # 2. Get Option Chain & Keys
        expiry_str = expiry.strftime("%Y-%m-%d")
        keys, strikes = get_option_chain_keys(ACCESS_TOKEN, symbol, expiry_str, spot_price, step_size)
        
        if keys and strikes:
            col2.metric("ATM Strike", f"{strikes['ATM']}")
            col3.metric("1SD Width", f"±{step_size}")
            
            # 3. Get Live Premiums
            premiums = get_premiums(ACCESS_TOKEN, keys)
            
            if premiums:
                # Calculate Strategy Values (Combined Premiums)
                val_atm = premiums.get('ATM_CE', 0) + premiums.get('ATM_PE', 0)
                val_1sd = premiums.get('1SD_CE', 0) + premiums.get('1SD_PE', 0)
                val_2sd = premiums.get('2SD_CE', 0) + premiums.get('2SD_PE', 0)
                
                # Update Session State for Charting
                current_time = datetime.now().strftime("%H:%M:%S")
                new_row = {
                    'Time': current_time, 
                    'ATM_Straddle': val_atm,
                    'Strangle_1SD': val_1sd,
                    'Strangle_2SD': val_2sd
                }
                st.session_state.chart_data = pd.concat([st.session_state.chart_data, pd.DataFrame([new_row])], ignore_index=True)
                
                # --- CHARTING ---
                st.markdown("### Combined Premium Chart")
                
                fig = go.Figure()
                
                # Trace 1: ATM Straddle
                fig.add_trace(go.Scatter(
                    x=st.session_state.chart_data['Time'], 
                    y=st.session_state.chart_data['ATM_Straddle'],
                    mode='lines+markers', name='ATM Straddle',
                    line=dict(color='#00F0FF', width=3) # Cyan
                ))
                
                # Trace 2: 1SD Strangle
                fig.add_trace(go.Scatter(
                    x=st.session_state.chart_data['Time'], 
                    y=st.session_state.chart_data['Strangle_1SD'],
                    mode='lines+markers', name=f'1SD Strangle (±{step_size})',
                    line=dict(color='#00FF94', width=2) # Neon Green
                ))

                # Trace 3: 2SD Strangle
                fig.add_trace(go.Scatter(
                    x=st.session_state.chart_data['Time'], 
                    y=st.session_state.chart_data['Strangle_2SD'],
                    mode='lines+markers', name=f'2SD Strangle (±{step_size*2})',
                    line=dict(color='#FF0055', width=2) # Neon Red
                ))

                fig.update_layout(
                    paper_bgcolor='#1E293B',
                    plot_bgcolor='#0F172A',
                    font=dict(color='white', family="Lato"),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor='#334155'),
                    legend=dict(orientation="h", y=1.1),
                    height=500,
                    margin=dict(l=20, r=20, t=50, b=20)
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Data Table below for granular view
                with st.expander("View Raw Data"):
                    st.dataframe(st.session_state.chart_data.tail(10))
            
            else:
                st.warning("Could not fetch premiums. Market might be closed or Token Invalid.")
        else:
            st.error("Could not find matching strikes in Option Chain.")
    else:
        st.error("Spot Price Fetch Failed. Check Token.")
else:
    st.info("👋 Enter your Upstox API Token in the sidebar to begin.")