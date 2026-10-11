# Mortgage Amortisation Schedule Generator

A high-precision financial tracking engine written in Python to calculate comprehensive mortgage amortisation schedules. This tool accurately models interest calculations down to the day, accounts for standard UK banking adjustments, and supports both recurring and one-off overpayments.

## Key Features

- **Dual-Interest First Payment:** Accurately calculates true UK banking startup costs by combining extra broken days in the completion month (e.g., intermediate completion gaps) alongside a standard full calendar month's amortised interest.
- **Contract Boundary Enforcement:** Utilises Pydantic v2 (Strict Mode) to validate data contracts, ensuring inputs like deposits, purchase prices, and deal structures adhere strictly to realistic constraints.
- **Dynamic Multi-Deal Sequencing:** Progresses automatically across separate fixed-rate deals before shifting gracefully onto external variable tracker configurations.
- **Automatic Variable Tracker Fallback:** If the total duration of your fixed rate deals is less than the overall mortgage term, the engine automatically fetches the Bank of England base rate and appends a 0.5% contractual premium to model tracker behavior for all remaining months.
- **Flexible Capital Overpayments:** Supports custom data loops mapping both ongoing monthly overpayment changes and precise one-off capital injections.
- **Formatted Excel Export:** Exports clean, ready-for-client tabular analysis straight into a formatted .xlsx spreadsheet.

## Project Architecture

```text
├── src/
│   ├── mortgage.py          # Main application orchestration & script entry point
│   ├── engine.py            # Core math calculator, day counts, & loop schedules
│   ├── contract_checker.py  # Pydantic v2 data structure & structural model validation
│   └── settings.py          # Global business thresholds, limits, and logging setup
└── Testing/
    └── mortgage_testing.py  # Complete unit test assertions for interest quantization
```

## Prerequisites and Installation

1. **Clone the repository and enter the directory:**
   ```bash
   git clone https://github.com
   cd Mortgage-Calculator
   ```

2. **Activate your virtual environment:**
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   Ensure you have pandas, pydantic, openpyxl, xlsxwriter, and python-dotenv installed inside your environment.

4. **Environment Configuration:**
   Create a .env file in the root directory of your project to store local system variables or secret paths:
   ```text
   OUTPUT_PATH=/path/to/your/output/directory
   LOG_LEVEL=INFO
   ```

## How to Run the Project

To execute the application data runner and compile your formatted spreadsheet schedule, execute the entry-point script:

```bash
python src/mortgage.py
```

### Usage Example

To test or modify calculation inputs, update the data parameters structured under the `if __name__ == '__main__':` block at the bottom of `src/mortgage.py`:

```python
if __name__ == '__main__':
    
    my_deals = [(Decimal('4.9'), 5), (Decimal('4.2'), 2), (Decimal('3.8'), 5)]

    monthly_overpayments = [
        (datetime(2024, 3, 1), Decimal('100')),
        (datetime(2028, 12, 1), Decimal('200')),
        (datetime(2030, 12, 1), Decimal('400')),
    ]

    start_date = datetime(2023, 12, 7)
    purchase_price = Decimal('220000')
    deposit = Decimal('60000')
    term_years = 35
    one_off_overpayments = [(datetime(2025, 3, 1), Decimal('1000')), (datetime(2029, 3, 1), Decimal('3000'))] #When adding data make sure to use "(datetime(yyy, mm , dd), Decimal('1000'))" for each one-off payments
```

Running the script with these values processes your underlying caching data loops, runs structural contract constraint checks, and loads required keys using python-dotenv. 

**Note on Payment Alignment:** The schedule engine assumes that regular direct debit collections default to the **1st of every calendar month**. If a mortgage starts mid-month (e.g., 7th December), the engine automatically aggregates the broken days of that completion month into the first payment run on the 1st of the following month (1st January).

The script then outputs an Excel file containing the complete monthly payment schedule, formatted with sterling currency indicators and saved into your designated output folder path.

## Running Unit Tests

A comprehensive verification suite is built-in to isolate precision targets and test first-month combined dual-interest logic bounds (ensuring alignment with the quantized baseline calculation metrics). 

Execute the test suite from your project terminal root using:

```bash
python -m unittest Testing/mortgage_testing.py
```

## License
Distributed under the MIT License. See [LICENSE](LICENSE) for more information.
