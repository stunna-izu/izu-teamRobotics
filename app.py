import json
import math
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Career Venture Lab | ROB-2 Precalculus Studio",
    layout="wide",
)


def fmt_usd(val: Decimal) -> str:
    return f"${val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def init_state() -> dict:
    """Initialize default ROB-2 (Precalculus - Advanced) state from Student Handbook."""
    return {
        "team_id": "TEAM-ROB",
        "course": "Precalculus",
        "pathway_id": "ROB-2",
        "selected_level": "Advanced",
        "snapshot_id": "SNAP-001",
        "state_version": 1,
        "simulation_date": "2027-01-31",
        "random_seed": 2027,
        "currency": "USD",
        # ROB-2 Exact Inputs (Handbook p. 78)
        "base_price": "120.00",
        "D0": 40,
        "staff_hours": 90.0,
        "hours_per_unit": 3.0,
        "opening_cash": "5000.00",
        "opening_stock_units": 100,
        "current_stock_units": 100,
        "component_unit_cost": "30.00",
        "restock_units": 0,
        "defect_rate": 0.0,
        # Editable Cost Rows (Handbook p. 78)
        "var_lines": {
            "components_COGS": "30.00",
            "assembly_labor": "20.00",
            "packaging": "10.00",
            "warranty_consumables": "5.00",
        },
        "fixed_lines": {
            "workspace": "250.00",
            "software": "100.00",
            "equipment_maintenance": "150.00",
            "admin": "100.00",
        },
        # Startup Financing & Opening Balances (Handbook p. 78)
        "owner_equity": "12000.00",
        "equipment_assets": "4000.00",
        "pre_opening_expense": "0.00",
        "opening_inventory_value": "3000.00",
        "opening_retained_earnings": "0.00",
        "opening_debt": "0.00",
        # Persistent Records
        "processed_run_ids": [],
        "ledger": [],
        "period_summaries": [],
        "campaigns": [],
        "recommendations": [],
        "decisions": [],
    }


if "biz_state" not in st.session_state:
    st.session_state.biz_state = init_state()

state = st.session_state.biz_state


def compute_variable_per_unit(s: dict) -> Decimal:
    return sum(Decimal(str(v)) for v in s["var_lines"].values())


def compute_fixed_monthly(s: dict) -> Decimal:
    return sum(Decimal(str(v)) for v in s["fixed_lines"].values())


def derive_capacity(s: dict) -> int:
    if s["hours_per_unit"] <= 0:
        return 0
    return math.floor(s["staff_hours"] / s["hours_per_unit"])


