import logging
import pandas as pd
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from pydantic import ValidationError
import json

from src.utils import get_output_path, time_it
from src.settings import (
    setup_logging,
    DEFAULT_VARIABLE_ADD_ON,
    DEFAULT_CURRENCY_SYMBOL,
    )
from src.engine import generate_schedule
from src.boe_scraper import setup as fetch_boe_base_rate
from src.contract_checker import MortgageDataChecker

setup_logging()
logger = logging.getLogger(__name__)

def load_config() -> dict:
    """Load mortgage configuration from the project root."""

    config_path = Path(__file__).resolve().parent.parent / 'config.json'

    with config_path.open('r', encoding='utf-8') as file:
        return json.load(file)


def parse_config(config: dict) -> dict:
    """Convert JSON configuration into mortgage input types."""

    return {
        'purchase_price': Decimal(config['purchase_price']),
        'deposit': Decimal(config['deposit']),
        'term_years': config['term_years'],
        'start_date': datetime.fromisoformat(config['start_date']),

        'fixed_deals': [
            (Decimal(deal['rate']), deal['years'])
            for deal in config['fixed_deals']
        ],

        'overpayments': [
            (
                datetime.fromisoformat(payment['date']),
                Decimal(payment['amount'])
            )
            for payment in config.get('overpayments', [])
        ],

        'one_off_overpayments': [
            (
                datetime.fromisoformat(payment['date']),
                Decimal(payment['amount'])
            )
            for payment in config.get('one_off_overpayments', [])
        ],
    }

@time_it
def validate_inputs(
    purchase_price: Decimal,
    deposit: Decimal,
    term_years: int,
    start_date: datetime,
    fixed_deals: List[Tuple[Decimal, int]],
    variable_tracker: Decimal,
    overpayments: List[Tuple[datetime, Decimal]],
    one_off_overpayments: List[Tuple[datetime, Decimal]]) -> Optional[pd.DataFrame]:
    """Validated user inputs against business logic, to ensure a clean output"""

    try:
        # Enforce contract rules strictly using the arguments passed into this function
        # Since one_off_overpayments has an int inside the type hint, we map it safely.
        validated_inputs = MortgageDataChecker(
            purchase_price=purchase_price,
            deposit=deposit,
            term_years=term_years,
            start_date=start_date,
            fixed_deals=fixed_deals,
            variable_tracker=variable_tracker,
            overpayments=overpayments,
            one_off_overpayments= one_off_overpayments,
        )
    except ValidationError as error:
        logger.error(f"Contract structural breach detected:\n{error}. ")
        return None
    except ValueError as error:
        logger.error(f"Contract business rule breach detected: {error}")
        return None

    fixed_deal_lengths = sum(
        deal_length for _, deal_length in validated_inputs.fixed_deals
    )
    total_term_months = validated_inputs.term_years * 12

    return generate_schedule(
        validated_inputs.purchase_price,
        validated_inputs.deposit,
        validated_inputs.term_years,
        validated_inputs.start_date,
        validated_inputs.fixed_deals,
        validated_inputs.variable_tracker,
        validated_inputs.overpayments,
        validated_inputs.one_off_overpayments,
        fixed_deal_lengths,
        total_term_months,
    )

def save_to_excel(df: pd.DataFrame) -> None:
    """Function saves output to Excel file in currency format and allows """
    
    output_dir = get_output_path()
    timestamp = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    filename = f'{timestamp} - amortise schedule.xlsx'
    full_path = output_dir / filename    
    Path(full_path).parent.mkdir(exist_ok=True, parents=True)

    with pd.ExcelWriter(full_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Mortgage Schedule')
        workbook  = writer.book
        worksheet = writer.sheets['Mortgage Schedule']
        money_format = workbook.add_format({'num_format':'£#,##0.00'})
        worksheet.set_column('B:F', 20, money_format)
        logger.info(f'File successfully saved as an Excel file in {full_path}')

    return None


if __name__ == '__main__':

    # Load and parse mortgage configuration from config.json.
    mortgage_config = parse_config(load_config())

    # Retrieve the Bank of England rate and apply the tracker margin.
    get_boe_rate = (
        Decimal(str(fetch_boe_base_rate()))
        + DEFAULT_VARIABLE_ADD_ON
    )

    # Validate mortgage inputs and generate the repayment schedule.
    df = validate_inputs(
        **mortgage_config,
        variable_tracker=get_boe_rate
    )

    # Preserve currency formatting for pandas output.
    pd.options.display.float_format = (
        f'{DEFAULT_CURRENCY_SYMBOL}{{:,.2f}}'.format
    )

    # Export the completed mortgage schedule to Excel.
    if df is not None:
        save_to_excel(df)
