def calculate_dcf(fcffs, wacc, terminal_growth):

    if wacc <= terminal_growth:
        raise ValueError(
            "WACC ต้องมากกว่า Terminal Growth Rate"
        )

    if wacc <= 0:
        raise ValueError("WACC ต้องมากกว่า 0")

    # Year 6 FCFF
    fcff_year6 = fcffs[-1] * (1 + terminal_growth)

    # Terminal Value
    terminal_value = (
        fcff_year6 / (wacc - terminal_growth)
    )

    # Present Value of Terminal Value
    pv_terminal = (
        terminal_value / ((1 + wacc) ** len(fcffs))
    )

    # Present Value of Forecast FCFF
    pv_forecast = sum(
        fcff / ((1 + wacc) ** year)
        for year, fcff in enumerate(fcffs, start=1)
    )

    # Enterprise Value
    enterprise_value = pv_forecast + pv_terminal

    return (
        fcff_year6,
        terminal_value,
        pv_terminal,
        pv_forecast,
        enterprise_value
    )