def step_simulation_month(
    s: dict,
    run_id: str,
    sim_date: str,
    requested: int,
    restock_units: int = 0,
    ad_cost: Decimal = Decimal("0.00"),
    capacity_override: int | None = None,
    refund_amount: Decimal = Decimal("0.00"),
    loan_proceeds: Decimal = Decimal("0.00"),
    loan_principal: Decimal = Decimal("0.00"),
    interest_exp: Decimal = Decimal("0.00"),
    additional_capex: Decimal = Decimal("0.00"),
    new_owner_cash: Decimal = Decimal("0.00"),
) -> tuple[bool, str]:
    """
    Deterministic ROB monthly algorithm (Handbook p. 79):
    capacity = floor(staff_hours / hours_per_unit) [unless fixture capacity_override]
    attempted = min(requested, capacity, current_stock_units + restock_units)
    failed = floor(attempted * defect_rate)
    sold = attempted - failed
    Consume components and noncomponent costs for every attempted kit.
    """
    if run_id in s["processed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected: no duplicate transactions created."

    if requested < 0 or restock_units < 0:
        return False, "Validation error: requested units and restock units must be nonnegative."

    cap = capacity_override if capacity_override is not None else derive_capacity(s)
    available_stock = s["current_stock_units"] + restock_units
    attempted = min(requested, cap, available_stock)
    failed = math.floor(attempted * float(s["defect_rate"]))
    sold = attempted - failed
    lost_demand = max(0, requested - attempted)

    price = Decimal(str(s["base_price"]))
    comp_cost_unit = Decimal(str(s["var_lines"]["components_COGS"]))
    noncomp_cost_unit = compute_variable_per_unit(s) - comp_cost_unit
    fixed_cost = compute_fixed_monthly(s)

    revenue = (price * Decimal(sold)).quantize(Decimal("0.01"))
    comp_consumed_exp = (comp_cost_unit * Decimal(attempted)).quantize(Decimal("0.01"))
    noncomp_var_exp = (noncomp_cost_unit * Decimal(attempted)).quantize(Decimal("0.01"))
    restock_cash_out = (Decimal(str(s["component_unit_cost"])) * Decimal(restock_units)).quantize(Decimal("0.01"))

    ver = s["state_version"]

    def add_txn(event_type: str, category: str, amount: Decimal, qty: int, unit_p: Decimal, fin_type: str = "none"):
        if amount == Decimal("0.00") and category != "fixed_expense":
            return
        s["ledger"].append({
            "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "run_id": run_id,
            "date": sim_date,
            "event_type": event_type,
            "category": category,
            "amount": str(amount),
            "quantity": qty,
            "unit_price": str(unit_p),
            "offering_id": "Introductory robot kit",
            "campaign_id": "NONE",
            "financing_type": fin_type,
            "state_version": ver,
        })

    add_txn("revenue", "sales_revenue", revenue, sold, price)
    add_txn("contra_revenue", "refund", refund_amount, 0, Decimal("0.00"))
    add_txn("expense", "components_consumed", comp_consumed_exp, attempted, comp_cost_unit)
    add_txn("expense", "noncomponent_variable", noncomp_var_exp, attempted, noncomp_cost_unit)
    add_txn("expense", "fixed_expense", fixed_cost, 1, fixed_cost)
    add_txn("expense", "own_marketing", ad_cost, 1, ad_cost)
    add_txn("inventory_purchase", "inventory_restock", restock_cash_out, restock_units, Decimal(str(s["component_unit_cost"])))
    add_txn("investing", "capex", additional_capex, 1, additional_capex)
    add_txn("financing", "loan_proceeds", loan_proceeds, 0, Decimal("0.00"), "loan")
    add_txn("financing", "loan_principal", loan_principal, 0, Decimal("0.00"), "loan")
    add_txn("expense", "interest", interest_exp, 0, Decimal("0.00"), "loan")
    add_txn("financing", "owner_contribution", new_owner_cash, 0, Decimal("0.00"), "equity")

    s["current_stock_units"] = available_stock - attempted
    s["processed_run_ids"].append(run_id)
    s["state_version"] += 1
    s["snapshot_id"] = f"SNAP-{s['state_version']:03d}"
    s["simulation_date"] = sim_date

    total_exp = comp_consumed_exp + noncomp_var_exp + fixed_cost + ad_cost + interest_exp
    op_profit = (revenue - refund_amount) - total_exp

    s["period_summaries"].append({
        "run_id": run_id,
        "date": sim_date,
        "mode": "FIXTURE_OVERRIDE" if capacity_override is not None else "NORMAL_DERIVED",
        "requested": requested,
        "capacity": cap,
        "attempted": attempted,
        "failed_builds": failed,
        "sold": sold,
        "lost_demand": lost_demand,
        "ending_stock_units": s["current_stock_units"],
        "revenue": str(revenue),
        "total_expense": str(total_exp),
        "profit": str(op_profit),
    })
    return True, f"Recorded run '{run_id}': Attempted={attempted}, Failed={failed}, Sold={sold}, Profit={fmt_usd(op_profit)}."


# ==============================================================================
# SIDEBAR: PERSISTENT STATE, SAVE/LOAD JSON, FIXTURE REPLAY & RESET
# ==============================================================================
with st.sidebar:
    st.title("Career Venture Lab")
    st.caption("Pathway: **ROB-2** | Course: **Precalculus** | Level: **Advanced**")
    st.write(f"**Team ID:** `{state['team_id']}` | **Version:** `v{state['state_version']}`")
    st.write(f"**Snapshot:** `{state['snapshot_id']}` | **Stock:** `{state['current_stock_units']} sets`")

    st.divider()
    st.subheader("Save / Restore State (JSON)")
    st.download_button(
        label="Download State JSON",
        data=json.dumps(state, indent=2),
        file_name=f"{state['team_id']}_ROB2_v{state['state_version']}.json",
        mime="application/json",
    )

    uploaded_json = st.file_uploader("Restore Saved State JSON", type=["json"])
    if uploaded_json is not None:
        if st.button("Load Uploaded JSON"):
            try:
                loaded = json.load(uploaded_json)
                if loaded.get("pathway_id") != "ROB-2":
                    st.error(f"Rejected: Expected pathway ROB-2, got '{loaded.get('pathway_id')}'.")
                elif loaded.get("team_id") != state["team_id"]:
                    st.error(f"Rejected: Team ID mismatch ('{loaded.get('team_id')}' vs '{state['team_id']}').")
                else:
                    st.session_state.biz_state = loaded
                    st.success("State restored cleanly!")
                    st.rerun()
            except Exception as exc:
                st.error(f"Invalid state file: {exc}")

    st.divider()
    st.subheader("ROB Fixture Acceptance Replay")
    st.caption("Replays handbook monthly_fixture.csv (Jan-Mar 2027) from clean opening balances.")
    if st.button("Reset & Run 3-Month ROB Fixture"):
        fresh = init_state()
        fresh["team_id"] = state["team_id"]
        fixture_rows = [
            ("FIX-2027-01", "2027-01-31", 40, 30, Decimal("0.00")),
            ("FIX-2027-02", "2027-02-28", 44, 30, Decimal("100.00")),
            ("FIX-2027-03", "2027-03-31", 36, 22, Decimal("0.00")),
        ]
        for r_id, dt, req, cap_ov, ad in fixture_rows:
            step_simulation_month(fresh, r_id, dt, req, restock_units=0, ad_cost=ad, capacity_override=cap_ov)
        st.session_state.biz_state = fresh
        st.success("ROB 3-Month Fixture executed!")
        st.rerun()

    if st.button("Reset to Clean Opening State"):
        tid = state["team_id"]
        st.session_state.biz_state = init_state()
        st.session_state.biz_state["team_id"] = tid
        st.rerun()


# ==============================================================================
# MAIN TABS: STAGE 1 (CORE + MATH) & STAGE 2 (REPORTS + MARKETING + AI WORKFLOW)
# ==============================================================================
tab_overview, tab_inputs, tab_math, tab_reports, tab_marketing, tab_ai = st.tabs([
    "Overview & Ledger",
    "Inputs & Step Engine",
    "Math Skills (Precalculus)",
    "Report Center",
    "Marketing Studio",
    "AI Departmental Workflow",
])

with tab_overview:
    st.header("Robotics Kit and Repair Studio (ROB-2)")
    st.info(
        "Simulation Only: Fictional educational business, customers, and funding. "
        "Normal mode derives capacity from staff hours; fixture mode uses explicit capacity overrides for testing."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Derived Monthly Capacity", f"{derive_capacity(state)} kits")
    c2.metric("Component Stock on Hand", f"{state['current_stock_units']} sets")
    c3.metric("Unit Variable Cost", fmt_usd(compute_variable_per_unit(state)))
    c4.metric("Monthly Fixed Cost", fmt_usd(compute_fixed_monthly(state)))

    st.subheader("Period Execution History")
    if state["period_summaries"]:
        st.dataframe(pd.DataFrame(state["period_summaries"]), use_container_width=True)
    else:
        st.caption("No months simulated yet. Use 'Inputs & Step Engine' or 'Reset & Run 3-Month ROB Fixture' in the sidebar.")

    st.subheader("Immutable Dated Event Ledger")
    if state["ledger"]:
        st.dataframe(pd.DataFrame(state["ledger"]), use_container_width=True)
    else:
        st.caption("Ledger is currently empty.")

with tab_inputs:
    st.header("Business Parameters & Monthly Simulation Step")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Operating & Pricing Parameters")
        state["team_id"] = st.text_input("Team ID", value=state["team_id"])
        state["base_price"] = str(st.number_input("Base Kit Price ($/unit)", min_value=1.0, value=float(state["base_price"]), step=5.0))
        state["D0"] = st.number_input("Baseline Monthly Demand D0 (kits)", min_value=0, value=int(state["D0"]), step=1)
        state["staff_hours"] = st.number_input("Productive Staff Hours / Month", min_value=0.0, value=float(state["staff_hours"]), step=3.0)
        state["hours_per_unit"] = st.number_input("Assembly Hours / Kit", min_value=0.1, value=float(state["hours_per_unit"]), step=0.5)
        state["defect_rate"] = st.slider("Build Defect Rate [0..1]", min_value=0.0, max_value=1.0, value=float(state["defect_rate"]), step=0.01)

    with col2:
        st.subheader("Editable Unit & Fixed Cost Lines")
        for k, v in state["var_lines"].items():
            state["var_lines"][k] = str(st.number_input(f"Variable: {k} ($/attempted unit)", min_value=0.0, value=float(v), step=1.0))
        for k, v in state["fixed_lines"].items():
            state["fixed_lines"][k] = str(st.number_input(f"Fixed: {k} ($/month)", min_value=0.0, value=float(v), step=10.0))

    st.divider()
    st.subheader("Advance Simulation by One Period (Approved Transaction)")
    with st.form("advance_step_form"):
        f1, f2, f3, f4 = st.columns(4)
        run_id_in = f1.text_input("Unique Run ID", value=f"RUN-{state['state_version']:03d}")
        date_in = f2.text_input("Period End Date (YYYY-MM-DD)", value="2027-01-31")
        req_in = f3.number_input("Requested Kits", min_value=0, value=int(state["D0"]), step=1)
        restock_in = f4.number_input("Restock Component Sets (Cash Outflow)", min_value=0, value=0, step=5)

        g1, g2, g3, g4 = st.columns(4)
        loan_in = g1.number_input("Loan Proceeds ($)", min_value=0.0, value=0.0, step=100.0)
        prin_in = g2.number_input("Loan Principal Repaid ($)", min_value=0.0, value=0.0, step=50.0)
        int_in = g3.number_input("Interest Expense ($)", min_value=0.0, value=0.0, step=10.0)
        capex_in = g4.number_input("Additional Equipment Capex ($)", min_value=0.0, value=0.0, step=100.0)

        submitted = st.form_submit_button("Approve & Advance Simulation Step")
        if submitted:
            ok, msg = step_simulation_month(
                state,
                run_id=run_id_in.strip(),
                sim_date=date_in.strip(),
                requested=int(req_in),
                restock_units=int(restock_in),
                loan_proceeds=Decimal(str(loan_in)),
                loan_principal=Decimal(str(prin_in)),
                interest_exp=Decimal(str(int_in)),
                additional_capex=Decimal(str(capex_in)),
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

with tab_math:
    st.header("Math Skills & Challenge Level Panel — Precalculus (Advanced)")
    p0 = float(state["base_price"])
    d0 = float(state["D0"])
    v_unit = float(compute_variable_per_unit(state))
    f_month = float(compute_fixed_monthly(state))
    cap = derive_capacity(state)

    st.markdown(
        f"""
        - **Course & Level:** Precalculus (`ROB-2`) — **Advanced**
        - **Foundation Rational Function:** $A(s) = \frac{{{f_month:.0f}}}{{s}} + {v_unit:.0f}$ for $0 < s \le {cap}$ (Vertical asymptote at $s=0$ where $A(0)$ is undefined; horizontal asymptote $y = {v_unit:.0f}$).
        - **Applied Composition:** $q(p) = \max(0, {2*d0:.0f} - {d0/p0:.5f}p)$, $s(p) = \min({cap}, q(p))$, $R(p) = p\cdot s(p)$, $C(s(p)) = {f_month:.0f} + {v_unit:.0f}s(p)$ on $0 \le p \le {2*p0:.0f}$.
        - **Advanced Seasonal Trigonometric Model (Assumed):** $D(t) = {d0:.0f}\left(1 + 0.20\sin\left(\frac{{2\pi(t-1)}}{{12}}\right)\right)$, period $12$ months, peak at $t=4$ ($1.20 D_0 = {1.2*d0:.1f}$), trough at $t=10$ ($0.80 D_0 = {0.8*d0:.1f}$), clipped at capacity ${cap}$.
        """
    )

    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.subheader("1. Rational Average Cost Curve A(s)")
        s_vals = np.linspace(1, max(1, cap), 100)
        a_vals = f_month / s_vals + v_unit
        fig_ac = go.Figure()
        fig_ac.add_trace(go.Scatter(x=s_vals, y=a_vals, name="A(s) = F/s + v", line=dict(width=3)))
        fig_ac.add_hline(y=v_unit, line_dash="dash", annotation_text=f"Horizontal Asymptote y = ${v_unit:.2f}")
        fig_ac.add_vline(x=0, line_dash="dot", annotation_text="Vertical Asymptote s = 0 (Undefined)")
        fig_ac.update_layout(xaxis_title="Completed Kits (s)", yaxis_title="Average Cost ($/kit)")
        st.plotly_chart(fig_ac, use_container_width=True)

    with m_col2:
        st.subheader("2. Seasonal Demand vs. Capacity Clipping D(t)")
        t_vals = np.arange(1, 13)
        raw_d = d0 * (1.0 + 0.20 * np.sin(2.0 * np.pi * (t_vals - 1) / 12.0))
        clipped_s = np.minimum(cap, np.floor(raw_d))
        fig_seas = go.Figure()
        fig_seas.add_trace(go.Scatter(x=t_vals, y=raw_d, name="Unclipped Seasonal Demand D(t)", mode="lines+markers"))
        fig_seas.add_trace(go.Bar(x=t_vals, y=clipped_s, name="Realized Integer Sales min(cap, floor(D(t)))", opacity=0.6))
        fig_seas.add_hline(y=cap, line_dash="dash", annotation_text=f"Capacity Limit ({cap} kits)")
        fig_seas.update_layout(xaxis_title="Month Index t (1..12)", yaxis_title="Robotics Kits")
        st.plotly_chart(fig_seas, use_container_width=True)

    breakpoint_p = p0 * (2.0 - cap / d0) if d0 > 0 else 0.0
    st.info(
        f"**Capacity Breakpoint Check:** $p = p_0(2 - \text{{cap}}/D_0) = {breakpoint_p:.2f}$. "
        f"At $s = {cap}$, $A({cap}) = {fmt_usd(Decimal(str(f_month / cap + v_unit))) if cap > 0 else 'Undefined'}$."
    )

with tab_reports:
    st.header("Report Center (ROB-2 | Precalculus - Advanced)")
    st.caption(
        f"Team: {state['team_id']} | Snapshot: {state['snapshot_id']} | Version: v{state['state_version']} | "
        "Read-only reconciliation from approved ledger."
    )
    if not state["ledger"]:
        st.info("No ledger transactions recorded yet. Run a step or replay the ROB fixture in the sidebar.")
    else:
        rev = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "sales_revenue")
        refunds = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "refund")
        net_sales = rev - refunds
        comp_cogs = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "components_consumed")
        noncomp_var = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "noncomponent_variable")
        fixed_exp = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "fixed_expense")
        own_mkt = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "own_marketing")
        interest_exp = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "interest")
        net_profit = net_sales - comp_cogs - noncomp_var - fixed_exp - own_mkt - interest_exp

        opening_cash = Decimal(str(state["opening_cash"]))
        restock_cash = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "inventory_restock")
        capex_cash = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "capex")
        loan_in = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "loan_proceeds")
        prin_out = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "loan_principal")
        owner_in = sum(Decimal(r["amount"]) for r in state["ledger"] if r["category"] == "owner_contribution")
        closing_cash = opening_cash + net_sales - noncomp_var - fixed_exp - own_mkt - interest_exp - restock_cash - capex_cash + loan_in + owner_in - prin_out

        ending_inv_val = Decimal(str(state["opening_inventory_value"])) + restock_cash - comp_cogs
        equipment_val = Decimal(str(state["equipment_assets"])) + capex_cash
        total_assets = closing_cash + ending_inv_val + equipment_val
        total_liab_eq = (Decimal(str(state["opening_debt"])) + loan_in - prin_out) + (Decimal(str(state["owner_equity"])) + owner_in) + (Decimal(str(state["opening_retained_earnings"])) + net_profit)

        r1, r2, r3 = st.columns(3)
        r1.metric("Cumulative Net Profit", fmt_usd(net_profit))
        r2.metric("Closing Spendable Cash", fmt_usd(closing_cash))
        r3.metric("Ending Inventory Value", fmt_usd(ending_inv_val))

        if closing_cash < Decimal("1000.00"):
            st.error("FINANCE ALERT: Cash balance is below the $1,000.00 ROB threshold!")

        bs_df = pd.DataFrame([
            {"Account": "Cash", "Balance": fmt_usd(closing_cash)},
            {"Account": "Component Inventory", "Balance": fmt_usd(ending_inv_val)},
            {"Account": "Equipment Assets", "Balance": fmt_usd(equipment_val)},
            {"Account": "TOTAL ASSETS", "Balance": fmt_usd(total_assets)},
            {"Account": "TOTAL LIABILITIES + EQUITY", "Balance": fmt_usd(total_liab_eq)},
        ])
        st.table(bs_df)

        st.download_button(
            "Export Ledger CSV",
            data=pd.DataFrame(state["ledger"]).to_csv(index=False),
            file_name=f"{state['team_id']}_ROB2_v{state['state_version']}_ledger.csv",
            mime="text/csv",
        )

