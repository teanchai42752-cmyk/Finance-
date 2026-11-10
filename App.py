
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

    st.write(
        "ระบบวิเคราะห์สัญญาณการซื้อขาย "
        "เพื่อช่วยประเมินแนวโน้มราคาและจังหวะเข้าเทรด"
    )

    st.divider()

    st.subheader("Trading Dashboard")

    col1, col2, col3 = st.columns(3)

    col1.metric("Asset", "XAU/USD")
    col2.metric("Signal", "Waiting")
    col3.metric("Market Status", "Monitoring")

    st.info(
        "พื้นที่สำหรับพัฒนาระบบ Trading Signals"
    )

    st.subheader("Technical Analysis")

    st.write("- Price Chart")
    st.write("- Technical Indicators")
    st.write("- Buy / Sell Signals")
    st.write("- Entry Price / Stop Loss / Take Profit")


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

    st.write(
        "ระบบวิเคราะห์ความเป็นไปได้ของโครงการลงทุน "
        "เพื่อประเมินผลตอบแทน ต้นทุน และความคุ้มค่าทางการเงิน"
    )

    st.divider()

    st.subheader(
        "Project Analysis Dashboard"
    )

    col1, col2, col3 = st.columns(3)

    col1.metric("NPV", "N/A")
    col2.metric("IRR", "N/A")
    col3.metric("Payback Period", "N/A")

    st.info(
        "พื้นที่สำหรับพัฒนาระบบ Feasibility Study"
    )

    st.subheader(
        "Project Financial Analysis"
    )

    st.write("- Initial Investment")
    st.write("- Revenue Projection")
    st.write("- Operating Costs")
    st.write("- Net Present Value (NPV)")
    st.write("- Internal Rate of Return (IRR)")
    st.write("- Payback Period")


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
