"""Generate realistic synthetic trucking insurance loss run data (golden data)."""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from faker import Faker

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.models.loss_run import FinancialBreakdown, LossRunIncident

fake = Faker()

# Coverage types with their specific incidents
COVERAGE_TYPES = {
    "Liability": [
        "IV backing into loading dock, hit {target}",
        "IV changing lanes, sideswiped OV",
        "IV rear-ended OV at traffic light",
        "IV making right turn, trailer struck OV",
        "IV lost control on wet pavement, struck {target}",
        "IV merging onto highway, collided with OV",
        "OV changed lanes into IV, causing collision",
        "IV backing, struck parked {target}",
        "Trailer door detached, struck adjacent vehicle",
        "IV hydroplaned, hit concrete barrier",
        "IV brakes failed, rear-ended OV",
        "Tire blowout caused IV to veer into OV",
        "IV making wide turn, clipped OV on passenger side",
        "OV ran stop sign, struck IV broadside",
    ],
    "Physical Damage": [
        "IV rollover on icy highway. Total loss.",
        "Engine fire while parked at truck stop",
        "Collision with deer caused front-end damage",
        "Windshield shattered by road debris",
        "Transmission failure during transport",
        "IV struck by falling tree branch during storm",
        "Trailer damaged in loading dock collision",
        "Fuel tank punctured by road debris",
    ],
    "Inland Marine": [
        "Cargo damaged during transport - water intrusion",
        "Insured transporting vehicle was damaged",
        "Theft of cargo from trailer at rest stop",
        "Refrigeration unit failure - spoiled goods",
        "Load shift caused cargo damage",
        "Cargo stolen from locked trailer overnight",
        "Equipment damaged during loading",
        "Cargo crushed due to improper securing",
    ],
    "Cargo": [
        "Shortage discovered at delivery",
        "Pallets damaged in transit",
        "Temperature-controlled cargo spoiled",
        "Cargo contamination during transport",
        "Missing items from sealed trailer",
        "Water damage to freight",
        "Cargo crushed from improper stacking",
    ],
}

CARGO_TYPES = ["electronics", "food products", "automotive parts", "machinery", "textiles"]
TARGETS = ["parked OV", "concrete barrier", "guardrail", "bridge support", "dock equipment"]
TRUCK_MAKES = ["Freightliner", "Kenworth", "Peterbilt", "Volvo", "Mack", "International"]
STATUSES = ["Open", "Closed"]
US_STATES = ["CA", "TX", "FL", "NY", "PA", "IL", "OH", "GA", "NC", "MI", "AZ", "TN", "OK", "AR", "MO"]


def _random_date(start: datetime, end: datetime) -> datetime:
    """Return a random datetime between start and end."""
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=fake.random_int(0, delta))


def _generate_company_name() -> str:
    """Generate a realistic trucking company name."""
    prefixes = ["Atlas", "Summit", "Horizon", "Delta", "Pioneer", "Eagle", "Titan", "Liberty"]
    middles = ["Express", "Freight", "Logistics", "Transport", "Cargo", "Hauling"]
    suffixes = ["LLC", "Inc", "Co", "Group"]
    
    pattern = random.choice([
        f"{random.choice(prefixes)} {random.choice(middles)} {random.choice(suffixes)}",
        f"{fake.last_name()} {random.choice(middles)} {random.choice(suffixes)}",
        f"{fake.city()} {random.choice(middles)}",
    ])
    return pattern


def _generate_incident_description(coverage_type: str) -> str:
    """Generate a realistic incident description for the coverage type."""
    templates = COVERAGE_TYPES.get(coverage_type, COVERAGE_TYPES["Liability"])
    template = random.choice(templates)
    if "{target}" in template:
        template = template.replace("{target}", random.choice(TARGETS))
    return template


