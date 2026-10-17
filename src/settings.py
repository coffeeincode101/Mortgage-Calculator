import os
import logging
import getpass
from dotenv import load_dotenv
from decimal import Decimal

# Business Rule Constants

MAX_MORTGAGE_TERM = 40
MIN_PURCHASE_PRICE = 0
DEFAULT_VARIABLE_ADD_ON = Decimal("0.5") 
DEFAULT_CURRENCY_SYMBOL = '£'

# BoE variables
URL = 'https://www.bankofengland.co.uk/boeapps/iadb/fromshowcolumns.asp'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

load_dotenv()

def setup_logging(): 
    current_user = getpass.getuser()
    is_cloud = os.getenv('CLOUD_ENV', 'false').lower() == 'true'
    
    handlers = [logging.StreamHandler()]
    if not is_cloud:
        handlers.append(logging.FileHandler('mortgage_debug.log'))

    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
