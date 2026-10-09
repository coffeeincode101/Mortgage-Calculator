import requests
import csv
from typing import Tuple, Optional
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from io import StringIO
from pathlib import Path
import os
import json
import logging
from utils import time_it

# Grab a logger specific to this file
logger = logging.getLogger(__name__)

URL = 'https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def get_default_dates() -> Tuple[str, str]:
    
    '''Date helper function that establishes today as the end_date and start_date as 7 days prior.'''
    end_date = date.today()
    start_date = end_date - relativedelta(
        days=7
    )  # Limits data sent back for only last 7 days to improve speed.
   
    return start_date.strftime('%d/%b/%Y'), end_date.strftime('%d/%b/%Y')


def parse_boe_rates(csv_text: str) -> Optional[float]:
    '''Parses responses from get_boe_rates and extracts the latest Bank of England rate'''

    f = StringIO(csv_text.strip())
    reader = csv.DictReader(f)
    data = list(reader)

    if not data:
        return None  # Handle empty response

    latest_row = data[0]

    try:

        raw_values = float(
            latest_row.get('Bank Rate')
            or latest_row.get('Value')
            or latest_row.get('IUDBEDR')
        )
        return float(raw_values) if raw_values is not None else None
    except (ValueError, TypeError):
        return None


def get_boe_rate(
    start_date: str, end_date: str, url=URL
) -> Optional[Tuple[dict, dict]]:
    successful_records = {}
    invalid_records = {}
    # Define this at the VERY top so all blocks can see it
    date_assessed = datetime.now().strftime('%d-%m-%Y')
    boe_rate = None

    params = {
        'csv.x': 'yes',
        'Datefrom': start_date,
        'Dateto': end_date,
        'SeriesCodes': 'IUDBEDR',
        'CSVF': 'TN',
        'UsingCodes': 'Y',
        'VPD': 'Y',
        'VOM': 'ALL',
    }

    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        boe_rate = parse_boe_rates(response.text)
    except Exception as e:
        # Use f-string to avoid TypeError when adding Exception to String
        invalid_records['Failed Rates'] = {
            'Rate': boe_rate,
            'Date accessed': date_assessed,
            'Failure Reason': f'Failed attempt. Error: {e}',
        }
        return ({}, invalid_records)

    if boe_rate is not None:
        successful_records['Successful Rates'] = {
            'Rate': boe_rate,
            'Date accessed': date_assessed,
        }
    else:
        invalid_records['Failed Rates'] = {
            'Rate': None,
            'Date accessed': date_assessed,
            'Failure Reason': 'Empty Rate',
        }
    return (successful_records, invalid_records)


def load_db(file_path: Path) -> dict:
    '''Handles file I/O: Loading the JSON.'''
    if file_path.exists():
        with open(file_path, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    return {'Successful': [], 'Failed': []}


def save_db(file_path: Path, db: dict):
    '''Handles file I/O: Saving the JSON.'''
    with open(file_path, 'w') as f:
        json.dump(db, f, indent=4)


def get_effective_rate(new_entry: dict, history: list) -> float:
    '''Pure Logic: Determines which rate to use.'''
    # 1. Try Live
    if new_entry and new_entry.get('Rate') is not None:

        return new_entry['Rate']

    # 2. Try History
    if history:
        last_rate = history[-1].get('Rate')

        return last_rate

    # 3. Fail
    raise ValueError('CRITICAL: No live or historical rate available.')

@time_it
def setup():
    script_dir = Path(__file__).resolve().parent.parent
    file_path = script_dir / 'data'/ 'boe_rate.json'

    # 1. Load existing data first
    db = load_db(file_path)
    history = db.get('Successful', [])

    # 2. Check: Is the last entry fresh? (Within 5 days)
    if history:
        last_entry = history[-1]
        last_date_str = last_entry.get('Date accessed')
        last_date = datetime.strptime(last_date_str, '%d-%m-%Y').date()

        days_since = (date.today() - last_date).days

        if days_since <= 5:
            logger.info(f" Using cached data ({days_since} days old): {last_entry['Rate']}%")
            return last_entry['Rate']

    # 3. If no history or data is old, Scrape live
    
    logger.info('Data is older than 5 days. Attempting to fetch live BoE rates...')

    boe_start, boe_end = get_default_dates()

    result = get_boe_rate(boe_start, boe_end)

    if not result:
        logger.warning('Scraper returned no data. Attempting fallback to history.')
        return get_effective_rate(None, history)

    success_data, failed_data = result
    new_rate_entry = success_data.get('Successful Rates')

    # 4. Save and return
    if new_rate_entry:
        logger.info(f"Successfully fetched live rate: {new_rate_entry['Rate']}%")
        db['Successful'].append(new_rate_entry)

    if failed_data.get('Failed Rates'):
        # You only need this once!
        logger.error(f"BoE Scrape failed: {failed_data['Failed Rates'].get('Failure Reason')}")
        db['Failed'].append(failed_data['Failed Rates'])

    save_db(file_path, db)

    # get_effective_rate handles the final logic of which rate to return
    return get_effective_rate(new_rate_entry, db['Successful'])


if __name__ == '__main__':

    setup()