with tab_marketing:
    st.header("Costed Marketing Studio")
    st.caption("Drafting is free; launching records one itemized expense per unique campaign_id.")
    c_id = st.text_input("Campaign ID", value=f"CAMP-{len(state['campaigns']) + 1:03d}")
    offering = st.selectbox("Offering", ["Introductory robot kit", "Sensor upgrade", "Repair service"])
    c_col1, c_col2 = st.columns(2)
    with c_col1:
        d_hrs = st.number_input("Design Hours", min_value=0.0, value=2.0, step=0.5)
        d_rate = st.number_input("Hourly Rate ($)", min_value=0.0, value=15.0, step=1.0)
        in_kind = st.checkbox("In-kind student labor (excluded from cash expense)", value=False)
        assets_c = st.number_input("Licensed Assets ($)", min_value=0.0, value=10.0, step=5.0)
    with c_col2:
        p_qty = st.number_input("Print Quantity", min_value=0, value=100, step=10)
        p_unit = st.number_input("Print Unit Cost ($)", min_value=0.0, value=0.25, step=0.05)
        dist_c = st.number_input("Distribution ($)", min_value=0.0, value=15.0, step=5.0)
        place_c = st.number_input("Placement ($)", min_value=0.0, value=20.0, step=5.0)

    conversions = st.number_input("Attributed Conversions (for CAC check)", min_value=0, value=0, step=1)
    cash_labor = Decimal("0.00") if in_kind else Decimal(str(d_hrs)) * Decimal(str(d_rate))
    camp_cost = (cash_labor + Decimal(str(assets_c)) + Decimal(str(p_qty)) * Decimal(str(p_unit)) + Decimal(str(dist_c)) + Decimal(str(place_c))).quantize(Decimal("0.01"))
    cac_str = fmt_usd(camp_cost / Decimal(conversions)) if conversions > 0 else "N/A (Zero Conversions)"

    st.write(f"**Campaign Cash Cost:** {fmt_usd(camp_cost)} | **Customer Acquisition Cost (CAC):** {cac_str}")
    approved_gate = st.checkbox("Student fact-check & independent reviewer approval completed")

    if st.button("Launch Campaign Once"):
        if not approved_gate:
            st.error("Blocked: Student fact-check and reviewer approval required.")
        elif any(c["campaign_id"] == c_id for c in state["campaigns"]):
            st.error(f"Duplicate Rejected: '{c_id}' was already launched.")
        else:
            state["campaigns"].append({"campaign_id": c_id, "offering": offering, "cost": str(camp_cost), "cac": cac_str})
            state["ledger"].append({
                "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
                "run_id": c_id,
                "date": state["simulation_date"],
                "event_type": "expense",
                "category": "own_marketing",
                "amount": str(camp_cost),
                "quantity": 1,
                "unit_price": str(camp_cost),
                "offering_id": offering,
                "campaign_id": c_id,
                "financing_type": "none",
                "state_version": state["state_version"],
            })
            st.success(f"Launched {c_id} and recorded {fmt_usd(camp_cost)} once.")

