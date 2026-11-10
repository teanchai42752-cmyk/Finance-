
import streamlit as st
import pandas as pd

# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Financial Analysis Dashboard",
    page_icon="💹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# 2. SIDEBAR NAVIGATION
# ==========================================
st.sidebar.title("💹 Financial Dashboard")
st.sidebar.write("Financial Analysis & Investment Tools")

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navigation Menu",
    [
        "Trading Signals",
        "DCF Valuation",
        "Feasibility Study"
    ]
)

st.sidebar.divider()

st.sidebar.caption("Financial Analysis Application")
st.sidebar.caption("Version 1.0.0")


# ==========================================
# 3. MAIN CONTENT
# ==========================================

# ==========================================
# PAGE 1: TRADING SIGNALS
# ==========================================
if menu == "Trading Signals":

    st.title("📈 Trading Signals")

    st.write(
        "ระบบวิเคราะห์สัญญาณการซื้อขาย "
        "เพื่อช่วยประเมินแนวโน้มราคาและหาจังหวะเข้าเทรด"
    )

    st.divider()

    st.subheader("Trading Dashboard")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Asset", "XAU/USD")

    with col2:
        st.metric("Signal", "Waiting")

    with col3:
        st.metric("Market Status", "Monitoring")

    st.info("พื้นที่สำหรับพัฒนาระบบ Trading Signals ในอนาคต")

    st.subheader("Analysis")

    st.write("เตรียมพื้นที่สำหรับ:")
    st.write("- Price Chart")
    st.write("- Technical Indicators")
    st.write("- Buy / Sell Signals")
    st.write("- Entry Price / Stop Loss / Take Profit")


