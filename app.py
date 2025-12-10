import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import backtest  # Importing your backtest logic module

# --- Page Configuration ---
st.set_page_config(
    page_title="Kyoto Capital | Backtest Engine",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Kyoto Capital: Algo Backtesting Dashboard")
st.markdown("---")

# --- Sidebar: Configuration ---
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload Tick/OHLC Data (CSV)", type=['csv'])
    
    st.subheader("Strategy Parameters")
    # Example parameters - adjust based on your specific strategy inputs
    param1 = st.number_input("Parameter 1 (e.g., Window)", min_value=1, value=14)
    param2 = st.number_input("Parameter 2 (e.g., Threshold)", min_value=0.0, value=1.5)
    
    run_btn = st.button("Run Backtest", type="primary")

# --- Main Logic ---
if run_btn and uploaded_file is not None:
    try:
        # 1. Load Data
        df = pd.read_csv(uploaded_file)
        st.success(f"Loaded data with {len(df)} rows.")

        # 2. Run Backtest
        # We pass the dataframe and params to your backtest module
        with st.spinner("Running Strategy..."):
            # Ensure your backtest.run_backtest function accepts these arguments
            results, signals, trade_log = backtest.run_backtest(df, param1, param2)

        # 3. Display Metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Return", f"{results.get('total_return', 0):.2f}%")
        col2.metric("Win Rate", f"{results.get('win_rate', 0):.2f}%")
        col3.metric("Max Drawdown", f"{results.get('max_drawdown', 0):.2f}%")
        col4.metric("Total Trades", results.get('total_trades', 0))

        # 4. Visualization (The Fix for KeyError is here)
        st.subheader("Trade Signals Analysis")
        
        # Prepare data for plotting
        # We map the signals to the dataframe index for plotting
        buy_signals = []
        sell_signals = []
        
        # --- CRITICAL FIX: Robust Key Handling ---
        # The loop checks if the key exists as an integer OR a string
        for i in df.index:
            # Try accessing with integer index first, then string index
            signal_data = signals.get(i) or signals.get(str(i))
            
            if signal_data == 'BUY':
                buy_signals.append(df.iloc[i]['Close']) # Assuming 'Close' column exists
                sell_signals.append(None)
            elif signal_data == 'SELL':
                buy_signals.append(None)
                sell_signals.append(df.iloc[i]['Close'])
            else:
                buy_signals.append(None)
                sell_signals.append(None)

        # Add columns to DF for easier plotting
        df['Buy_Signal'] = buy_signals
        df['Sell_Signal'] = sell_signals

        # Plotting with Plotly
        fig = go.Figure()

        # Candlestick (if OHLC data exists) or Line Chart
        if set(['Open', 'High', 'Low', 'Close']).issubset(df.columns):
            fig.add_trace(go.Candlestick(x=df.index,
                            open=df['Open'], high=df['High'],
                            low=df['Low'], close=df['Close'],
                            name='Price'))
        else:
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Price'))

        # Add Buy Markers
        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df['Buy_Signal'],
            mode='markers',
            marker=dict(symbol='triangle-up', color='green', size=10),
            name='Buy Signal'
        ))

        # Add Sell Markers
        fig.add_trace(go.Scatter(
            x=df.index, 
            y=df['Sell_Signal'],
            mode='markers',
            marker=dict(symbol='triangle-down', color='red', size=10),
            name='Sell Signal'
        ))

        fig.update_layout(
            title='Price Action with Trade Signals',
            xaxis_title='Index/Time',
            yaxis_title='Price',
            template='plotly_dark',
            height=600
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # 5. Trade Log Table
        st.subheader("Trade Logs")
        if trade_log:
            log_df = pd.DataFrame(trade_log)
            st.dataframe(log_df, use_container_width=True)
        else:
            st.info("No trades generated.")

    except Exception as e:
        st.error(f"An error occurred during execution: {e}")
        # Print detailed traceback to terminal for debugging
        import traceback
        traceback.print_exc()

elif run_btn and uploaded_file is None:
    st.warning("Please upload a CSV file first.")