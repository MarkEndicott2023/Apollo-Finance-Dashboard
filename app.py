"""Apollo Cooperative — Finance Dashboard.

Reads the centralized budget/reconciliation workbook at
artifacts/budget_recon_centralized.xlsx and renders charts that help
Apollo members see the house's financial health over time.

Run with:  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

WORKBOOK = "budget_recon_centralized.xlsx"

st.set_page_config(
    page_title="Apollo Finance Dashboard",
    page_icon=":moneybag:",
    layout="wide",
)


@st.cache_data(show_spinner="Loading workbook…")
def load_data(path: Path) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None)
    return sheets


def monthly_net(ledger: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Return one row per year_month with income, expense, and net totals.

    Income = sum of credit on rows where section == 'income'.
    Expense = sum of debit on rows where section == 'expense'.
    Net = income - expense (positive = surplus, negative = deficit).
    """
    income = (
        ledger.loc[ledger["section"] == "income"]
        .groupby("year_month", dropna=False)["credit"]
        .sum(min_count=1)
        .rename("income")
    )
    expense = (
        ledger.loc[ledger["section"] == "expense"]
        .groupby("year_month", dropna=False)["debit"]
        .sum(min_count=1)
        .rename("expense")
    )
    df = (
        periods[["year_month", "fiscal_year", "semester", "month_name"]]
        .merge(income, on="year_month", how="left")
        .merge(expense, on="year_month", how="left")
    )
    df[["income", "expense"]] = df[["income", "expense"]].fillna(0.0)
    df["net"] = df["income"] - df["expense"]
    df = df.sort_values("year_month").reset_index(drop=True)
    # Split net into surplus/deficit columns so the bar chart can color them
    # separately (positive bars green, negative bars red).
    df["Surplus"] = df["net"].clip(lower=0)
    df["Deficit"] = df["net"].clip(upper=0)
    # Running total from the first month forward — answers "how far ahead
    # or behind has Apollo accumulated over time?"
    df["cumulative_net"] = df["net"].cumsum()
    return df


def render_kpis(view: pd.DataFrame) -> None:
    """Top-of-page metric tiles summarizing the filtered view."""
    total_income = view["income"].sum()
    total_expense = view["expense"].sum()
    total_net = view["net"].sum()
    months_in_surplus = int((view["net"] > 0).sum())
    months_in_deficit = int((view["net"] < 0).sum())

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total income", f"${total_income:,.0f}")
    k2.metric("Total expenses", f"${total_expense:,.0f}")
    k3.metric(
        "Net (surplus − deficit)",
        f"${total_net:,.0f}",
        delta=f"{months_in_surplus} surplus / {months_in_deficit} deficit months",
        delta_color="normal" if total_net >= 0 else "inverse",
    )
    k4.metric("Months in view", f"{len(view)}")


def render_monthly_surplus_deficit(view: pd.DataFrame) -> None:
    """Bar chart: one bar per month, green above zero / red below."""
    st.subheader("Monthly surplus / deficit")
    st.caption(
        "Each bar is one month. Green bars rise above zero (income > expenses); "
        "red bars drop below zero (expenses > income)."
    )

    chart_df = (
        view.sort_values("year_month")
        .set_index("year_month")[["Surplus", "Deficit"]]
    )
    st.bar_chart(chart_df, color=["#2e7d32", "#c62828"], height=420)


def render_cumulative_net(view: pd.DataFrame) -> None:
    """Line chart: running total of monthly net over time."""
    st.subheader("Cumulative net position over time")
    ending = view.sort_values("year_month")["cumulative_net"].iloc[-1]
    starting = view.sort_values("year_month")["cumulative_net"].iloc[0] - view.sort_values("year_month")["net"].iloc[0]
    st.caption(
        "Running total of monthly net (surplus minus deficit), starting from "
        f"September 2021. Line above zero = Apollo is ahead overall; below zero = behind. "
        f"In the current view the line moves from **${starting:,.0f}** to **${ending:,.0f}** "
        f"(change of **${ending - starting:+,.0f}**)."
    )

    cum_df = (
        view.sort_values("year_month")
        .set_index("year_month")[["cumulative_net"]]
        .rename(columns={"cumulative_net": "Cumulative net"})
    )
    st.line_chart(cum_df, color="#1565c0", height=360)