with tab_ai:
    st.header("AI Departmental Workflow (Manual JSON Handoff)")
    st.caption("Export current snapshot -> Run in approved Gem/Skill/Chat -> Import & verify proposal -> Approve.")
    st.download_button(
        "Export Snapshot JSON for AI Roles",
        data=json.dumps(state, indent=2),
        file_name=f"{state['team_id']}_ROB2_v{state['state_version']}_snapshot.json",
        mime="application/json",
    )
    rec_raw = st.text_area("Paste AI Recommendation JSON", height=140)
    checker = st.text_input("Independent Student Checker")
    if st.button("Import & Validate Recommendation"):
        try:
            rec = json.loads(rec_raw)
            if rec.get("team_id") != state["team_id"]:
                st.error("Rejected: Team ID mismatch.")
            elif rec.get("state_version") != state["state_version"]:
                st.error(f"Rejected Stale Version: Proposal v{rec.get('state_version')} != Active v{state['state_version']}.")
            elif not checker.strip():
                st.error("Rejected: Enter an independent student checker name.")
            else:
                rec["approval_status"] = "pending"
                rec["checker"] = checker.strip()
                state["recommendations"].append(rec)
                st.success("Proposal queued with approval_status='pending'.")
        except Exception as exc:
            st.error(f"Invalid JSON: {exc}")

    for i, r in enumerate(state["recommendations"]):
        with st.container(border=True):
            st.write(f"**{r.get('role', 'Assistant')}** (v{r.get('state_version')}) — Status: `{r.get('approval_status')}` | Checker: {r.get('checker')}")
            st.write(r.get("recommendation", ""))
            if r.get("approval_status") == "pending":
                if st.button("Approve Recommendation", key=f"appr_{i}"):
                    r["approval_status"] = "approved"
                    st.rerun()
