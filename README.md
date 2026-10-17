# Mortgage Amortisation Schedule Generator

A Python application for generating detailed mortgage repayment forecasts, including monthly interest, principal reductions, fixed-rate transitions, recurring and one-off overpayments, and Bank of England–linked variable-rate modelling.

The application uses Python's `Decimal` type for financial calculations, Pydantic v2 for strict input validation, and pandas with XlsxWriter to produce formatted Excel amortisation schedules.

Mortgage inputs are managed through an editable **`config.json` file**, allowing users to generate different forecasts without modifying the Python source code.

The project also includes Docker containerisation, automated regression and integration tests, and GitHub Actions continuous integration.

## Key Features

- **Mortgage amortisation:** Calculates monthly payments, interest, principal reductions, overpayments and outstanding balances.
- **Fixed-rate transitions:** Supports consecutive fixed-rate deals and recalculates repayments based on the remaining balance and mortgage term.
- **Bank of England integration:** Retrieves the published Bank Rate and applies a configurable tracker margin for the variable-rate period.
- **Broken-period interest:** Calculates additional interest accrued between the completion date and the end of the completion month.
- **Leap-year handling:** Uses the appropriate 365- or 366-day divisor when calculating initial broken-period interest.
- **Recurring overpayments:** Supports changes to monthly overpayment amounts at specified dates.
- **One-off overpayments:** Allows additional individual payments to reduce the outstanding balance.
- **Strict validation:** Uses Pydantic v2 to enforce data types and mortgage business rules.
- **JSON configuration:** Allows mortgage inputs to be changed without editing application code.
- **Excel export:** Generates a formatted `.xlsx` workbook containing the repayment schedule.
- **Docker support:** Allows the application to run without installing Python dependencies on the host machine.
- **Automated testing:** Supports Python 3.11–3.15 through GitHub Actions.

## Project Architecture

```text
Mortgage-Calculator/
├── .github/
│   └── workflows/             # Continuous integration
├── src/
│   ├── mortgage.py            # Application orchestration and Excel export
│   ├── engine.py              # Mortgage calculation engine
│   ├── contract_checker.py    # Pydantic input validation
│   ├── boe_scraper.py         # Bank of England rate retrieval
│   ├── settings.py            # Application configuration
│   └── utils.py               # Shared utilities
├── Testing/
│   └── mortgage_testing.py    # Automated tests
├── config.json                # Editable mortgage inputs
├── data/
│   └── boe_rate.json          # Bank of England cache
├── Schedules/                 # Generated Excel schedules
├── Dockerfile
├── .dockerignore
├── .gitignore
├── pyproject.toml
└── README.md
```

The architecture separates application orchestration, input validation, financial calculations, external data retrieval and output generation.

## Mortgage Configuration

Mortgage inputs are managed through `config.json`, located in the repository root.

Users can modify their mortgage details without editing Python source code.

### Example config.json

```json
{
  "purchase_price": "220000.00",
  "deposit": "60000.00",
  "term_years": 35,
  "start_date": "2023-12-07",
  "fixed_deals": [
    {
      "rate": "4.9",
      "years": 5
    },
    {
      "rate": "4.2",
      "years": 2
    },
    {
      "rate": "3.8",
      "years": 5
    }
  ],
  "overpayments": [
    {
      "date": "2024-03-01",
      "amount": "100.00"
    },
    {
      "date": "2028-12-01",
      "amount": "200.00"
    },
    {
      "date": "2030-12-01",
      "amount": "400.00"
    }
  ],
  "one_off_overpayments": []
}
```

### Configuration Parameters

| Parameter | Description |
|---|---|
| `purchase_price` | Property purchase price |
| `deposit` | Initial mortgage deposit |
| `term_years` | Total mortgage term in years |
| `start_date` | Mortgage completion date |
| `fixed_deals` | Fixed interest rates and their durations in years |
| `overpayments` | Changes to recurring monthly overpayment amounts |
| `one_off_overpayments` | Individual additional payments |

### One-Off Overpayment Example

To add individual overpayments, modify the `one_off_overpayments` section:

```json
"one_off_overpayments": [
  {
    "date": "2026-10-01",
    "amount": "1000.00"
  },
  {
    "date": "2028-05-01",
    "amount": "5000.00"
  }
]
```

If no additional payments are required, use an empty list:

```json
"one_off_overpayments": []
```

### Configuration Rules