def _calculate_financial_amounts(status: str, coverage_type: str) -> dict:
    """Generate realistic financial amounts based on coverage type."""
    amounts = {"bi": None, "pd": None, "lae": None, "ded": None}
    
    if coverage_type == "Liability":
        # Liability claims have both PD and sometimes BI
        has_bi = random.random() < 0.25  # 25% have bodily injury
        
        # Property Damage (common)
        if status == "Closed":
            pd_paid = round(random.uniform(3000, 50000), 2)
            amounts["pd"] = FinancialBreakdown(
                reserve=0.0, paid=pd_paid, recovered=0.0, total_incurred=pd_paid
            )
        else:  # Open
            pd_reserve = round(random.uniform(5000, 60000), 2)
            pd_paid = round(random.uniform(0, pd_reserve * 0.3), 2) if random.random() < 0.3 else 0.0
            amounts["pd"] = FinancialBreakdown(
                reserve=pd_reserve, paid=pd_paid, recovered=0.0, total_incurred=pd_reserve + pd_paid
            )
        
        # Bodily Injury (if applicable)
        if has_bi:
            if status == "Closed":
                bi_paid = round(random.uniform(10000, 100000), 2)
                amounts["bi"] = FinancialBreakdown(
                    reserve=0.0, paid=bi_paid, recovered=0.0, total_incurred=bi_paid
                )
            else:  # Open
                bi_reserve = round(random.uniform(20000, 150000), 2)
                amounts["bi"] = FinancialBreakdown(
                    reserve=bi_reserve, paid=0.0, recovered=0.0, total_incurred=bi_reserve
                )
        
        # Deductible recovery
        if random.random() < 0.7:
            ded_recovered = round(random.uniform(5000, 35000), 2)
            amounts["ded"] = FinancialBreakdown(
                reserve=0.0, paid=0.0, recovered=ded_recovered, total_incurred=-ded_recovered
            )
    
    elif coverage_type == "Physical Damage":
        # Physical damage to insured vehicle
        if status == "Closed":
            pd_paid = round(random.uniform(2000, 80000), 2)  # Can be high for total loss
            amounts["pd"] = FinancialBreakdown(
                reserve=0.0, paid=pd_paid, recovered=0.0, total_incurred=pd_paid
            )
        else:  # Open
            pd_reserve = round(random.uniform(5000, 100000), 2)
            amounts["pd"] = FinancialBreakdown(
                reserve=pd_reserve, paid=0.0, recovered=0.0, total_incurred=pd_reserve
            )
        
        # Deductible
        if random.random() < 0.8:
            ded_recovered = round(random.uniform(1000, 5000), 2)
            amounts["ded"] = FinancialBreakdown(
                reserve=0.0, paid=0.0, recovered=ded_recovered, total_incurred=-ded_recovered
            )
    
    elif coverage_type in ["Inland Marine", "Cargo"]:
        # Cargo/equipment damage - typically PD only
        if status == "Closed":
            pd_paid = round(random.uniform(500, 50000), 2)
            amounts["pd"] = FinancialBreakdown(
                reserve=0.0, paid=pd_paid, recovered=0.0, total_incurred=pd_paid
            )
        else:  # Open
            pd_reserve = round(random.uniform(1000, 60000), 2)
            amounts["pd"] = FinancialBreakdown(
                reserve=pd_reserve, paid=0.0, recovered=0.0, total_incurred=pd_reserve
            )
        
        # Deductible (less common for cargo)
        if random.random() < 0.4:
            ded_recovered = round(random.uniform(500, 10000), 2)
            amounts["ded"] = FinancialBreakdown(
                reserve=0.0, paid=0.0, recovered=ded_recovered, total_incurred=-ded_recovered
            )
    
    # LAE (Loss Adjustment Expense) - only on some closed claims
    if status == "Closed" and random.random() < 0.3:
        lae_paid = round(random.uniform(200, 2000), 2)
        amounts["lae"] = FinancialBreakdown(
            reserve=0.0, paid=lae_paid, recovered=0.0, total_incurred=lae_paid
        )
    
    # Default to zero breakdowns if not set
    for key in ["bi", "pd", "lae", "ded"]:
        if amounts[key] is None:
            amounts[key] = FinancialBreakdown()
    
    return amounts


def _create_incident(idx: int, start_year: int = 2023) -> LossRunIncident:
    """Generate a single realistic loss run incident."""
    # Generate dates
    loss_date = _random_date(
        datetime(start_year, 1, 1),
        datetime(start_year + 1, 12, 31)
    )
    # Reported date is 1-60 days after loss (can be longer for some)
    report_delay = random.choices(
        [random.randint(1, 7), random.randint(8, 30), random.randint(31, 120)],
        weights=[60, 30, 10]
    )[0]
    reported_date = loss_date + timedelta(days=report_delay)
    
    # Status
    status = random.choice(STATUSES)
    
    # Select coverage type (weighted distribution)
    coverage_type = random.choices(
        list(COVERAGE_TYPES.keys()),
        weights=[60, 20, 15, 5]  # Liability most common, then Physical Damage, Inland Marine, Cargo
    )[0]
    
    # Company details
    company_name = _generate_company_name()
    policy_state = random.choice(US_STATES)
    
    # Generate incident description based on coverage type
    description = _generate_incident_description(coverage_type)
    
    # Driver name (not always present for cargo/physical damage claims)
    driver_name = None
    if coverage_type == "Liability" or random.random() < 0.5:
        driver_name = f"{fake.last_name()}, {fake.first_name()}"
    
    # Claimants (more common for Liability claims)
    num_claimants = 0
    if coverage_type == "Liability":
        num_claimants = random.choices([0, 1, 2, 3, 4], weights=[10, 50, 25, 10, 5])[0]
    elif random.random() < 0.3:  # Some non-liability claims have claimants
        num_claimants = random.choices([1, 2], weights=[80, 20])[0]
    
    claimants = []
    for _ in range(num_claimants):
        if random.random() < 0.8:
            claimants.append(f"{fake.last_name()}, {fake.first_name()}")
        else:
            claimants.append(fake.company())
    
    # Financial amounts based on coverage type
    amounts = _calculate_financial_amounts(status, coverage_type)
    
    # Unit number (truck ID) - sometimes present
    unit_number = None
    if random.random() < 0.4:
        unit_number = f"{random.choice(['2023', '2024'])} {random.choice(TRUCK_MAKES)[:2].upper()} {random.randint(100000, 999999)}"
    
    # Agency - sometimes present
    agency = fake.company() if random.random() < 0.3 else None
    
    # Adjuster notes - rare but detailed
    adjuster_notes = None
    if random.random() < 0.15:
        adjuster_notes = fake.sentence(nb_words=15)
    
    # Reference number format: L + year(2 digits) + sequential
    ref_year = loss_date.year % 100
    ref_num = f"L{ref_year}{idx:04d}"
    
    return LossRunIncident(
        incident_number=f"#{30000 + idx}",
        reference_number=ref_num,
        company_name=company_name,
        division="General",
        coverage_type=coverage_type,
        status=status,
        policy_number=f"L{ref_year}A{random.randint(1000, 9999)}",
        policy_state=policy_state,
        cause_code=None,
        description=description,
        handler="Claims Adjuster",
        unit_number=unit_number,
        date_of_loss=loss_date.strftime("%m/%d/%Y"),
        loss_state=random.choice(US_STATES),
        date_reported=reported_date.strftime("%m/%d/%Y"),
        agency=agency,
        insured=company_name,
        claimants=claimants,
        driver_name=driver_name,
        bi=amounts["bi"],
        pd=amounts["pd"],
        lae=amounts["lae"],
        ded=amounts["ded"],
        adjuster_notes=adjuster_notes
    )


