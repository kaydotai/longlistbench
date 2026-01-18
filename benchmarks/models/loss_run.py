from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FinancialBreakdown(BaseModel):
    """Financial breakdown by loss category."""

    reserve: float = Field(default=0.0, description="Amount reserved for potential payout")
    paid: float = Field(default=0.0, description="Amount already paid")
    recovered: float = Field(default=0.0, description="Amount recovered (e.g., deductible)")
    total_incurred: float = Field(default=0.0, description="Reserve + Paid - Recovered")


class LossRunIncident(BaseModel):
    """Trucking insurance loss run incident record."""

    incident_number: str = Field(description="Incident number (e.g., #12345)")
    reference_number: str = Field(description="Reference ID (e.g., L240123)")
    company_name: str = Field(description="Trucking company name")
    division: str = Field(default="General", description="Company division")
    coverage_type: str = Field(description="Coverage type (Liability, Physical Damage, Inland Marine, Cargo)")
    status: str = Field(description="Open or Closed")
    policy_number: str = Field(description="Policy identifier")
    policy_state: str = Field(description="Policy state abbreviation")
    cause_code: Optional[str] = Field(default=None, description="Internal cause code")
    description: str = Field(description="Detailed incident description")
    handler: str = Field(default="Claims Adjuster", description="Claims handler")
    unit_number: Optional[str] = Field(default=None, description="Vehicle/truck unit ID")
    date_of_loss: str = Field(description="Date incident occurred")
    loss_state: str = Field(description="State where loss occurred")
    date_reported: str = Field(description="Date reported to insurance")
    agency: Optional[str] = Field(default=None, description="Insurance agency name")
    insured: str = Field(description="Insured party name")
    claimants: list[str] = Field(default_factory=list, description="List of claimants")
    driver_name: Optional[str] = Field(default=None, description="Driver name at time of incident")

    bi: FinancialBreakdown = Field(default_factory=FinancialBreakdown, description="Bodily Injury")
    pd: FinancialBreakdown = Field(default_factory=FinancialBreakdown, description="Property Damage")
    lae: FinancialBreakdown = Field(default_factory=FinancialBreakdown, description="Loss Adjustment Expense")
    ded: FinancialBreakdown = Field(default_factory=FinancialBreakdown, description="Deductible")

    adjuster_notes: Optional[str] = Field(default=None, description="Additional adjuster notes")