# ==========================================
# PAGE 2: DCF VALUATION
# ==========================================
elif menu == "DCF Valuation":

    st.title("💰 DCF Valuation")

    st.write(
        "ระบบประเมินมูลค่ากิจการด้วยวิธี "
        "Discounted Cash Flow (DCF) "
        "เพื่อคำนวณมูลค่ากิจการจากกระแสเงินสดในอนาคต"
    )

    st.divider()

    st.subheader("📊 DCF Valuation Inputs")

    st.write(
        "กรอกข้อมูลทางการเงินเพื่อใช้ในการประมาณการ "
        "กระแสเงินสดล่วงหน้า 5 ปี"
    )

    # --------------------------------------
    # INPUT SECTION
    # --------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        revenue = st.number_input(
            "รายได้ปัจจุบัน (ล้านบาท)",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            format="%.2f"
        )

        growth_rate = st.number_input(
            "อัตราการเติบโตของรายได้ (Growth Rate %)",
            min_value=-100.0,
            max_value=200.0,
            value=5.0,
            step=0.5
        )

        operating_margin = st.number_input(
            "อัตรากำไรจากการดำเนินงาน (Operating Margin %)",
            min_value=-100.0,
            max_value=100.0,
            value=15.0,
            step=0.5
        )

    with col2:

        wacc = st.number_input(
            "ต้นทุนเงินทุนถัวเฉลี่ยถ่วงน้ำหนัก (WACC %)",
            min_value=0.1,
            max_value=100.0,
            value=10.0,
            step=0.5
        )

        terminal_growth = st.number_input(
            "อัตราการเติบโตระยะยาว (Terminal Growth Rate %)",
            min_value=-10.0,
            max_value=50.0,
            value=3.0,
            step=0.5
        )

    st.divider()

    # --------------------------------------
    # CALCULATE BUTTON
    # --------------------------------------

    if st.button(
        "🧮 Calculate",
        type="primary",
        use_container_width=True
    ):

        # Convert percentage to decimal
        growth = growth_rate / 100
        margin = operating_margin / 100
        discount_rate = wacc / 100
        terminal_rate = terminal_growth / 100

        # Validate WACC and Terminal Growth
        if discount_rate <= terminal_rate:

            st.error(
                "WACC ต้องมากกว่า Terminal Growth Rate "
                "เพื่อให้สามารถคำนวณ Terminal Value ได้"
            )

        else:

            # ----------------------------------
            # DCF FORECAST: 5 YEARS
            # ----------------------------------

            forecast_data = []

            pv_fcf_total = 0

            for year in range(1, 6):

                # Forecast Revenue
                forecast_revenue = (
                    revenue * (1 + growth) ** year
                )

                # Simplified FCF
                fcf = forecast_revenue * margin

                # Discount Factor
                discount_factor = (
                    1 / (1 + discount_rate) ** year
                )

                # Present Value of FCF
                pv_fcf = fcf * discount_factor

                pv_fcf_total += pv_fcf

                forecast_data.append({
                    "Year": f"Year {year}",
                    "Revenue (MB)": forecast_revenue,
                    "Operating Profit / FCF (MB)": fcf,
                    "Discount Factor": discount_factor,
                    "Present Value of FCF (MB)": pv_fcf
                })

            # ----------------------------------
            # TERMINAL VALUE
            # ----------------------------------

            # FCF in Year 6
            fcf_year6 = (
                forecast_data[4]["Operating Profit / FCF (MB)"]
                * (1 + terminal_rate)
            )

            # Gordon Growth Model
            terminal_value = (
                fcf_year6 / (discount_rate - terminal_rate)
            )

            # Present Value of Terminal Value
            pv_terminal_value = (
                terminal_value / (1 + discount_rate) ** 5
            )

            # ----------------------------------
            # ENTERPRISE VALUE
            # ----------------------------------

            enterprise_value = (
                pv_fcf_total + pv_terminal_value
            )

            # ----------------------------------
            # DISPLAY FORECAST TABLE
            # ----------------------------------

            st.success("คำนวณ DCF Valuation สำเร็จ!")

            st.divider()

            st.subheader("📈 5-Year Financial Forecast")

            df = pd.DataFrame(forecast_data)

            st.dataframe(
                df.style.format({
                    "Revenue (MB)": "{:,.2f}",
                    "Operating Profit / FCF (MB)": "{:,.2f}",
                    "Discount Factor": "{:.4f}",
                    "Present Value of FCF (MB)": "{:,.2f}"
                }),
                use_container_width=True,
                hide_index=True
            )

            # ----------------------------------
            # DISPLAY VALUATION RESULTS
            # ----------------------------------

            st.divider()

            st.subheader("💎 DCF Valuation Results")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    label="Enterprise Value",
                    value=f"{enterprise_value:,.2f} MB"
                )

            with col2:
                st.metric(
                    label="PV of Forecast FCF",
                    value=f"{pv_fcf_total:,.2f} MB"
                )

            with col3:
                st.metric(
                    label="PV of Terminal Value",
                    value=f"{pv_terminal_value:,.2f} MB"
                )

            # ----------------------------------
            # VALUATION SUMMARY
            # ----------------------------------

            st.divider()

            st.subheader("📋 Valuation Summary")

            summary_data = {
                "รายการ": [
                    "Present Value of Forecast FCF",
                    "Terminal Value",
                    "Present Value of Terminal Value",
                    "Enterprise Value"
                ],
                "มูลค่า (ล้านบาท)": [
                    pv_fcf_total,
                    terminal_value,
                    pv_terminal_value,
                    enterprise_value
                ]
            }

            summary_df = pd.DataFrame(summary_data)

            st.dataframe(
                summary_df.style.format({
                    "มูลค่า (ล้านบาท)": "{:,.2f}"
                }),
                use_container_width=True,
                hide_index=True
            )

            st.info(
                "หมายเหตุ: โมเดลนี้ใช้ Operating Profit "
                "เป็นตัวแทน FCF แบบอย่างง่าย "
                "โดยยังไม่หักภาษี เงินลงทุนในสินทรัพย์ถาวร "
                "ค่าเสื่อมราคา และเงินทุนหมุนเวียน"
            )


# ==========================================
# PAGE 3: FEASIBILITY STUDY
# ==========================================
elif menu == "Feasibility Study":

    st.title("📊 Feasibility Study")

    st.write(
        "ระบบวิเคราะห์ความเป็นไปได้ของโครงการลงทุน "
        "เพื่อประเมินผลตอบแทน ต้นทุน และความคุ้มค่าทางการเงิน"
    )

    st.divider()

    st.subheader("Project Analysis Dashboard")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("NPV", "N/A")

    with col2:
        st.metric("IRR", "N/A")

    with col3:
        st.metric("Payback Period", "N/A")

    st.info("พื้นที่สำหรับพัฒนาระบบ Feasibility Study ในอนาคต")

    st.subheader("Project Financial Analysis")

    st.write("เตรียมพื้นที่สำหรับ:")
    st.write("- Initial Investment")
    st.write("- Revenue Projection")
    st.write("- Operating Costs")
    st.write("- Net Present Value (NPV)")
    st.write("- Internal Rate of Return (IRR)")
    st.write("- Payback Period")


# ==========================================
# 4. FOOTER
# ==========================================
st.divider()

st.caption(
    "Financial Analysis Dashboard | "
    "Powered by Python & Streamlit"
)
