import logging
import pandas as pd
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from pydantic import ValidationError

from utils import get_output_path, time_it
from settings import setup_logging, DEFAULT_VARIABLE_ADD_ON, DEFAULT_CURRENCY_SYMBOL
from engine import generate_schedule
from boe_scraper import setup as fetch_boe_base_rate
from contract_checker import MortgageDataChecker

setup_logging()
logger = logging.getLogger(__name__)

@time_it
def validate_inputs(
    purchase_price: Decimal,
    deposit: Decimal,
    term_years: int,
    start_date: datetime,
    fixed_deals: List[Tuple[Decimal, int]],
    variable_tracker: Decimal,
    overpayments: List[Tuple[datetime, Decimal]],
    one_off_overpayments: List[Tuple[datetime, float]]) -> Optional[pd.DataFrame]:
    '''Validated user inputs against business logic, to ensure a clean output'''
   
    fixed_deal_lengths = sum([deal_length for _, deal_length in fixed_deals])
    total_term_months = term_years * 12
   
    try:
        # Enforce contract rules strictly using the arguments passed into this function
        # Since one_off_overpayments has an int inside the type hint, we map it safely.
        MortgageDataChecker(
            purchase_price=purchase_price,
            deposit=deposit,
            term_years=term_years,
            start_date=start_date,
            fixed_deals=fixed_deals,
            variable_tracker=variable_tracker,
            overpayments=overpayments,
            one_off_overpayments=[(dt, Decimal(amt).quantize(Decimal('0.01'))) for dt, amt in one_off_overpayments]
        )
    except ValidationError as error:
        logger.error(f"Contract structural breach detected:\n{error}. ")
        return None
    except ValueError as error:
        logger.error(f"Contract business rule breach detected: {error}")
        return None

    return generate_schedule(purchase_price, deposit, term_years, start_date,
            fixed_deals, variable_tracker, overpayments, one_off_overpayments, fixed_deal_lengths, total_term_months)

def save_to_excel(df: pd.DataFrame) -> None:
    '''Function saves output to Excel file in currency format and allows '''
    
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
    one_off_overpayments = [] #When add data make sure to use "(datetime(yyy, mm , dd), 1000)" for each one-off payments

    # Get external rate data
    get_boe_rate = Decimal(str(fetch_boe_base_rate())) + DEFAULT_VARIABLE_ADD_ON
    
     
    df = validate_inputs(
        purchase_price=purchase_price,
        deposit=deposit,
        term_years=term_years,
        start_date=start_date,
        fixed_deals=my_deals,
        variable_tracker=get_boe_rate,  
        overpayments=monthly_overpayments,
        one_off_overpayments=one_off_overpayments,
    )

    pd.options.display.float_format = f'{DEFAULT_CURRENCY_SYMBOL}{{:,.2f}}'.format
    if df is not None:
        save_to_excel(df)