- Store monetary amounts and interest rates as JSON strings to preserve decimal precision.
- Use `YYYY-MM-DD` for dates.
- Mortgage terms and fixed-deal durations must be integers.
- Fixed interest rates must be greater than 0%.
- Variable interest rates must be greater than 0% when provided to the validation contract.
- Combined fixed-rate durations cannot exceed the mortgage term.
- The deposit must be greater than zero and less than the purchase price.
- Overpayment amounts cannot be negative.
- Multiple recurring overpayment changes in the same calendar month are rejected.
- Multiple one-off overpayments in the same calendar month are rejected.
- Malformed individual records are rejected rather than silently discarded.
- Empty overpayment lists are permitted.

### Configuration Processing

The application follows this sequence:

1. `load_config()` reads `config.json`.
2. `parse_config()` converts the JSON values into Python types, including `Decimal`, `datetime` and tuples.
3. The application obtains the Bank of England rate and applies the configured tracker margin.
4. `MortgageDataChecker` validates the mortgage inputs.
5. The validated values are passed to the calculation engine.
6. The resulting amortisation schedule is exported to Excel.

The configuration parser handles data conversion, while Pydantic enforces the mortgage input contract.

**When using Docker, changes to `config.json` take effect on the next container run without rebuilding the image.**

## Installation — Running with Python

Python 3.11–3.15 is supported.

Dependencies are defined in `pyproject.toml`.

### 1. Clone the Repository

```bash
git clone https://github.com/coffeeincode101/Mortgage-Calculator.git
cd Mortgage-Calculator
```

### 2. Create a Virtual Environment

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
python -m pip install --upgrade pip
python -m pip install --group runtime
```

### 4. Configure Mortgage Inputs

Open `config.json` and modify the mortgage details.

Save the configuration before executing the application.

### 5. Run the Application

From the repository root:

```bash
python -m src.mortgage
```

The application loads the configuration, validates the inputs, calculates the amortisation schedule and exports the resulting Excel workbook to its configured output location.

## Docker Deployment

Docker allows the application to run inside an isolated Python environment without requiring Python or the project dependencies to be installed on the host computer.

The Docker image uses Python 3.15 slim and runs the application as a non-root user.

### Prerequisites

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and ensure it is running.

Git is required to clone the repository.

### macOS / Linux

#### 1. Clone the Repository

```bash
git clone https://github.com/coffeeincode101/Mortgage-Calculator.git
cd Mortgage-Calculator
```

#### 2. Build the Docker Image

```bash
docker build -t mortgage-calculator:1.2 .
```

#### 3. Prepare Persistent Directories

```bash
mkdir -p Schedules data
```

#### 4. Run the Container

```bash
docker run --rm \
  -v "$(pwd)/Schedules:/app/output" \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config.json:/app/config.json:ro" \
  mortgage-calculator:1.2
```

The generated Excel file will appear in the repository's `Schedules/` directory.

### Windows PowerShell

#### 1. Clone the Repository

```powershell
git clone https://github.com/coffeeincode101/Mortgage-Calculator.git
cd Mortgage-Calculator
```

#### 2. Build the Docker Image

```powershell
docker build -t mortgage-calculator:1.2 .
```

#### 3. Prepare Persistent Directories

```powershell
New-Item -ItemType Directory -Force -Path Schedules, data | Out-Null
```

#### 4. Run the Container

```powershell
docker run --rm `
  -v "${PWD}/Schedules:/app/output" `
  -v "${PWD}/data:/app/data" `
  -v "${PWD}/config.json:/app/config.json:ro" `
  mortgage-calculator:1.2
