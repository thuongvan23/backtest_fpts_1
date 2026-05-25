import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
# import mplfinance as mpf
from datetime import date
import io

st.set_page_config(page_title="Backtest Strategy System", layout="wide")

# --- KHỞI TẠO CẤU HÌNH & HẰNG SỐ CHUẨN TỪ COLAB ---
# INITIAL_CAPITAL = 500_000_000
# MAX_POSITION_SIZE = 100_000_000

# Giao diện cho phép tinh chỉnh Parameter (giữ default y hệt Colab)
st.sidebar.header("⚙️ Cấu hình Backtest")

# --- CẤU HÌNH VỐN ---
INITIAL_CAPITAL = st.sidebar.number_input(
    "Vốn ban đầu (Initial Capital)",
    min_value=100_000_000,
    value=500_000_000,
    step=50_000_000
)
st.sidebar.caption(f"≈ {INITIAL_CAPITAL:,.0f} đ")

MAX_POSITION_SIZE = st.sidebar.number_input(
    "Kích thước vị thế tối đa (Max Position Size)",
    min_value=10_000_000,
    value=50_000_000,
    step=10_000_000
)
st.sidebar.caption(f"≈ {MAX_POSITION_SIZE:,.0f} đ")

start_date = st.sidebar.date_input(
    "Ngày bắt đầu backtest",
    value=date(2000, 1, 1),
    min_value=date(1990, 1, 1),
    max_value=date.today()
)

end_date = st.sidebar.date_input(
    "Ngày kết thúc backtest",
    value=date.today(),
    min_value=date(1990, 1, 1),
    max_value=date.today()
)

start_date = pd.to_datetime(start_date)
end_date = pd.to_datetime(end_date)

if start_date >= end_date:
    st.error("Ngày bắt đầu phải nhỏ hơn ngày kết thúc")
    st.stop()

nen_tich_luy = st.sidebar.slider("Nền tích lũy max (%)", 0.01, 0.10, 0.04, step=0.01)
min_days = st.sidebar.number_input("Số ngày tích lũy tối thiểu", value=4)
max_days = st.sidebar.number_input("Số ngày tích lũy tối đa", value=9)
so_ngay_tich_luy = range(int(min_days), int(max_days) + 1)

breakout_days_check = st.sidebar.number_input("Breakout days check", value=3)
max_chase = st.sidebar.slider("Max chase limit (Chỉ vào khi không bị break quá cao)", 1.0, 1.1, 1.04, step=0.01)
target = st.sidebar.slider("Target (TP)", 1.0, 2.0, 1.4, step=0.05)
stoploss = st.sidebar.slider("Stoploss (SL)", 0.8, 1.0, 0.95, step=0.01)
min_hold_days = st.sidebar.number_input("Min hold days (Thị trường là T+2, số ngày hold tối thiếu)", value=14)
max_hold_days = st.sidebar.number_input("Max hold days (quá số ngày này sẽ tự động chốt)", value=25)
if min_hold_days > max_hold_days:
    st.error("Min hold days phải nhỏ hơn hoặc bằng Max hold days")
    st.stop()
avoid_duplicate = st.sidebar.number_input("Avoid duplicate days (sau khi vào 1 lệnh thì cách ra để tránh lặp lại) ", value=10)

BACKTEST_CONFIG = {
    "nen_tich_luy": nen_tich_luy,
    "so_ngay_tich_luy": so_ngay_tich_luy,
    "breakout_days_check": int(breakout_days_check),
    "max_chase": max_chase,
    "target": target,
    "stoploss": stoploss,
    "min_hold_days": int(min_hold_days),
    "avoid_duplicate": int(avoid_duplicate),
    "max_hold_days": int(max_hold_days)
}

