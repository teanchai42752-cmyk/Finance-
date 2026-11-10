
import streamlit as st
import pandas as pd
import numpy as np
import io

# =====================================================
# 1. PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="Professional Financial Dashboard",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# 2. MENU CONSTANTS
# =====================================================

MENU_TRADING = "Trading Signals"
MENU_DCF = "DCF Valuation"
MENU_FEASIBILITY = "Feasibility Study"

MENU_OPTIONS = [
    MENU_TRADING,
    MENU_DCF,
    MENU_FEASIBILITY
]

# =====================================================
# 3. GLOBAL STYLE
# =====================================================

st.markdown("""
<style>
    .main {
        background-color: #f8fafc;
    }

    div[data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #e2e8f0;
        padding: 16px;
        border-radius: 12px;
    }

    div[data-testid="stMetricValue"] {
        color: #0f766e;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


# =====================================================
# 4. HELPER FUNCTIONS
# =====================================================

def read_financial_file(uploaded_file):

    file_bytes = uploaded_file.getvalue()

    if uploaded_file.name.lower().endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(file_bytes))

    elif uploaded_file.name.lower().endswith(".csv"):

        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding="utf-8-sig"
            )

        except UnicodeDecodeError:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding="cp874"
            )

    else:
        raise ValueError("รองรับเฉพาะไฟล์ .xlsx และ .csv")

    # Remove accidental spaces in column names
    df.columns = df.columns.astype(str).str.strip()

    return df


def validate_forecast(df):

    required_columns = [
        "EBIT",
        "Tax Rate (%)",
        "D&A",
        "CapEx",
        "Change in NWC"
    ]

    missing_columns = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            "ไม่พบคอลัมน์: "
            + ", ".join(missing_columns)
        )

    if len(df) < 5:
        raise ValueError(
            "ข้อมูลต้องมีอย่างน้อย 5 ปี"
        )

    df = df.head(5).copy()

    for col in required_columns:

        df[col] = pd.to_numeric(
            df[col],
            errors="raise"
        )

    # Convert tax rate to percentage
    df["Tax Rate (%)"] = df["Tax Rate (%)"].apply(
        lambda x: x * 100 if 0 <= x <= 1 else x
    )

    values = df[required_columns].to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise ValueError(
            "พบข้อมูลว่างหรือค่าตัวเลขที่ไม่ถูกต้อง"
        )

    if (
        (df["Tax Rate (%)"] < 0).any()
        or (df["Tax Rate (%)"] > 100).any()
    ):
        raise ValueError(
            "Tax Rate ต้องอยู่ระหว่าง 0-100%"
        )

    if (df["D&A"] < 0).any():
        raise ValueError("D&A ต้องไม่ติดลบ")

    if (df["CapEx"] < 0).any():
        raise ValueError("CapEx ต้องไม่ติดลบ")

    if "Year" not in df.columns:

        df.insert(
            0,
            "Year",
            [f"Year {i}" for i in range(1, 6)]
        )

    else:
        df["Year"] = df["Year"].astype(str)

    return df.to_dict("records")


def calculate_wacc(
    risk_free_rate,
    beta,
    equity_risk_premium,
    cost_of_debt,
    tax_rate,
    equity_weight,
    debt_weight
):

    total_weight = equity_weight + debt_weight

    if total_weight <= 0:
        raise ValueError(
            "สัดส่วนเงินทุนรวมต้องมากกว่า 0"
        )

    equity_weight = equity_weight / total_weight
    debt_weight = debt_weight / total_weight

    # CAPM
    cost_of_equity = (
        risk_free_rate
        + beta * equity_risk_premium
    )

    # After-tax Cost of Debt
    after_tax_cost_of_debt = (
        cost_of_debt * (1 - tax_rate)
    )

    # WACC
    wacc = (
        equity_weight * cost_of_equity
        + debt_weight * after_tax_cost_of_debt
    )

    return (
        cost_of_equity,
        after_tax_cost_of_debt,
        wacc,
        equity_weight,
        debt_weight
    )


def calculate_fcff(forecast_data, wacc):

    results = []
    total_pv_fcf = 0

    for year, row in enumerate(
        forecast_data,
        start=1
    ):

        ebit = float(row["EBIT"])
        tax_rate = float(row["Tax Rate (%)"]) / 100
        da = float(row["D&A"])
        capex = float(row["CapEx"])
        change_nwc = float(row["Change in NWC"])

        # 1. Tax Expense
        tax_expense = ebit * tax_rate

        # 2. NOPAT
        nopat = ebit - tax_expense

        # 3. Add back D&A
        after_da = nopat + da

        # 4. Deduct CapEx
        after_capex = after_da - capex

        # 5. Deduct Change in NWC
        fcff = after_capex - change_nwc

        # Discount Factor
        discount_factor = (
            1 / (1 + wacc) ** year
        )

        # Present Value
        pv_fcf = fcff * discount_factor

        total_pv_fcf += pv_fcf

        results.append({

            "Year": row["Year"],
            "EBIT": ebit,
            "Tax Rate (%)": tax_rate * 100,
            "Tax Expense": tax_expense,
            "NOPAT": nopat,
            "D&A": da,
            "After D&A": after_da,
            "CapEx": capex,
            "After CapEx": after_capex,
            "Change in NWC": change_nwc,
            "FCFF": fcff,
            "Discount Factor": discount_factor,
            "PV of FCFF": pv_fcf

        })

    return pd.DataFrame(results), total_pv_fcf


def calculate_dcf(
    fcffs,
    wacc,
    terminal_growth,
    pv_forecast
):

    if wacc <= terminal_growth:
        raise ValueError(
            "WACC ต้องมากกว่า Terminal Growth Rate"
        )

    if wacc <= 0:
        raise ValueError("WACC ต้องมากกว่า 0")

    if len(fcffs) != 5:
        raise ValueError("ต้องมี FCFF จำนวน 5 ปี")

    # Year 6 FCFF
    fcff_year6 = (
        fcffs[-1] * (1 + terminal_growth)
    )

    # Terminal Value
    terminal_value = (
        fcff_year6 / (wacc - terminal_growth)
    )

    # Present Value of Terminal Value
    pv_terminal = (
        terminal_value / (1 + wacc) ** 5
    )

    # Enterprise Value
    enterprise_value = (
        pv_forecast + pv_terminal
    )

    return (
        fcff_year6,
        terminal_value,
        pv_terminal,
        enterprise_value
    )


def calculate_sensitivity(
    fcffs,
    base_wacc,
    base_growth
):

    wacc_values = [
        base_wacc - 0.02,
        base_wacc - 0.01,
        base_wacc,
        base_wacc + 0.01,
        base_wacc + 0.02
    ]

    growth_values = [
        base_growth - 0.01,
        base_growth - 0.005,
        base_growth,
        base_growth + 0.005,
        base_growth + 0.01
    ]

    rows = []

    for wacc in wacc_values:

        row = {
            "WACC (%)": wacc * 100
        }

        for growth in growth_values:

            column_name = f"{growth * 100:.2f}%"

            if wacc <= growth or wacc <= 0:

                row[column_name] = np.nan

            else:

                fcff_year6 = (
                    fcffs[-1] * (1 + growth)
                )

                terminal_value = (
                    fcff_year6 / (wacc - growth)
                )

                pv_terminal = (
                    terminal_value / (1 + wacc) ** 5
                )

                pv_forecast = sum(
                    fcff / (1 + wacc) ** year
                    for year, fcff in enumerate(
                        fcffs,
                        start=1
                    )
                )

                row[column_name] = (
                    pv_forecast + pv_terminal
                )

        rows.append(row)

    return pd.DataFrame(rows)


# =====================================================
# 5. PAGE 1: TRADING SIGNALS
# =====================================================

def render_trading_signals():

    st.title("📈 Trading Signals")
    st.write("วิเคราะห์แนวโน้มราคาและสัญญาณทางเทคนิคสำหรับหุ้นและสินทรัพย์หลัก")
    st.caption("ข้อมูลราคาอ้างอิงจาก Yahoo Finance ผ่าน yfinance อาจล่าช้าและไม่ใช่ราคาสำหรับส่งคำสั่งซื้อขายจริง")

    symbol_map = {
        "AAPL": "AAPL",
        "TSLA": "TSLA",
        "XAU/USD": "XAUUSD=X",
        "EUR/USD": "EURUSD=X"
    }

    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        asset = st.selectbox("เลือกสินทรัพย์", list(symbol_map.keys()), key="signals_asset")
    with c2:
        period = st.selectbox("ช่วงข้อมูล", ["3mo", "6mo", "1y", "2y"], index=2, key="signals_period")
    with c3:
        interval = st.selectbox("Timeframe", ["1d", "1h", "30m"], index=0, key="signals_interval")

    if interval == "30m" and period != "1mo":
        period = "1mo"
        st.info("ปรับช่วงข้อมูลเป็น 1mo เนื่องจากข้อมูล 30 นาทีมีข้อจำกัดด้านระยะเวลาย้อนหลัง")
    elif interval == "1h" and period == "2y":
        period = "6mo"
        st.info("ปรับช่วงข้อมูลเป็น 6mo เนื่องจากข้อมูลรายชั่วโมงมีข้อจำกัดด้านระยะเวลาย้อนหลัง")

    if st.button("🔄 โหลดข้อมูลล่าสุด", type="primary", key="refresh_signals"):
        st.cache_data.clear()

    @st.cache_data(ttl=60, show_spinner=False)
    def load_market_data(ticker, selected_period, selected_interval):
        import yfinance as yf
        data = yf.download(
            ticker,
            period=selected_period,
            interval=selected_interval,
            auto_adjust=True,
            progress=False,
            threads=False
        )
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        data = data.rename(columns=str.title)
        return data

    try:
        with st.spinner(f"กำลังดึงข้อมูล {asset}..."):
            market = load_market_data(symbol_map[asset], period, interval)

        if market.empty or "Close" not in market.columns:
            st.error("ไม่พบข้อมูลราคา กรุณาลองเปลี่ยนช่วงเวลาหรือกลับมาตรวจสอบอีกครั้ง")
            return

        market = market.copy()
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col in market.columns:
                market[col] = pd.to_numeric(market[col], errors="coerce")
        market = market.dropna(subset=["Close"])
        if len(market) < 20:
            st.warning("ข้อมูลมีน้อยเกินไปสำหรับการคำนวณตัวชี้วัด กรุณาเลือกช่วงเวลาที่ยาวขึ้น")
            return

        close = market["Close"]
        market["SMA 5"] = close.rolling(5).mean()
        market["SMA 15"] = close.rolling(15).mean()
        market["EMA 12"] = close.ewm(span=12, adjust=False).mean()
        market["EMA 26"] = close.ewm(span=26, adjust=False).mean()
        market["MACD"] = market["EMA 12"] - market["EMA 26"]
        market["MACD Signal"] = market["MACD"].ewm(span=9, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        market["RSI 14"] = 100 - (100 / (1 + rs))
        market["RSI 14"] = market["RSI 14"].fillna(50)

        market["TR"] = pd.concat([
            market["High"] - market["Low"],
            (market["High"] - close.shift()).abs(),
            (market["Low"] - close.shift()).abs()
        ], axis=1).max(axis=1) if {"High", "Low"}.issubset(market.columns) else close.diff().abs()
        market["ATR 14"] = market["TR"].rolling(14).mean()

        latest = market.iloc[-1]
        previous = market.iloc[-2]
        price = float(latest["Close"])
        prior_price = float(previous["Close"])
        change = price - prior_price
        change_pct = (change / prior_price * 100) if prior_price else 0.0
        sma_fast = float(latest["SMA 5"])
        sma_slow = float(latest["SMA 15"])
        rsi = float(latest["RSI 14"])
        macd = float(latest["MACD"])
        macd_signal = float(latest["MACD Signal"])

        if sma_fast > sma_slow and macd > macd_signal and rsi < 70:
            signal = "BUY"
            rationale = "SMA 5 อยู่เหนือ SMA 15 และ MACD เป็นบวกเมื่อเทียบกับเส้น Signal โดย RSI ยังไม่เข้าสู่เขตซื้อมากเกินไป"
        elif sma_fast < sma_slow and macd < macd_signal and rsi > 30:
            signal = "SELL"
            rationale = "SMA 5 อยู่ต่ำกว่า SMA 15 และ MACD ต่ำกว่าเส้น Signal โดย RSI ยังไม่เข้าสู่เขตขายมากเกินไป"
        else:
            signal = "HOLD"
            rationale = "สัญญาณจากแนวโน้มและโมเมนตัมยังไม่สอดคล้องกันเพียงพอ"

        atr = float(latest["ATR 14"]) if pd.notna(latest["ATR 14"]) else price * 0.01
        if signal == "BUY":
            stop_loss = price - 1.5 * atr
            take_profit = price + 3.0 * atr
        elif signal == "SELL":
            stop_loss = price + 1.5 * atr
            take_profit = price - 3.0 * atr
        else:
            stop_loss = np.nan
            take_profit = np.nan

        st.divider()
        st.subheader(f"Market Overview — {asset}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Last Price", f"{price:,.5f}" if "FX" in symbol_map[asset] else f"{price:,.2f}")
        m2.metric("Change", f"{change:+,.5f}", f"{change_pct:+.2f}%")
        m3.metric("Trading Signal", signal)
        m4.metric("RSI (14)", f"{rsi:.2f}")

        signal_color = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}[signal]
        st.markdown(f"### {signal_color} {signal}")
        st.write(rationale)

        s1, s2, s3 = st.columns(3)
        s1.metric("Entry Reference", f"{price:,.5f}")
        s2.metric("Stop Loss", f"{stop_loss:,.5f}" if pd.notna(stop_loss) else "รอสัญญาณ")
        s3.metric("Take Profit (RR 1:2)", f"{take_profit:,.5f}" if pd.notna(take_profit) else "รอสัญญาณ")

        st.caption("ระดับ Stop Loss / Take Profit เป็นตัวอย่างจาก ATR 1.5 เท่า และ Risk:Reward 1:2 ไม่ใช่คำแนะนำลงทุนหรือคำสั่งซื้อขาย")
        st.divider()
        st.subheader("Price & Moving Averages")
        chart_columns = ["Close", "SMA 5", "SMA 15"]
        st.line_chart(market[chart_columns].tail(150), use_container_width=True)

        left, right = st.columns(2)
        with left:
            st.subheader("MACD")
            st.line_chart(market[["MACD", "MACD Signal"]].tail(150), use_container_width=True)
        with right:
            st.subheader("RSI (14)")
            st.line_chart(market[["RSI 14"]].tail(150), use_container_width=True)

        st.subheader("Technical Indicators")
        indicator_view = market[["Close", "SMA 5", "SMA 15", "RSI 14", "MACD", "MACD Signal", "ATR 14"]].tail(10).sort_index(ascending=False)
        st.dataframe(indicator_view.style.format("{:,.4f}"), use_container_width=True)

        csv_data = market.reset_index().to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 Download Market Data & Indicators", csv_data, f"{asset.replace('/', '_')}_signals.csv", "text/csv")
        st.caption(f"แหล่งข้อมูล: Yahoo Finance | Ticker: {symbol_map[asset]} | อัปเดตตามข้อมูลล่าสุดที่ผู้ให้บริการเปิดเผย")
    except Exception as e:
        st.error(f"ไม่สามารถประมวลผล Trading Signals ได้: {e}")
        st.info("ตรวจสอบการเชื่อมต่ออินเทอร์เน็ตและลองโหลดข้อมูลใหม่")


# =====================================================
# 6. PAGE 2: DCF VALUATION
# =====================================================

def render_dcf_valuation():

    st.title("💰 Professional DCF Valuation")

    st.write(
        "ระบบประเมินมูลค่ากิจการด้วยวิธี "
        "Discounted Cash Flow (DCF) "
        "โดยใช้ Free Cash Flow to Firm (FCFF)"
    )

    st.divider()

    # ---------------------------------------------
    # 6.1 FILE UPLOAD
    # ---------------------------------------------

    st.subheader("📂 Financial Statement Upload")

    uploaded_file = st.file_uploader(
        "อัปโหลดไฟล์งบการเงิน",
        type=["xlsx", "csv"],
        help="รองรับ Excel และ CSV ที่มีข้อมูลประมาณการอย่างน้อย 5 ปี",
        key="dcf_upload"
    )

    financial_df = None

    if uploaded_file is not None:

        try:

            financial_df = read_financial_file(
                uploaded_file
            )

            st.success(
                f"อัปโหลด {uploaded_file.name} สำเร็จ"
            )

            st.dataframe(
                financial_df.head(5),
                use_container_width=True,
                hide_index=True
            )

        except Exception as e:

            st.error(
                f"ไม่สามารถอ่านไฟล์ได้: {e}"
            )

    else:

        st.info(
            "หากไม่มีไฟล์ สามารถกรอกตัวเลขทางการเงินด้วยตนเองได้"
        )

    # Template
    template = pd.DataFrame({

        "Year": [2027, 2028, 2029, 2030, 2031],
        "EBIT": [150, 165, 180, 195, 210],
        "Tax Rate (%)": [20, 20, 20, 20, 20],
        "D&A": [30, 32, 35, 38, 40],
        "CapEx": [40, 45, 50, 55, 60],
        "Change in NWC": [10, 12, 15, 15, 18]

    })

    st.download_button(
        "📥 Download Financial Template",
        data=template.to_csv(
            index=False
        ).encode("utf-8-sig"),
        file_name="DCF_Template.csv",
        mime="text/csv"
    )

    st.divider()

    # ---------------------------------------------
    # 6.2 WACC CALCULATOR
    # ---------------------------------------------

    st.subheader("⚙️ WACC Calculator")

    wacc_method = st.radio(
        "วิธีคำนวณ WACC",
        [
            "Manual WACC",
            "Calculate WACC using CAPM"
        ],
        horizontal=True,
        key="wacc_method"
    )

    wacc = None

    if wacc_method == "Manual WACC":

        wacc = st.number_input(
            "WACC (%)",
            min_value=0.1,
            max_value=100.0,
            value=10.0,
            step=0.5,
            key="manual_wacc"
        ) / 100

    elif wacc_method == "Calculate WACC using CAPM":

        col1, col2 = st.columns(2)

        with col1:

            risk_free = st.number_input(
                "Risk-Free Rate (%)",
                value=2.5,
                min_value=0.0,
                max_value=100.0,
                step=0.1
            ) / 100

            beta = st.number_input(
                "Levered Beta",
                value=1.0,
                min_value=-5.0,
                max_value=10.0,
                step=0.1
            )

            erp = st.number_input(
                "Equity Risk Premium (%)",
                value=6.0,
                min_value=0.0,
                max_value=100.0,
                step=0.1
            ) / 100

        with col2:

            cost_debt = st.number_input(
                "Pre-tax Cost of Debt (%)",
                value=5.0,
                min_value=0.0,
                max_value=100.0,
                step=0.1
            ) / 100

            debt_tax = st.number_input(
                "Debt Tax Rate (%)",
                value=20.0,
                min_value=0.0,
                max_value=100.0
            ) / 100

            equity_weight = st.number_input(
                "Equity Weight (%)",
                value=70.0,
                min_value=0.0,
                max_value=100.0
            )

            debt_weight = st.number_input(
                "Debt Weight (%)",
                value=30.0,
                min_value=0.0,
                max_value=100.0
            )

        try:

            (
                cost_equity,
                after_tax_debt,
                wacc,
                actual_equity,
                actual_debt
            ) = calculate_wacc(
                risk_free,
                beta,
                erp,
                cost_debt,
                debt_tax,
                equity_weight,
                debt_weight
            )

            st.success("WACC Calculation Completed")

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Cost of Equity",
                f"{cost_equity * 100:.2f}%"
            )

            c2.metric(
                "After-tax Cost of Debt",
                f"{after_tax_debt * 100:.2f}%"
            )

            c3.metric(
                "Calculated WACC",
                f"{wacc * 100:.2f}%"
            )

        except ValueError as e:

            st.error(str(e))
            wacc = None

    st.divider()

    # ---------------------------------------------
    # 6.3 TERMINAL GROWTH RATE
    # ---------------------------------------------

    st.subheader("📌 Valuation Assumptions")

    terminal_growth = st.number_input(
        "Terminal Growth Rate (%)",
        min_value=-10.0,
        max_value=50.0,
        value=3.0,
        step=0.5
    ) / 100

    # ---------------------------------------------
    # 6.4 MANUAL INPUT
    # ---------------------------------------------

    if uploaded_file is None:

        st.divider()

        st.subheader("✏️ Manual Financial Inputs")

        st.caption(
            "ใช้ตัวเลขชุดเดียวกันเป็นสมมติฐานรายปีตลอด 5 ปี"
        )

        c1, c2 = st.columns(2)

        with c1:

            ebit = st.number_input(
                "EBIT (ล้านบาท)",
                value=150.0,
                step=10.0
            )

            tax_rate = st.number_input(
                "Tax Rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=20.0
            )

            da = st.number_input(
                "D&A (ล้านบาท)",
                min_value=0.0,
                value=30.0,
                step=5.0
            )

        with c2:

            capex = st.number_input(
                "CapEx (ล้านบาท)",
                min_value=0.0,
                value=40.0,
                step=5.0
            )

            change_nwc = st.number_input(
                "Change in NWC (ล้านบาท)",
                value=10.0,
                step=5.0
            )

    st.divider()

    # ---------------------------------------------
    # 6.5 EQUITY BRIDGE
    # ---------------------------------------------

    st.subheader("🏦 Equity Value Bridge")

    c1, c2, c3 = st.columns(3)

    with c1:

        total_debt = st.number_input(
            "Total Debt (ล้านบาท)",
            min_value=0.0,
            value=0.0,
            step=10.0
        )

    with c2:

        cash = st.number_input(
            "Cash & Equivalents (ล้านบาท)",
            min_value=0.0,
            value=0.0,
            step=10.0
        )

    with c3:

        shares = st.number_input(
            "จำนวนหุ้น (ล้านหุ้น)",
            min_value=0.0,
            value=100.0,
            step=10.0
        )

    st.divider()

    # ---------------------------------------------
    # 6.6 CALCULATE
    # ---------------------------------------------

    if st.button(
        "🚀 Calculate Professional DCF",
        type="primary",
        use_container_width=True,
        key="calculate_dcf"
    ):

        if wacc is None:

            st.error(
                "กรุณาตรวจสอบข้อมูล WACC"
            )

        elif wacc <= terminal_growth:

            st.error(
                "WACC ต้องมากกว่า Terminal Growth Rate"
            )

        elif wacc <= 0:

            st.error(
                "WACC ต้องมากกว่า 0"
            )

        elif uploaded_file is not None and financial_df is None:

            st.error(
                "ไม่สามารถใช้ไฟล์ที่อัปโหลดได้ "
                "กรุณาตรวจสอบไฟล์อีกครั้ง"
            )

        else:

            try:

                # Prepare Forecast Data

                if uploaded_file is not None:

                    forecast_data = validate_forecast(
                        financial_df
                    )

                else:

                    forecast_data = []

                    for year in range(1, 6):

                        forecast_data.append({

                            "Year": f"Year {year}",
                            "EBIT": ebit,
                            "Tax Rate (%)": tax_rate,
                            "D&A": da,
                            "CapEx": capex,
                            "Change in NWC": change_nwc

                        })

                # Calculate FCFF

                result_df, pv_forecast = calculate_fcff(
                    forecast_data,
                    wacc
                )

                fcffs = result_df["FCFF"].tolist()

                (
                    fcff_year6,
                    terminal_value,
                    pv_terminal,
                    enterprise_value
                ) = calculate_dcf(
                    fcffs,
                    wacc,
                    terminal_growth,
                    pv_forecast
                )

                # Equity Bridge

                net_debt = total_debt - cash

                equity_value = (
                    enterprise_value - net_debt
                )

                intrinsic_value = (
                    equity_value / shares
                    if shares > 0
                    else None
                )

                # ---------------------------------
                # DISPLAY FORECAST
                # ---------------------------------

                st.success(
                    "DCF Calculation Completed Successfully!"
                )

                st.divider()

                st.subheader(
                    "📊 5-Year FCFF Forecast"
                )

                st.caption(
                    "หน่วย: ล้านบาท | "
                    "FCFF = EBIT × (1 - Tax Rate) "
                    "+ D&A - CapEx - Change in NWC"
                )

                format_dict = {
                    col: "{:,.2f}"
                    for col in result_df.columns
                    if col != "Year"
                }

                st.dataframe(
                    result_df.style.format(format_dict),
                    use_container_width=True,
                    hide_index=True
                )

                # Download FCFF
                st.download_button(
                    "📥 Download FCFF Forecast",
                    data=result_df.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name="DCF_FCFF_Forecast.csv",
                    mime="text/csv"
                )

                # ---------------------------------
                # FCFF CHART
                # ---------------------------------

                st.divider()

                st.subheader(
                    "📈 FCFF Forecast Chart"
                )

                chart_df = result_df.set_index(
                    "Year"
                )[["FCFF", "PV of FCFF"]]

                st.bar_chart(
                    chart_df,
                    use_container_width=True
                )

                # ---------------------------------
                # TERMINAL VALUE
                # ---------------------------------

                st.divider()

                st.subheader(
                    "♾️ Terminal Value Analysis"
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Year 5 FCFF",
                    f"{fcffs[-1]:,.2f} MB"
                )

                c2.metric(
                    "Year 6 FCFF",
                    f"{fcff_year6:,.2f} MB"
                )

                c3.metric(
                    "Terminal Value",
                    f"{terminal_value:,.2f} MB"
                )

                # ---------------------------------
                # ENTERPRISE VALUE
                # ---------------------------------

                st.divider()

                st.subheader(
                    "💎 Enterprise Value"
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "PV of 5-Year FCFF",
                    f"{pv_forecast:,.2f} MB"
                )

                c2.metric(
                    "PV of Terminal Value",
                    f"{pv_terminal:,.2f} MB"
                )

                c3.metric(
                    "Enterprise Value",
                    f"{enterprise_value:,.2f} MB"
                )

                # ---------------------------------
                # EQUITY VALUE
                # ---------------------------------

                st.divider()

                st.subheader(
                    "🏦 Equity Valuation"
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Net Debt",
                    f"{net_debt:,.2f} MB"
                )

                c2.metric(
                    "Equity Value",
                    f"{equity_value:,.2f} MB"
                )

                c3.metric(
                    "Intrinsic Value / Share",
                    (
                        f"{intrinsic_value:,.2f} Baht"
                        if intrinsic_value is not None
                        else "N/A"
                    )
                )

                # ---------------------------------
                # VALUATION BREAKDOWN
                # ---------------------------------

                st.divider()

                st.subheader(
                    "📋 Valuation Breakdown"
                )

                breakdown = pd.DataFrame({

                    "รายการ": [
                        "PV of Forecast FCFF",
                        "Terminal Value",
                        "PV of Terminal Value",
                        "Enterprise Value",
                        "Less: Total Debt",
                        "Add: Cash & Equivalents",
                        "Equity Value",
                        "Intrinsic Value per Share"
                    ],

                    "มูลค่า": [
                        pv_forecast,
                        terminal_value,
                        pv_terminal,
                        enterprise_value,
                        -total_debt,
                        cash,
                        equity_value,
                        intrinsic_value
                    ]

                })

                st.dataframe(
                    breakdown.style.format({
                        "มูลค่า": lambda x: (
                            f"{x:,.2f}"
                            if pd.notna(x)
                            else "N/A"
                        )
                    }),
                    use_container_width=True,
                    hide_index=True
                )

                # ---------------------------------
                # SENSITIVITY ANALYSIS
                # ---------------------------------

                st.divider()

                st.subheader(
                    "🎯 Sensitivity Analysis"
                )

                st.write(
                    "เปรียบเทียบ Enterprise Value "
                    "ภายใต้ระดับ WACC และ Terminal Growth Rate ที่แตกต่างกัน"
                )

                sensitivity_df = calculate_sensitivity(
                    fcffs,
                    wacc,
                    terminal_growth
                )

                st.caption(
                    "แถว = WACC | คอลัมน์ = Terminal Growth Rate | หน่วย: ล้านบาท"
                )

                st.dataframe(
                    sensitivity_df.style.format(
                        "{:,.2f}",
                        na_rep="N/A"
                    ),
                    use_container_width=True,
                    hide_index=True
                )

                st.download_button(
                    "📥 Download Sensitivity Analysis",
                    data=sensitivity_df.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    file_name="DCF_Sensitivity.csv",
                    mime="text/csv"
                )

                # ---------------------------------
                # ASSUMPTIONS
                # ---------------------------------

                st.divider()

                st.subheader(
                    "⚙️ Valuation Assumptions"
                )

                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "WACC",
                    f"{wacc * 100:.2f}%"
                )

                c2.metric(
                    "Terminal Growth",
                    f"{terminal_growth * 100:.2f}%"
                )

                c3.metric(
                    "Forecast Period",
                    "5 Years"
                )

                if enterprise_value < 0:

                    st.warning(
                        "Enterprise Value มีค่าติดลบ "
                        "ควรตรวจสอบสมมติฐานทางการเงิน"
                    )

                st.info(
                    "หมายเหตุ: Enterprise Value เป็นมูลค่ากิจการ "
                    "ส่วน Equity Value คำนวณจาก Enterprise Value "
                    "หัก Net Debt และ Intrinsic Value per Share "
                    "คำนวณจาก Equity Value หารด้วยจำนวนหุ้น"
                )

            except Exception as e:

                st.error(
                    f"เกิดข้อผิดพลาดในการคำนวณ DCF: {e}"
                )


# =====================================================
# 7. PAGE 3: FEASIBILITY STUDY
# =====================================================

def render_feasibility_study():

    st.title("📊 Feasibility Study")
    st.write("ประเมินความเป็นไปได้ทางการเงินของโครงการลงทุนด้วยประมาณการกระแสเงินสด ภาษี ค่าเสื่อมราคา และตัวชี้วัดความคุ้มค่า")
    st.caption("ผลลัพธ์เป็นแบบจำลองจากสมมติฐานที่ผู้ใช้ป้อน ไม่ใช่คำแนะนำการลงทุน")
    st.divider()

    st.subheader("1. Project Assumptions")
    with st.form("feasibility_inputs"):
        c1, c2, c3 = st.columns(3)
        with c1:
            project_name = st.text_input("ชื่อโครงการ", value="New Investment Project")
            initial_investment = st.number_input("เงินลงทุนสินทรัพย์เริ่มต้น (บาท)", min_value=0.0, value=5_000_000.0, step=100_000.0)
            project_years = st.number_input("ระยะเวลาโครงการ (ปี)", min_value=1, max_value=20, value=5, step=1)
        with c2:
            annual_revenue = st.number_input("รายได้ปีแรก (บาท)", min_value=0.0, value=2_500_000.0, step=100_000.0)
            revenue_growth = st.number_input("อัตราการเติบโตของรายได้ต่อปี (%)", min_value=-50.0, max_value=200.0, value=5.0, step=1.0)
            variable_cost_pct = st.number_input("ต้นทุนผันแปรต่อรายได้ (%)", min_value=0.0, max_value=100.0, value=35.0, step=1.0)
        with c3:
            fixed_cost = st.number_input("ค่าใช้จ่ายคงที่ปีแรก (บาท)", min_value=0.0, value=900_000.0, step=50_000.0)
            fixed_cost_growth = st.number_input("การเติบโตของค่าใช้จ่ายคงที่ (%)", min_value=-50.0, max_value=100.0, value=3.0, step=1.0)
            discount_rate = st.number_input("อัตราคิดลด / Required Return (%)", min_value=0.1, max_value=100.0, value=10.0, step=0.5)
        c4, c5, c6 = st.columns(3)
        with c4:
            tax_rate = st.number_input("อัตราภาษีเงินได้นิติบุคคล (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0)
        with c5:
            annual_capex = st.number_input("เงินลงทุนเพิ่มเติมต่อปี (บาท)", min_value=0.0, value=0.0, step=50_000.0)
        with c6:
            salvage_value = st.number_input("มูลค่าซากเมื่อสิ้นสุดโครงการ (บาท)", min_value=0.0, value=0.0, step=50_000.0)
        c7, c8 = st.columns(2)
        with c7:
            working_capital_pct = st.number_input("เงินทุนหมุนเวียน (% ของรายได้)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)
        with c8:
            depreciation_method = st.selectbox("วิธีคิดค่าเสื่อมราคา", ["Straight-line (เส้นตรง)", "ไม่คิดค่าเสื่อมราคา"])
        submitted = st.form_submit_button("🚀 ประเมินความคุ้มค่าของโครงการ", type="primary", use_container_width=True)

    if not submitted:
        st.info("กรอกสมมติฐานของโครงการ แล้วกดปุ่มประเมินเพื่อคำนวณ NPV, IRR และระยะเวลาคืนทุน")
        return

    try:
        growth = revenue_growth / 100
        fixed_growth = fixed_cost_growth / 100
        tax = tax_rate / 100
        discount = discount_rate / 100
        variable_ratio = variable_cost_pct / 100
        nwc_ratio = working_capital_pct / 100
        years = int(project_years)

        if initial_investment <= 0:
            st.error("เงินลงทุนเริ่มต้นต้องมากกว่า 0")
            return
        if discount <= 0:
            st.error("อัตราคิดลดต้องมากกว่า 0")
            return
        if 1 + growth <= 0 or 1 + fixed_growth <= 0:
            st.error("อัตราการเติบโตต้องไม่ทำให้รายได้หรือค่าใช้จ่ายติดลบ")
            return

        annual_depreciation = (
            max(0.0, initial_investment - salvage_value) / years
            if depreciation_method.startswith("Straight-line")
            else 0.0
        )
        initial_nwc = annual_revenue * nwc_ratio
        nwc_balance = initial_nwc
        cash_flows = [-initial_investment - initial_nwc]
        rows = []
        revenue = annual_revenue
        fixed = fixed_cost

        for year in range(1, years + 1):
            if year > 1:
                revenue *= (1 + growth)
                fixed *= (1 + fixed_growth)

            variable_cost = revenue * variable_ratio
            ebitda = revenue - variable_cost - fixed
            depreciation = annual_depreciation
            ebit = ebitda - depreciation
            tax_expense = max(0.0, ebit * tax)
            nopat = ebit - tax_expense
            operating_cash_flow = nopat + depreciation

            capex = annual_capex
            if year == years:
                change_nwc = -nwc_balance
                nwc_balance = 0.0
            elif year == 1:
                change_nwc = 0.0
            else:
                required_nwc = revenue * nwc_ratio
                change_nwc = required_nwc - nwc_balance
                nwc_balance = required_nwc

            free_cash_flow = operating_cash_flow - capex - change_nwc
            if year == years:
                free_cash_flow += salvage_value

            discount_factor = 1 / ((1 + discount) ** year)
            discounted_cf = free_cash_flow * discount_factor
            cash_flows.append(float(free_cash_flow))
            rows.append({
                "Year": year,
                "Revenue": revenue,
                "Variable Costs": variable_cost,
                "Fixed Costs": fixed,
                "EBITDA": ebitda,
                "Depreciation": depreciation,
                "EBIT": ebit,
                "Cash Tax": tax_expense,
                "NOPAT": nopat,
                "Add Back Depreciation": depreciation,
                "Additional CapEx": capex,
                "Change in NWC": change_nwc,
                "Salvage Value": salvage_value if year == years else 0.0,
                "Free Cash Flow": free_cash_flow,
                "Discount Factor": discount_factor,
                "Present Value": discounted_cf
            })

        forecast_df = pd.DataFrame(rows)
        npv = float(sum(cf / ((1 + discount) ** year) for year, cf in enumerate(cash_flows)))
        try:
            import numpy_financial as npf
            irr_value = float(npf.irr(cash_flows))
            if not np.isfinite(irr_value):
                irr_value = None
        except Exception:
            irr_value = None

        cumulative = cash_flows[0]
        payback = None
        discounted_cumulative = cash_flows[0]
        discounted_payback = None
        for idx, cf in enumerate(cash_flows[1:], start=1):
            previous_cumulative = cumulative
            cumulative += cf
            if payback is None and cumulative >= 0 and cf > 0:
                payback = (idx - 1) + abs(previous_cumulative) / cf
            previous_discounted = discounted_cumulative
            discounted_cf = cf / ((1 + discount) ** idx)
            discounted_cumulative += discounted_cf
            if discounted_payback is None and discounted_cumulative >= 0 and discounted_cf > 0:
                discounted_payback = (idx - 1) + abs(previous_discounted) / discounted_cf

        total_initial_funding = initial_investment + initial_nwc
        profitability_index = (
            (npv + total_initial_funding) / total_initial_funding
            if total_initial_funding > 0 else np.nan
        )
        break_even_revenue = (
            fixed_cost / (1 - variable_ratio)
            if variable_ratio < 1 else np.nan
        )

        st.divider()
        st.subheader(f"2. ผลการประเมินโครงการ: {project_name}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Net Present Value (NPV)", f"฿{npv:,.0f}", "คุ้มค่า" if npv > 0 else "ไม่ผ่านเกณฑ์" if npv < 0 else "จุดคุ้มทุน")
        k2.metric("Internal Rate of Return (IRR)", f"{irr_value * 100:.2f}%" if irr_value is not None else "คำนวณไม่ได้")
        k3.metric("Payback Period", f"{payback:.2f} ปี" if payback is not None else "เกินอายุโครงการ")
        k4.metric("Discounted Payback", f"{discounted_payback:.2f} ปี" if discounted_payback is not None else "เกินอายุโครงการ")

        if npv > 0 and irr_value is not None and irr_value > discount:
            st.success("ผลเบื้องต้น: โครงการผ่านเกณฑ์ทางการเงินภายใต้สมมติฐานที่กำหนด")
        elif npv < 0 or (irr_value is not None and irr_value < discount):
            st.warning("ผลเบื้องต้น: โครงการยังไม่ผ่านเกณฑ์ผลตอบแทนทางการเงิน ควรทบทวนรายได้ ต้นทุน หรือเงินลงทุน")
        else:
            st.info("ผลประเมินยังไม่ชัดเจน ควรพิจารณาตัวชี้วัดร่วมกับความเสี่ยงและข้อมูลเชิงธุรกิจ")

        st.caption("แบบจำลองคำนวณภาษีจาก EBIT หลังหักค่าเสื่อมราคา และบวกค่าเสื่อมราคากลับในกระแสเงินสดจากการดำเนินงาน จึงสะท้อน Depreciation Tax Shield เมื่อมีกำไรทางภาษี")
        st.caption("ข้อจำกัด: ใช้ค่าเสื่อมราคาเส้นตรงกับเงินลงทุนสินทรัพย์เริ่มต้นตลอดอายุโครงการ ไม่คิดภาษีจากกำไร/ขาดทุนในการจำหน่ายสินทรัพย์ และไม่คิดค่าเสื่อมของ CapEx เพิ่มเติมโดยอัตโนมัติ ควรปรับให้ตรงกับนโยบายบัญชีและภาษีจริง")
        st.divider()
        st.subheader("3. Projected Cash Flow")
        st.dataframe(forecast_df.style.format({c: "{:,.2f}" for c in forecast_df.columns if c != "Year"}), use_container_width=True, hide_index=True)
        st.line_chart(forecast_df.set_index("Year")[["Revenue", "EBITDA", "Free Cash Flow", "Present Value"]], use_container_width=True)
        st.download_button("📥 Download Feasibility Cash Flow", forecast_df.to_csv(index=False).encode("utf-8-sig"), "Feasibility_Cash_Flow.csv", "text/csv")

        st.divider()
        st.subheader("4. Investment Decision Metrics")
        metrics_df = pd.DataFrame({
            "ตัวชี้วัด": ["Initial Investment incl. NWC", "Annual Depreciation", "NPV", "IRR", "Required Return", "Profitability Index", "Break-even Revenue (Year 1)", "Payback Period", "Discounted Payback Period"],
            "ผลการคำนวณ": [
                f"{total_initial_funding:,.2f} บาท",
                f"{annual_depreciation:,.2f} บาท/ปี",
                f"{npv:,.2f} บาท",
                f"{irr_value * 100:.2f}%" if irr_value is not None else "คำนวณไม่ได้",
                f"{discount_rate:.2f}%",
                f"{profitability_index:.3f}" if np.isfinite(profitability_index) else "คำนวณไม่ได้",
                f"{break_even_revenue:,.2f} บาท" if np.isfinite(break_even_revenue) else "คำนวณไม่ได้",
                f"{payback:.2f} ปี" if payback is not None else "เกินอายุโครงการ",
                f"{discounted_payback:.2f} ปี" if discounted_payback is not None else "เกินอายุโครงการ"
            ]
        })
        st.dataframe(metrics_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("5. NPV Sensitivity Analysis")
        st.write("วิเคราะห์ NPV เมื่ออัตราคิดลดและการเติบโตของรายได้เปลี่ยนแปลงจากสมมติฐานฐาน")
        discount_scenarios = [max(0.001, discount - 0.02), max(0.001, discount - 0.01), discount, discount + 0.01, discount + 0.02]
        growth_scenarios = [growth - 0.02, growth - 0.01, growth, growth + 0.01, growth + 0.02]
        sensitivity_rows = []
        for scenario_discount in discount_scenarios:
            row = {"Discount Rate (%)": scenario_discount * 100}
            for scenario_growth in growth_scenarios:
                scenario_revenue = annual_revenue
                scenario_fixed = fixed_cost
                scenario_cfs = [-initial_investment - initial_nwc]
                scenario_nwc_balance = initial_nwc
                for year in range(1, years + 1):
                    if year > 1:
                        scenario_revenue *= (1 + scenario_growth)
                        scenario_fixed *= (1 + fixed_growth)
                    scenario_ebitda = scenario_revenue * (1 - variable_ratio) - scenario_fixed
                    scenario_ebit = scenario_ebitda - annual_depreciation
                    scenario_tax = max(0.0, scenario_ebit * tax)
                    scenario_ocf = scenario_ebit - scenario_tax + annual_depreciation
                    if year == years:
                        scenario_nwc_change = -scenario_nwc_balance
                        scenario_nwc_balance = 0.0
                    elif year == 1:
                        scenario_nwc_change = 0.0
                    else:
                        target_nwc = scenario_revenue * nwc_ratio
                        scenario_nwc_change = target_nwc - scenario_nwc_balance
                        scenario_nwc_balance = target_nwc
                    scenario_cf = scenario_ocf - annual_capex - scenario_nwc_change
                    if year == years:
                        scenario_cf += salvage_value
                    scenario_cfs.append(scenario_cf)
                scenario_npv = sum(cf / ((1 + scenario_discount) ** year) for year, cf in enumerate(scenario_cfs))
                row[f"{scenario_growth * 100:.1f}%"] = scenario_npv
            sensitivity_rows.append(row)
        sensitivity_df = pd.DataFrame(sensitivity_rows)
        st.dataframe(sensitivity_df.style.format("{:,.0f}"), use_container_width=True, hide_index=True)
        st.download_button("📥 Download NPV Sensitivity", sensitivity_df.to_csv(index=False).encode("utf-8-sig"), "Feasibility_Sensitivity.csv", "text/csv")

        st.divider()
        st.subheader("6. Decision Guidelines")
        st.markdown("""
        - **NPV > 0:** มูลค่าปัจจุบันของผลประโยชน์สูงกว่าเงินลงทุนและต้นทุนเงินทุน
        - **IRR > Required Return:** อัตราผลตอบแทนภายในสูงกว่าอัตราผลตอบแทนขั้นต่ำที่ต้องการ
        - **Payback Period:** ระยะเวลาที่กระแสเงินสดสะสมแบบไม่คิดลดคืนเงินลงทุน
        - **Discounted Payback:** ระยะเวลาคืนทุนเมื่อคิดมูลค่าเงินตามเวลา
        - **Profitability Index > 1:** มูลค่าปัจจุบันของกระแสเงินสดรับต่อเงินลงทุนเริ่มต้นมากกว่า 1
        """)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการประเมินโครงการ: {e}")


# =====================================================
# 8. SIDEBAR NAVIGATION
# =====================================================

st.sidebar.title("💹 Financial Dashboard")

st.sidebar.write(
    "Professional Investment Analysis"
)

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navigation Menu",
    options=MENU_OPTIONS,
    index=0,
    key="main_navigation"
)

st.sidebar.divider()

st.sidebar.caption(
    "Financial Analysis Application"
)

st.sidebar.caption(
    "Version 3.0.0"
)


# =====================================================
# 9. MAIN PAGE ROUTER
# =====================================================

# แสดงผลตามเมนูที่ผู้ใช้เลือก

if menu == MENU_TRADING:

    render_trading_signals()

elif menu == MENU_DCF:

    render_dcf_valuation()

elif menu == MENU_FEASIBILITY:

    render_feasibility_study()

else:

    st.title("⚠️ Navigation Error")

    st.error(
        f"ไม่พบหน้าที่เลือก: {menu}"
    )

    st.write(
        "กรุณาเลือกเมนูจาก Sidebar อีกครั้ง"
    )

    st.write(
        "เมนูที่รองรับ:",
        ", ".join(MENU_OPTIONS)
    )


# =====================================================
# 10. FOOTER
# =====================================================

st.divider()

st.caption(
    "Professional Financial Analysis Dashboard | "
    "Python + Streamlit + Pandas + NumPy"
)