def render_account_balances(house_summary: pd.DataFrame, years: list[int]) -> None:
    """Line chart: end-of-month balance for every Apollo bank account."""
    st.subheader("Bank-account balances over time")
    bal_view = (
        house_summary.loc[house_summary["fiscal_year"].isin(years)]
        .sort_values("year_month")
        .copy()
    )
    account_cols = {
        "checking_end": "Checking",
        "savings_end": "Savings",
        "reserve_end": "Reserve",
        "other_end": "Other",
    }
    last_row = bal_view.iloc[-1]
    last_parts = [
        f"{label} ${last_row[col]:,.0f}" for col, label in account_cols.items()
        if pd.notna(last_row[col])
    ]
    last_total = sum(
        last_row[col] for col in account_cols if pd.notna(last_row[col])
    )
    st.caption(
        "End-of-month balance for every Apollo bank account, overlapped. "
        f"At {last_row['year_month']}: {' · '.join(last_parts)} "
        f"(**total ${last_total:,.0f}**). "
        "Savings, Reserve, and Other accounts only appear in the source "
        "records starting September 2022 — the gaps before that are not "
        "zeroed-out balances, they're months that pre-date the tracking."
    )

    bal_df = (
        bal_view.set_index("year_month")[list(account_cols.keys())]
        .rename(columns=account_cols)
    )
    st.line_chart(
        bal_df,
        color=["#6a1b9a", "#2e7d32", "#1565c0", "#ef6c00"],
        height=380,
    )


def render_monthly_table(view: pd.DataFrame) -> None:
    """Collapsible table with the per-month numbers behind the charts."""
    with st.expander("Show monthly numbers"):
        table = view[
            ["year_month", "fiscal_year", "semester", "month_name", "income", "expense", "net", "cumulative_net"]
        ].sort_values("year_month")
        st.dataframe(
            table,
            hide_index=True,
            use_container_width=True,
            column_config={
                "year_month": st.column_config.TextColumn(label="Month (YYYY-MM)"),
                "fiscal_year": st.column_config.NumberColumn(label="Fiscal year", format="%d"),
                "semester": st.column_config.TextColumn(label="Semester"),
                "month_name": st.column_config.TextColumn(label="Month name"),
                "income": st.column_config.NumberColumn(label="Income", format="$%.2f"),
                "expense": st.column_config.NumberColumn(label="Expenses", format="$%.2f"),
                "net": st.column_config.NumberColumn(
                    label="Net (income − expenses)", format="$%.2f"
                ),
                "cumulative_net": st.column_config.NumberColumn(
                    label="Cumulative net (running total)", format="$%.2f"
                ),
            },
        )


def main() -> None:

    data = load_data(WORKBOOK)
    ledger = data["ledger_entries"]
    periods = data["periods"]
    house_summary = data["monthly_house_summary"]

    monthly = monthly_net(ledger, periods)

    st.title("Apollo Finance Dashboard")
    st.caption(f"Source: `{WORKBOOK}` · {len(ledger):,} ledger entries")

    # ---- Sidebar filters ----
    with st.sidebar:
        st.header("Filters")
        all_years = sorted(int(y) for y in monthly["fiscal_year"].dropna().unique())
        years = st.multiselect(
            "Fiscal year",
            options=all_years,
            default=all_years,
            help="Apollo's fiscal year runs Sept–Aug; FY2022 = Sept 2021 → Aug 2022.",
        )

    if not years:
        st.info("Select at least one fiscal year in the sidebar.")
        st.stop()

    view = monthly.loc[monthly["fiscal_year"].isin(years)].copy()

    render_kpis(view)
    st.divider()
    render_monthly_surplus_deficit(view)
    st.divider()
    render_cumulative_net(view)
    st.divider()
    render_account_balances(house_summary, years)
    render_monthly_table(view)


if __name__ == "__main__":
    main()
