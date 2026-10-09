from decimal import Decimal
from typing import Tuple, List
from datetime import datetime
from src.settings import MAX_MORTGAGE_TERM, MIN_PURCHASE_PRICE, DEFAULT_VARIABLE_ADD_ON, DEFAULT_CURRENCY_SYMBOL
from pydantic import BaseModel, Field, model_validator, ConfigDict

class MortgageDataChecker(BaseModel):
    model_config ={
        'strict' : True,
        'extra': 'forbid',
        'frozen':True
        }

    start_date: datetime
    purchase_price: Decimal = Field(gt=MIN_PURCHASE_PRICE)
    deposit: Decimal = Field(gt=0)
    term_years: int = Field(le=MAX_MORTGAGE_TERM)
    fixed_deals: list[Tuple[Decimal, int]]
    variable_tracker: Decimal
    overpayments:List[Tuple[datetime, Decimal]]
    one_off_overpayments: List[Tuple[datetime, Decimal]]

    @model_validator(mode='after')
    def enforce_contracts(self) -> 'MortgageDataChecker':
        #Checks deposit is not greater than  or equal to the propert price

        if self.deposit>=self.purchase_price:
            raise ValueError('Deposit contract violated: Deposit must be strictly less than the purchase price.')

        #Checks that the deal length is not greater than the term of the mortgage
        fixed_deal_months = sum([deal_length * 12 for _, deal_length in self.fixed_deals])
        total_term_months = self.term_years * 12

        if fixed_deal_months > total_term_months:
            raise ValueError('Term contract violated: Total length of fixed deals exceeds the mortgage term.')

        if any(amt < 0 for _, amt in self.overpayments) or any(amt < 0 for _, amt in self.one_off_overpayments):
            raise ValueError('Ledger contract violated: Overpayment amounts cannot be negative.')

        return self



