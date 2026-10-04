from pydantic import BaseModel
from typing import Optional
from decimal import Decimal


class DashboardSummary(BaseModel):
    """
    Top-level summary cards shown on the dashboard.
    All amounts in MXN for consistent display.
    savings_rate is a percentage: (income - expenses) / income * 100
    """
    period_label:       str
    total_income:       Decimal
    total_expenses:     Decimal
    net_balance:        Decimal
    savings_rate:       Decimal
    largest_expense:    Optional[Decimal]
    largest_category:   Optional[str]
    projected_monthly:  Decimal
    vs_projected:       Decimal


class MonthlyDataPoint(BaseModel):
    """
    Single month data point for income vs expenses chart.
    month_label format: 'Jan 2025', 'Feb 2025' etc.
    """
    month_label:    str
    year:           int
    month:          int
    total_income:   Decimal
    total_expenses: Decimal
    net_balance:    Decimal
    projected_monthly: Decimal = Decimal("0")


class MonthlyAnalytics(BaseModel):
    """
    Response for GET /api/v1/analytics/monthly
    Contains data points for each month in the requested range.
    """
    months:         list[MonthlyDataPoint]
    total_income:   Decimal
    total_expenses: Decimal
    net_balance:    Decimal
    period_months:  int
    projected_monthly: Decimal = Decimal("0")


class WeeklyDataPoint(BaseModel):
    """
    Single week data point for cash flow chart.
    week_label format: 'W12 2025'
    """
    week_label:     str
    week_number:    int
    week_year:      int
    total_income:   Decimal
    total_expenses: Decimal
    net_balance:    Decimal


class WeeklyAnalytics(BaseModel):
    """
    Response for GET /api/v1/analytics/weekly
    Contains data points for each week in the requested range.
    """
    weeks:          list[WeeklyDataPoint]
    total_income:   Decimal
    total_expenses: Decimal
    net_balance:    Decimal


class CategoryDataPoint(BaseModel):
    """
    Single category data point for breakdown pie/bar chart.
    pct_of_total is the percentage this category represents
    of all expenses in the period.
    """
    category_id:    Optional[str]
    category_name:  str
    color:          str
    total_amount:   Decimal
    pct_of_total:   Decimal
    transaction_count: int


class CategoryAnalytics(BaseModel):
    """
    Response for GET /api/v1/analytics/categories
    """
    categories:     list[CategoryDataPoint]
    total_expenses: Decimal
    period_label:   str


class ProjectedDataPoint(BaseModel):
    """
    Single month data point comparing projected vs real spending.
    projected_amount comes from recurring rules.
    real_amount comes from actual recorded expenses.
    variance is real - projected (negative = under budget).
    """
    month_label:       str
    year:              int
    month:             int
    projected_amount:  Decimal
    real_amount:       Decimal
    variance:          Decimal
    is_future:         bool


class ProjectedAnalytics(BaseModel):
    """
    Response for GET /api/v1/analytics/projected
    Past months show real vs projected.
    Future months show only projected from recurring rules.
    """
    months:                  list[ProjectedDataPoint]
    total_projected:         Decimal
    total_real:              Decimal
    total_variance:          Decimal
    avg_monthly_projected:   Decimal


class BudgetProgressItem(BaseModel):
    """
    Single budget progress item for the budget overview screen.
    """
    budget_id:       str
    category_name:   str
    color:           str
    period:          str
    limit_amount:    Decimal
    spent_amount:    Decimal
    pct_spent:       Decimal
    remaining:       Decimal
    alert_threshold: int
    is_over_budget:  bool


class BudgetProgressAnalytics(BaseModel):
    """
    Response for GET /api/v1/analytics/budget-progress
    """
    budgets:         list[BudgetProgressItem]
    total_limit:     Decimal
    total_spent:     Decimal
    over_budget_count: int


class CarryForwardStatus(BaseModel):
    """
    State of the carry-forward for a given month.
    balance     — previous month's net balance (MXN, signed)
    applied     — True if a carry-forward entry already exists for this month
    entry_type  — 'income' | 'expense' | 'none'
    source_period — human label of the source month e.g. 'May 2025'
    """
    source_period: str
    balance:       Decimal
    entry_type:    str
    applied:       bool


class CarryForwardApply(BaseModel):
    year:  int
    month: int