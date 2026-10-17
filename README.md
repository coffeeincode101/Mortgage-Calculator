# Mortgage Amortisation Schedule Generator

A Python application for generating detailed mortgage repayment forecasts. It models monthly interest, principal reductions, changes between fixed-rate deals, recurring and one-off overpayments, and an optional Bank of England–linked variable-rate period.

Calculations use Python's `Decimal` type to avoid binary floating-point rounding errors in monetary values. The application produces a month-by-month amortisation schedule and exports it to a formatted Excel workbook.

## Key Features

- **First-payment broken-period interest:** Adds interest accrued from the mortgage completion date through the end of that calendar month (inclusive) to the standard interest for the first repayment month. The additional interest is added to the first payment, preserving the scheduled principal contribution.
- **Decimal-based calculations:** Uses `Decimal` and two-decimal-place quantisation for monetary calculations, with defined repayment rounding behaviour.
- **Strict input validation:** Uses Pydantic v2 models to validate data types and business constraints, including purchase price, deposit, mortgage term, rate-deal durations and overpayment values.
- **Completion-year leap-year handling:** Selects a 365- or 366-day divisor for the initial broken-interest period based on the mortgage completion year. Standard monthly interest is calculated using the annual rate divided by 12; the engine does not recalculate daily interest across every subsequent calendar year.
- **Multiple mortgage deals:** Processes successive fixed-rate periods and recalculates the scheduled payment when a new rate period begins, using the remaining principal and term.
- **Bank of England–linked tracker modelling:** When fixed-rate periods do not cover the full term, the application can use a retrieved Bank Rate plus the configured tracker margin (0.5 percentage points in the supplied configuration) for the remaining period. This is a modelling assumption, not a forecast of future Bank Rate changes.
- **Flexible overpayments:** Supports changes to ongoing monthly overpayments and individual one-off payments. Early settlement caps applied overpayments to the principal still outstanding.
- **Excel export:** Produces a formatted `.xlsx` repayment schedule with monthly payments, principal, interest, overpayments and remaining balance.
- **Python Compatibility:** The mortgage calculator targets Python 3.11 through 3.15. A GitHub Actions continuous integration workflow runs the regression test suite against each supported Python version on pushes and pull requests to main.

## Project Architecture

```text
Mortgage-Calculator/
├── src/
│   ├── mortgage.py          # Application orchestration and entry point
│   ├── engine.py            # Amortisation calculations and schedule generation
│   ├── boe_scraper.py       # Bank of England rate retrieval and cache management
│   ├── contract_checker.py  # Pydantic input validation
│   ├── settings.py          # Application constants and configuration
│   └── utils.py             # Shared utilities, including timing helpers
├── Testing/
│   └── mortgage_testing.py  # Unit and regression tests
├── data/
│   └── boe_rate.json        # Cached successful and failed rate retrievals
├── pyproject.toml
└── README.md
```

## Bank of England Rate Integration

The rate-retrieval module queries the Bank of England's published statistical data for the Bank Rate series (`IUDBEDR`).

The integration includes:

- A seven-day retrieval window for recent published rates.
- A five-day local cache to reduce unnecessary HTTP requests.
- A five-second request timeout to avoid indefinitely waiting for responses.
- JSON-based storage of successful retrievals and failed attempts.
- Historical-rate fallback when live retrieval fails.
- Temporary-file writing and atomic replacement to reduce the risk of corrupted JSON during interrupted writes.

If neither live data nor a historical successful rate is available, the application raises an error instead of silently inventing a rate.

**Important:** A cached or newly retrieved Bank Rate represents a point-in-time value. The calculator does not predict future rate decisions or changes to a lender's tracker terms.

## Prerequisites and Installation

Python 3.11–3.15 is supported and tested through GitHub Actions. Project dependencies and compatible version constraints are managed centrally in [pyproject.toml](pyproject.toml).

**1. Clone the repository**

```bash
git clone https://github.com/coffeeincode101/Mortgage-Calculator.git
cd Mortgage-Calculator
```

**2. Create and activate a virtual environment (macOS/Linux)**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**

```bash
python -m pip install --upgrade pip
python -m pip install --group runtime
```

**4. Environment configuration**

Configure local environment settings as needed. For example, if your application is configured to read these variables, create a `.env` file in the project root:

```dotenv
OUTPUT_PATH=/path/to/your/output/directory
LOG_LEVEL=INFO
```

Do not commit `.env` files containing local paths or secrets.

## Running the Application

From the project root, run:

```bash
python src/mortgage.py
```

### Example Input

The following illustrates the mortgage inputs used by the project. Configure them in the application's entry point or wherever your current input flow supplies the corresponding values.

```python
from datetime import datetime
from decimal import Decimal

my_deals = [
    (Decimal("4.9"), 5),
    (Decimal("4.2"), 2),
    (Decimal("3.8"), 5),
]

monthly_overpayments = [
    (datetime(2024, 3, 1), Decimal("100.00")),
    (datetime(2028, 12, 1), Decimal("200.00")),
    (datetime(2030, 12, 1), Decimal("400.00")),
]

one_off_overpayments = [
    (datetime(2025, 3, 1), Decimal("1000.00")),
    (datetime(2029, 3, 1), Decimal("3000.00")),
]

start_date = datetime(2023, 12, 7)
purchase_price = Decimal("220000.00")
deposit = Decimal("60000.00")
term_years = 35
```

### First Payment Timing

The schedule assumes regular payments are collected on the **first day of each calendar month**, beginning in the month after completion.

For a completion date of 7 December 2023, the first scheduled payment is 1 January 2024 and includes **25 days** of initial broken-period interest (7–31 December, inclusive) in addition to January's standard monthly interest.

The application then generates a monthly schedule and exports it as a formatted Excel workbook to the configured output location.

## Running Unit Tests

Run the `unittest` suite from the project root:

```bash
python -m unittest discover -s Testing -p "mortgage_testing.py" -v
```

The tests cover:

- Daily-rate divisors for leap and non-leap completion years.
- Initial broken-period day counting and combined first-month interest.
- Monthly interest, final payment settlement and principal overpayments.
- Pydantic strict-type checks and business-rule validation.

When calculation conventions or constructor parameters change, update the relevant tests to verify the intended behaviour rather than merely changing expected figures to match the output.

## Calculation Assumptions

This application is a forecasting tool, **not a lender-issued repayment statement**. Actual mortgage statements can differ due to the lender's daily-interest convention, payment collection dates, rate-change timing, fees and contractual treatment of overpayments.

Confirm these details against the relevant mortgage agreement.

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.