```

The Excel workbook will be available inside the `Schedules` folder.

To open the folder in Windows File Explorer:

```powershell
explorer.exe .\Schedules
```

### Docker Volume Mapping

| Host location | Container location | Purpose |
|---|---|---|
| `Schedules/` | `/app/output` | Generated Excel amortisation schedules |
| `data/` | `/app/data` | Bank of England cache |
| `config.json` | `/app/config.json` | Mortgage input configuration |

The configuration file is mounted as read-only (`:ro`).

This allows Docker to read the latest mortgage inputs without modifying the file.

The `--rm` option removes the container after execution. Files in the mounted host directories remain available.

### Changing Mortgage Inputs

After the initial Docker image has been built:

1. Open `config.json`.
2. Modify the mortgage details.
3. Save the file.
4. Run the existing `docker run` command again.
5. Open the newly generated workbook in `Schedules/`.

**There is no need to rebuild Docker when changing only mortgage inputs in `config.json`.**

Rebuilding is required when application source code or dependencies change.

## Bank of England Integration

The application retrieves the Bank of England's published Bank Rate series (`IUDBEDR`).

The scraper includes:

- A seven-day retrieval window.
- A five-day local cache.
- A five-second HTTP request timeout.
- JSON storage of successful and failed retrieval attempts.
- Historical-rate fallback when a live request fails.
- Temporary-file writing and atomic replacement to reduce the risk of cache corruption.

If the live request fails, the application attempts to reuse its most recent successful historical rate.

If no live or historical rate is available, the application raises an error rather than inventing a rate.

### Variable-Rate Modelling

When fixed-rate deals do not cover the full mortgage term, the calculator uses the retrieved Bank Rate plus the configured tracker margin for the remaining period.

The supplied configuration uses an additional **0.5 percentage points**.

This is a forecasting assumption. The application does not predict future Bank Rate changes.

## Financial Calculation Methodology

### Monthly Interest

Standard monthly interest is calculated using:

```text
Monthly interest = Outstanding balance × (Annual rate / 100 / 12)
```

Monetary calculations use `Decimal` and appropriate two-decimal-place quantisation.

### Initial Broken-Period Interest

The calculator accounts for interest accrued from the mortgage completion date through the end of the completion month, inclusive.

For example:

```text
Completion date: 7 December 2023
First regular payment: January 2024
Broken-period interest: 25 days
```

Additional broken-period interest is included in the first payment while preserving the scheduled principal contribution.

The daily-rate divisor is based on whether the completion year contains 365 or 366 days.

### Fixed-Rate Transitions

When one fixed-rate deal ends and another begins, the calculator recalculates the scheduled monthly repayment using the outstanding balance, remaining mortgage term and new interest rate.

### Overpayments

Recurring monthly and one-off overpayments reduce the outstanding principal.

The calculation engine caps applied overpayments when necessary to prevent the outstanding mortgage balance from becoming negative.

Additional payments can shorten the overall repayment period.

## Automated Testing

The project includes unit, regression and integration tests using Python's `unittest` framework.

### Run the Test Suite

From the project root:

```bash
python -m unittest discover -s Testing -p 'mortgage_testing.py' -v
```

### Test Coverage

The automated tests cover:

- Mortgage interest calculations.
- Broken-period interest.
- Leap-year handling.
- Fixed-rate transitions.
- Full mortgage amortisation.
- Recurring overpayments.
- Early mortgage settlement.
- Strict Pydantic input validation.
- Invalid mortgage terms and interest rates.
- Duplicate and malformed overpayment records.
- Bank of England JSON persistence.
- Atomic file replacement and failed-write protection.
- Network timeouts and cached-rate fallback.
- Missing historical Bank of England rates.
- Excel workbook generation and verification.

### End-to-End Integration Testing

The integration test exercises the complete mortgage calculation and Excel export workflow.

It:

1. Supplies valid mortgage inputs.
2. Executes Pydantic validation.
3. Generates a 24-month amortisation schedule.
4. Exports the schedule into an Excel workbook.
5. Opens the generated workbook using pandas.
6. Verifies the repayment records and final mortgage balance.
7. Confirms that the total principal repaid matches the original mortgage balance.

The test uses a temporary output directory, preventing changes to existing mortgage forecasts.

The integration test uses explicitly supplied interest rates and does not require a live Bank of England connection.

## Continuous Integration

GitHub Actions automatically runs the test suite against:

| Python version | Environment |
|---|---|
| 3.11 | Ubuntu |
| 3.12 | Ubuntu |
| 3.13 | Ubuntu |
| 3.14 | Ubuntu |
| 3.15 | Ubuntu |

Each environment independently installs the project dependencies and executes the automated tests.

The workflow supports pushes to `main`, pull requests targeting `main` and manual execution.

## Limitations and Assumptions

**This application is a mortgage forecasting tool, not a lender-issued mortgage statement or financial advice.**

Actual lender calculations may differ due to:

- Daily-interest conventions.
- Payment collection dates.
- Interest-rate changes.
- Mortgage fees.
- Contractual treatment of overpayments.
- Lender-specific repayment rounding rules.

The Bank of England tracker model assumes a constant rate over the remaining variable-rate period. It does not predict future interest-rate decisions.

Users should verify the modelling assumptions against their mortgage agreement before relying on the forecast.

## Licence

Distributed under the MIT License. See [LICENSE](LICENSE).