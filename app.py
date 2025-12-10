import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- CONFIGURATION ---
st.set_page_config(page_title="Kyoto Capital | Live Dashboard", layout="wide")

# 🔴 PASTE YOUR UPSTOX ACCESS TOKEN HERE
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiIyNUNHNDIiLCJqdGkiOiI2OTM4ZmZkNmYwYjE5MTAyZjYyZDI2M2EiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6dHJ1ZSwiaWF0IjoxNzY1MzQzMTkwLCJpc3MiOiJ1ZGFwaS1nYXRld2F5LXNlcnZpY2UiLCJleHAiOjE3NjU0MDQwMDB9.tK0D-HKXccX_0aboTIzggYTOTxrNtjlIjyX0BVmLB4Y" 

# ✅ THE VERIFIED MAPPING (Golden Keys)
INSTRUMENT_MAPPING = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank"
}

# --- FUNCTIONS ---

def get_live_price(instrument_key):
    """
    Fetches live price from Upstox V2.
    Handles the tricky logic where Request uses '|' but Response uses ':'
    """
    url = "https://api.upstox.com/v2/market-quote/ltp"
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    params = {'instrument_key': instrument_key}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        
        # DEBUG: Print raw response to terminal to see what's happening
        print(f"DEBUG Response for {instrument_key}: {data}")

        if response.status_code == 200 and data.get("status") == "success":
            # ⚠️ CRITICAL FIX: Upstox response keys use ':' instead of '|'
            # We convert 'NSE_INDEX|Nifty 50' -> 'NSE_INDEX:Nifty 50' to find the data
            response_key = instrument_key.replace('|', ':')
            
            # Fetch the specific instrument data
            instrument_data = data['data'].get(response_key)
            
            if instrument_data:
                return instrument_data['last_price']
            else:
                st.error(f"Key mismatch! API returned data but could not find key: {response_key}")
                return None
        else:
            st.error(f"API Error: {data.get('message', 'Unknown Error')}")
            return None
            
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

# --- UI LAYOUT ---

st.title("📈 Kyoto Capital: Live Algo Dashboard")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("Live Configuration")
    selected_symbol = st.selectbox("Select Instrument", list(INSTRUMENT_MAPPING.keys()))
    
    # Get the correct key for the API
    api_instrument_key = INSTRUMENT_MAPPING[selected_symbol]
    
    st.info(f"API Key: {api_instrument_key}")
    
    if st.button("Refresh Data"):
        st.rerun()

# Main Area
st.subheader(f"Live Spot Data: {selected_symbol}")

# 1. Fetch Data
current_price = get_live_price(api_instrument_key)

# 2. Display Data or Error
if current_price:
    # Success Display
    col1, col2 = st.columns(2)
    col1.metric(label=f"{selected_symbol} Spot Price", value=f"₹{current_price}")
    col2.success("Connected to Upstox V2")
    
    # Debug Logs (Expandable)
    with st.expander("🔍 Debug Logs (Connection Details)"):
        st.write(f"1. User Selected: {selected_symbol}")
        st.write(f"2. Sending Key to API: `{api_instrument_key}`")
        st.write(f"3. Searching Response for Key: `{api_instrument_key.replace('|', ':')}`")
        st.write(f"4. Price Found: {current_price}")

else:
    # Error Display
    st.warning("⚠️ Spot Data Missing. Check Token or API Limits.")
    with st.expander("🔍 Debug Logs"):
        st.write(f"Requesting Key: {api_instrument_key}")
        st.write("Result: None (Error in fetching)")