# ==================== LOGIC HÀM BACKTEST ====================
def run_backtest(df, stock_name, nen_tich_luy, so_ngay_tich_luy, breakout_days_check, 
                 max_chase, target, stoploss, min_hold_days, max_hold_days, avoid_duplicate):
    trades = []
    last_breakout_idx = -1

    for i in range(80, len(df)):
        if i <= last_breakout_idx:
            continue
        if df['EMA21'].iloc[i] <= df['EMA65'].iloc[i]:
            continue

        trade_found = False
        for base_days in so_ngay_tich_luy:
            if i + base_days >= len(df):
                continue

            base_df = df.iloc[i:i+base_days]
            highest = base_df['High'].max()
            lowest = base_df['Low'].min()
            base_range = (highest - lowest) / lowest

            if base_range > nen_tich_luy:
                continue

            breakout_start = i + base_days
            for breakout_idx in range(breakout_start, breakout_start + breakout_days_check):
                if breakout_idx >= len(df):
                    continue

                candle = df.iloc[breakout_idx]
                breakout_price = candle['Close']

                if breakout_price <= highest:
                    continue
                if breakout_price > highest * max_chase:
                    continue

                tp = breakout_price * target
                sl = breakout_price * stoploss

                result = "HOLD"
                exit_price = None
                exit_date = None

                # Bắt đầu xét thoát sau min_hold_days
                start_exit_idx = breakout_idx + min_hold_days
                
                # Giới hạn tối đa thời gian nắm giữ
                end_exit_idx = min(breakout_idx + max_hold_days, len(df) - 1)
                
                future = df.iloc[start_exit_idx:end_exit_idx + 1]
                
                for j in range(len(future)):
                    row = future.iloc[j]
                
                    # Stoploss ưu tiên trước
                    if row['Low'] <= sl:
                        result = "STOPLOSS"
                        exit_price = sl
                        exit_date = future.index[j]
                        break
                
                    # Take profit
                    if row['High'] >= tp:
                        result = "TAKE_PROFIT"
                        exit_price = tp
                        exit_date = future.index[j]
                        break
                
                # Nếu chưa TP/SL tới max_hold_days -> auto chốt
                if exit_price is None:
                
                    forced_exit_row = df.iloc[end_exit_idx]
                
                    exit_price = forced_exit_row['Close']
                    exit_date = forced_exit_row.name
                
                    result = "MAX_HOLD_EXIT"

                trades.append({
                    'Buy Date': df.index[breakout_idx],
                    'Buy Price': breakout_price,
                    'Result': result,
                    'Exit Price': exit_price,
                    'Profit': (exit_price - breakout_price)/breakout_price,
                    'Exit Date': exit_date,
                    'Stock': stock_name,
                    'Hold time': exit_date - df.index[breakout_idx]
                })

                last_breakout_idx = breakout_idx + avoid_duplicate
                trade_found = True
                break

            if trade_found:
                break

    return pd.DataFrame(trades)

# ==================== LOGIC ĐỌC FILE & LÀM SẠCH ====================
# def read_stock_file(file_wrapper):
def read_stock_file(file_wrapper, start_date, end_date):
    df = pd.read_csv(file_wrapper)
    df = df.rename(columns={
        "Ngày": "Date", "Lần cuối": "Close", "Mở": "Open",
        "Cao": "High", "Thấp": "Low", "KL": "Volume", "% Thay đổi": "Change"
    })
    
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y')

    def clean_price(x):
        return float(str(x).replace(',', ''))

    def clean_volume(x):
        x = str(x).strip()
        if 'M' in x: return float(x.replace('M', '')) * 1_000_000
        if 'K' in x: return float(x.replace('K', '')) * 1_000
        return float(x)

    for col in ['Open', 'High', 'Low', 'Close']:
        df[col] = df[col].apply(clean_price)
    df['Volume'] = df['Volume'].apply(clean_volume)

    df = df.sort_values('Date', kind='mergesort') # Thêm kind='mergesort' vào đây
    df.set_index('Date', inplace=True)
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA65'] = df['Close'].ewm(span=65, adjust=False).mean()

    # effective_start = max(start_date, df.index.min())

    # df = df[
    #     (df.index >= effective_start) &
    #     (df.index <= end_date)
    # ]
    
    return df