def generate_incidents(n: int, seed: Optional[int] = None, start_year: int = 2023) -> list[LossRunIncident]:
    """Generate n loss run incidents. Use seed for reproducibility."""
    if seed is not None:
        Faker.seed(seed)
        random.seed(seed)
    return [_create_incident(i + 1, start_year=start_year) for i in range(n)]


def write_json(incidents: list[LossRunIncident], path: Path) -> None:
    """Write incidents to JSON file."""
    data = [incident.model_dump() for incident in incidents]
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved {len(incidents)} incidents → {path}")


def write_csv(incidents: list[LossRunIncident], path: Path) -> None:
    """Write incidents to CSV file (flattened structure)."""
    if not incidents:
        print("No incidents to write")
        return
    
    # Flatten the nested financial structures for CSV
    rows = []
    for incident in incidents:
        row = {
            "incident_number": incident.incident_number,
            "reference_number": incident.reference_number,
            "company_name": incident.company_name,
            "division": incident.division,
            "coverage_type": incident.coverage_type,
            "status": incident.status,
            "policy_number": incident.policy_number,
            "policy_state": incident.policy_state,
            "cause_code": incident.cause_code or "",
            "description": incident.description,
            "handler": incident.handler,
            "unit_number": incident.unit_number or "",
            "date_of_loss": incident.date_of_loss,
            "loss_state": incident.loss_state,
            "date_reported": incident.date_reported,
            "agency": incident.agency or "",
            "insured": incident.insured,
            "claimants": "; ".join(incident.claimants),
            "driver_name": incident.driver_name or "",
            # BI
            "bi_reserve": incident.bi.reserve,
            "bi_paid": incident.bi.paid,
            "bi_recovered": incident.bi.recovered,
            "bi_total_incurred": incident.bi.total_incurred,
            # PD
            "pd_reserve": incident.pd.reserve,
            "pd_paid": incident.pd.paid,
            "pd_recovered": incident.pd.recovered,
            "pd_total_incurred": incident.pd.total_incurred,
            # LAE
            "lae_reserve": incident.lae.reserve,
            "lae_paid": incident.lae.paid,
            "lae_recovered": incident.lae.recovered,
            "lae_total_incurred": incident.lae.total_incurred,
            # DED
            "ded_reserve": incident.ded.reserve,
            "ded_paid": incident.ded.paid,
            "ded_recovered": incident.ded.recovered,
            "ded_total_incurred": incident.ded.total_incurred,
            "adjuster_notes": incident.adjuster_notes or "",
        }
        rows.append(row)
    
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"✓ Saved {len(incidents)} incidents → {path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic trucking insurance loss run data."
    )
    parser.add_argument(
        "-n", "--num", type=int, default=100, help="Number of incidents (default: 100)"
    )
    parser.add_argument(
        "-o",
        "--output",
        default="benchmarks/synthetic/data/incidents.json",
        help="Output file path",
    )
    parser.add_argument(
        "-s", "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--csv", action="store_true", help="Output CSV instead of JSON"
    )
    parser.add_argument(
        "--year", type=int, default=2023, help="Start year for loss dates (default: 2023)"
    )

    args = parser.parse_args()
    incidents = generate_incidents(args.num, seed=args.seed, start_year=args.year)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.csv or str(output_path).endswith(".csv"):
        write_csv(incidents, output_path)
    else:
        write_json(incidents, output_path)


if __name__ == "__main__":
    main()