# ==================== LOGIC TÍNH TOÁN THỐNG KÊ CHI TIẾT ====================
def calculate_statistics(trades_df):
    if len(trades_df) == 0: return None
    # closed_trades = trades_df[trades_df['Result'].isin(['TAKE_PROFIT', 'STOPLOSS'])].copy()
    closed_trades = trades_df.copy()
    if len(closed_trades) == 0: return None

    closed_trades['Return %'] = ((closed_trades['Exit Price'] - closed_trades['Buy Price']) / closed_trades['Buy Price']) * 100
    # wins = closed_trades[closed_trades['Result'] == 'TAKE_PROFIT']
    # losses = closed_trades[closed_trades['Result'] == 'STOPLOSS']
    wins = closed_trades[closed_trades['Return %'] > 0]
    losses = closed_trades[closed_trades['Return %'] <= 0]

    total_trades = len(closed_trades)
    win_count = len(wins)
    loss_count = len(losses)
    winrate = win_count / total_trades
    avg_win = wins['Return %'].mean() if win_count > 0 else 0
    avg_loss = abs(losses['Return %'].mean()) if loss_count > 0 else 0
    expectancy = (winrate * avg_win) - ((1 - winrate) * avg_loss)
    gross_profit = wins['Return %'].sum()
    gross_loss = abs(losses['Return %'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss != 0 else np.inf
    rr_ratio = avg_win / avg_loss if avg_loss != 0 else np.inf

    return {
        'Total Trades': total_trades, 'Winrate %': round(winrate * 100, 2),
        'Average Win %': round(avg_win, 2), 'Average Loss %': round(avg_loss, 2),
        'RR Ratio': round(rr_ratio, 2), 'Profit Factor': round(profit_factor, 2),
        'Expectancy %': round(expectancy, 2)
    }

# ==================== GIAO DIỆN CHÍNH STREAMLIT ====================
st.title("📈 Hệ thống Backtest Chiến lược Giao dịch")

uploaded_files = st.file_uploader("Tải lên các file dữ liệu cổ phiếu (CSV)", accept_multiple_files=True, type=['csv'])

if uploaded_files:
    summary_results = []
    all_trades = []
    
    st.info(f"Đang xử lý {len(uploaded_files)} tệp tin...")

    for file in uploaded_files:
        try:
            stock_name = file.name.replace(".csv", "")
            # Đọc trực tiếp từ BytesIO buffer của streamlit uploader
            # df = read_stock_file(file)
            df = read_stock_file(file, start_date, end_date)
            trades_df = run_backtest(df, stock_name, **BACKTEST_CONFIG)

            # Chỉ giữ lệnh nằm trong khoảng thời gian thống kê
            trades_df = trades_df[
                (trades_df['Buy Date'] >= start_date) &
                (trades_df['Buy Date'] <= end_date)
            ]
            
            if len(trades_df) > 0:
                all_trades.append(trades_df)

            stats = calculate_statistics(trades_df)
            if stats is not None:
                stats['Stock'] = stock_name
                summary_results.append(stats)
        except Exception as e:
            st.error(f"Lỗi khi xử lý file {file.name}: {e}")

    if len(summary_results) > 0:
        summary_df = pd.DataFrame(summary_results).sort_values(by='Expectancy %', ascending=False)
        
        st.header("🏆 BẢNG TỔNG HỢP CUỐI CÙNG (FINAL SUMMARY)")
        st.dataframe(summary_df, use_container_width=True)
        
        # Cho phép download kết quả summary
        st.download_button("📥 Tải xuống backtest_summary.csv", summary_df.to_csv(index=False).encode('utf-8'), "backtest_summary.csv", "text/csv")
    else:
        st.warning("Không sinh ra lệnh giao dịch hợp lệ nào từ các file đã cấu hình.")

    if len(all_trades) > 0:
        # Gộp tất cả các DataFrame lệnh đơn lẻ lại thành một bảng tổng
        all_trades_df = pd.concat(all_trades, ignore_index=True)
        
        st.sidebar.warning(f"Tổng số lệnh CHIẾN LƯỢC sinh ra: {len(all_trades_df)} lệnh")
        # -------------------------------------------------------------------------
        # ĐIỂM ĐỒNG BỘ 1: ÉP DỮ LIỆU QUA FILE CSV GIẢ LẬP ĐỂ LẤY ĐÚNG INDEX GỐC CỦA COLAB
        # -------------------------------------------------------------------------
        csv_buffer = io.StringIO()
        all_trades_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        df_stats = pd.read_csv(csv_buffer)
        # -------------------------------------------------------------------------

        # Chuẩn hóa lại ngày tháng sau khi đọc từ "file CSV giả lập"
        df_stats['Buy Date'] = pd.to_datetime(df_stats['Buy Date'])
        df_stats['Exit Date'] = pd.to_datetime(df_stats['Exit Date'])

        # Trích xuất số ngày nắm giữ bằng Regex chuẩn như Colab
        df_stats['Hold Days'] = (
            df_stats['Hold time']
            .astype(str)
            .str.extract('(\\d+)')
            .astype(int)
        )

        df_stats['Year'] = df_stats['Buy Date'].dt.year
        df_stats['Month'] = df_stats['Buy Date'].dt.month

        # Hiển thị lịch sử lệnh lên giao diện Streamlit
        st.header("📜 LỊCH SỬ TẤT CẢ CÁC LỆNH (ALL TRADES HISTORY)")
        st.dataframe(df_stats.sort_values(by='Buy Date').reset_index(drop=True), use_container_width=True)
        
        # Tính toán Basic Stats cho cấu trúc hiển thị
        total_t = len(df_stats)
        wins_t = df_stats[df_stats['Profit'] > 0]
        losses_t = df_stats[df_stats['Profit'] <= 0]
        winrate_t = len(wins_t) / total_t * 100 if total_t > 0 else 0
        avg_win_t = wins_t['Profit'].mean() if len(wins_t) > 0 else 0
        avg_loss_t = losses_t['Profit'].mean() if len(losses_t) > 0 else 0
        rr_t = abs(avg_win_t / avg_loss_t) if avg_loss_t != 0 else np.inf
        profit_factor_t = wins_t['Profit'].sum() / abs(losses_t['Profit'].sum()) if losses_t['Profit'].sum() != 0 else np.inf
        expectancy_t = ((winrate_t / 100) * avg_win_t) + ((1 - winrate_t / 100) * avg_loss_t)

        st.subheader("📊 THỐNG KÊ CƠ BẢN (BASIC STATS)")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Tổng số lệnh", total_t)
        col2.metric("Tỷ lệ thắng (Winrate)", f"{winrate_t:.2f}%")
        col3.metric("Profit Factor", f"{profit_factor_t:.2f}")
        col4.metric("Risk Reward Ratio", f"{rr_t:.2f}")
        col5.metric("Kỳ vọng (Expectancy)", f"{expectancy_t:.4f}")

        # --- PHẦN ĐỒ THỊ TRỰC QUAN (VISUALIZATION) ---
        st.header("📊 PHÂN TÍCH BIỂU ĐỒ TRỰC QUAN")
        v_col1, v_col2 = st.columns(2)

        with v_col1:
            st.subheader("Tỷ lệ Thắng vs Thua (Win vs Loss)")
            result_counts = df_stats['Result'].value_counts()
            fig1, ax1 = plt.subplots(figsize=(5, 5))
            ax1.pie(result_counts.values, labels=result_counts.index, autopct='%1.1f%%')
            st.pyplot(fig1)
            plt.close(fig1)  # Giải phóng bộ nhớ RAM đồ họa cho Streamlit

            st.subheader("Phân phối Thời gian Nắm giữ")
            fig3, ax3 = plt.subplots(figsize=(6, 3.5))
            ax3.hist(df_stats['Hold Days'], bins=30)
            ax3.set_xlabel('Ngày nắm giữ')
            ax3.set_ylabel('Tần suất')
            st.pyplot(fig3)
            plt.close(fig3)

        with v_col2:
            st.subheader("Số lượng Lệnh theo Năm (Trades Per Year)")
            trades_per_year = df_stats.groupby('Year').size()
            fig2, ax2 = plt.subplots(figsize=(6, 3.5))
            trades_per_year.plot(kind='bar', ax=ax2)
            ax2.set_ylabel('Số lượng lệnh')
            st.pyplot(fig2)
            plt.close(fig2)

            st.subheader("Lợi nhuận Trung bình theo Tháng Vào lệnh")
            monthly_profit = df_stats.groupby('Month')['Profit'].mean()
            fig4, ax4 = plt.subplots(figsize=(6, 3.5))
            monthly_profit.plot(kind='bar', ax=ax4)
            ax4.set_ylabel('Lợi nhuận TB')
            st.pyplot(fig4)
            plt.close(fig4)

        # ==================== LOGIC BACKTEST QUẢN LÝ VỐN (KHỚP CHUẨN COLAB 100%) ====================
        # st.header("💰 QUẢN LÝ VỐN DANH MỤC (PORTFOLIO BACKTEST LOOP)")
        
        # cash = INITIAL_CAPITAL
        # open_positions = []
        # executed_trades = []

        # # Sắp xếp theo Buy Date bằng thuật toán ổn định 'mergesort' để bảo lưu trật tự quét file gốc
        # df_loop = df_stats.copy()
        # df_loop = df_loop.sort_values(by='Buy Date', kind='mergesort').reset_index(drop=True)

        # for idx, row in df_loop.iterrows():
        #     buy_date = row['Buy Date']
        # ==================== LOGIC BACKTEST QUẢN LÝ VỐN (KHỚP CHUẨN COLAB 100%) ====================
        st.header("💰 QUẢN LÝ VỐN DANH MỤC (PORTFOLIO BACKTEST LOOP)")
        
        cash = INITIAL_CAPITAL
        open_positions = []
        executed_trades = []

        # ----------------------------------------------------------------------------------
        # ĐIỂM SỬA QUYẾT ĐỊNH CUỐI CÙNG: ĐỒNG BỘ TRẬT TỰ BAN ĐẦU CỦA MÃ CỔ PHIẾU
        # 1. Sắp xếp theo mã Stock trước để cố định trật tự (giống như cách glob.glob quét từ A-Z)
        # 2. Sau đó mới dùng 'mergesort' theo Buy Date để giữ vững trật tự A-Z này khi trùng ngày.
        # ----------------------------------------------------------------------------------
        df_loop = df_stats.copy()
        df_loop = df_loop.sort_values(by='Stock').reset_index(drop=True) # Tầng 1: Đồng bộ mã CP
        df_loop = df_loop.sort_values(by='Buy Date', kind='mergesort').reset_index(drop=True) # Tầng 2: Sắp xếp ngày ổn định
        # ----------------------------------------------------------------------------------

        for idx, row in df_loop.iterrows():
            buy_date = row['Buy Date']
            
            # KIỂM TRA THOÁT LỆNH (Giữ nguyên logic bên dưới của bạn...)
            
            # KIỂM TRA THOÁT LỆNH
            remaining_positions = []
            for pos in open_positions:
                if pos['Exit Date'] <= buy_date:
                    cash += pos['Exit Value']
                else:
                    remaining_positions.append(pos)
            open_positions = remaining_positions

            # TÍNH TOÁN SỐ LƯỢNG CỔ PHIẾU
            buy_price = row['Buy Price']
            shares = int(MAX_POSITION_SIZE // buy_price)
            shares = (shares // 100) * 100

            if shares <= 0:
                continue

            position_cost = shares * buy_price

            # KIỂM TRA TIỀN MẶT KHẢ DỤNG
            if cash < position_cost:
                continue

            # THỰC THI KHỚP LỆNH MUA
            cash -= position_cost
            exit_value = shares * row['Exit Price']
            pnl = exit_value - position_cost

            open_positions.append({
                'Exit Date': row['Exit Date'],
                'Exit Value': exit_value
            })

            executed_trades.append({
                'Buy Date': row['Buy Date'], 'Exit Date': row['Exit Date'],
                'Stock': row['Stock'], 'Shares': shares, 'Buy Price': row['Buy Price'],
                'Exit Price': row['Exit Price'], 'Cost': position_cost, 'Exit Value': exit_value,
                'PnL': pnl, 'Profit %': row['Profit'], 'Cash After Buy': cash
            })

        # ĐÓNG TOÀN BỘ VỊ THẾ CÒN LẠI CUỐI CHU KỲ
        for pos in open_positions:
            cash += pos['Exit Value']

        # XỬ LÝ KẾT QUẢ VÀ HIỂN THỊ ĐỒ THỊ VỐN
        if len(executed_trades) > 0:
            executed_df = pd.DataFrame(executed_trades)
            total_profit = cash - INITIAL_CAPITAL
            roi = total_profit / INITIAL_CAPITAL * 100

            # SỬA LỖI 1: Sử dụng 'mergesort' khi xếp theo Exit Date để khóa chặt cấu trúc tính Drawdown
            executed_df = executed_df.sort_values(by='Exit Date', kind='mergesort').reset_index(drop=True)
            
            equity = INITIAL_CAPITAL
            equity_curve = []
            for _, r in executed_df.iterrows():
                equity += r['PnL']
                equity_curve.append(equity)
            
            executed_df['Equity'] = equity_curve
            executed_df['Peak'] = executed_df['Equity'].cummax()
            executed_df['Drawdown'] = (executed_df['Equity'] - executed_df['Peak']) / executed_df['Peak']
            max_drawdown = executed_df['Drawdown'].min()

            # Bảng số liệu Metric tổng hợp chuẩn chỉnh từng đồng
            p_col1, p_col2, p_col3, p_col4 = st.columns(4)
            p_col1.metric("Vốn ban đầu", f"{INITIAL_CAPITAL:,.0f}đ")
            p_col2.metric("Vốn cuối cùng (Final Capital)", f"{cash:,.0f}đ")
            p_col3.metric("Tổng lợi nhuận thực tế (Total Profit)", f"{total_profit:,.0f}đ")
            p_col4.metric("Tỷ lệ ROI %", f"{roi:.2f}%")

            st.write(f"**Số lệnh được thực thi thực tế (Executed Trades):** {len(executed_df)} lệnh")
            st.write(f"**Max Drawdown của tài khoản:** {max_drawdown:.2%}")

            # Thiết lập định dạng hiển thị chi tiết báo cáo năm/tháng
            executed_df['Buy Year'] = pd.to_datetime(executed_df['Buy Date']).dt.year
            executed_df['Buy Month'] = pd.to_datetime(executed_df['Buy Date']).dt.month

            st.subheader("📈 Đường cong tăng trưởng vốn (Equity Curve)")
            fig_eq, ax_eq = plt.subplots(figsize=(14, 5))
            ax_eq.plot(executed_df['Exit Date'], executed_df['Equity'])
            ax_eq.set_title('Equity Curve')
            ax_eq.grid(True)
            st.pyplot(fig_eq)
            plt.close(fig_eq)

            st.subheader("📆 Thống kê chi tiết theo năm (Yearly Portfolio Stats)")
            yearly_stats = executed_df.groupby('Buy Year').agg({
                'PnL': ['sum', 'mean', 'count'],
                'Profit %': 'mean',
                'Drawdown': 'min'
            })
            yearly_stats.columns = ['Total PnL', 'Average PnL', 'Total Trades', 'Average Profit %', 'Worst Drawdown']
            st.dataframe(yearly_stats, use_container_width=True)

            st.subheader("📅 Ma trận số lượng lệnh phát sinh theo tháng/năm")
            monthly_trades = pd.crosstab(executed_df['Buy Year'], executed_df['Buy Month'])
            st.dataframe(monthly_trades, use_container_width=True)
            
            # SỬA LỖI 2: Đưa DataFrame về cấu trúc sắp xếp Buy Date trước khi người dùng tải file, đồng thời ép mã hóa utf-8-sig chống lỗi Excel
            download_df = executed_df.sort_values(by='Buy Date', kind='mergesort').reset_index(drop=True)
            csv_data = download_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Tải xuống executed_trades.csv", csv_data, "executed_trades.csv", "text/csv")
