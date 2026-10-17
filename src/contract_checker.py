from decimal import Decimal
from typing import Tuple, List
from datetime import datetime
from src.settings import MAX_MORTGAGE_TERM, MIN_PURCHASE_PRICE
from pydantic import BaseModel, Field, model_validator, ConfigDict, field_validator

class MortgageDataChecker(BaseModel):
    model_config = {
        'strict': True,
        'extra': 'forbid',
        'frozen': True
    }

    start_date: datetime
    purchase_price: Decimal = Field(gt=MIN_PURCHASE_PRICE)
    deposit: Decimal = Field(gt=0)
    term_years: int = Field(
        gt=0,
        le=MAX_MORTGAGE_TERM)
    
    fixed_deals: list[Tuple[Decimal, int]]
    variable_tracker: Decimal | None = Field(default=None, gt=Decimal("0"))
    overpayments: List[Tuple[datetime, Decimal]]
    one_off_overpayments: List[Tuple[datetime, Decimal]] = Field(default_factory=list)

    @field_validator('fixed_deals', mode='after')
    @classmethod
    def validate_fixed_deals(cls, deals):
        '''Reject negative rates and non-positive deal durations.'''

        for index, (rate, duration) in enumerate(deals, start=1):

            if rate <= 0:
                raise ValueError(
                    f'Fixed-rate deal Record {index} has an invalid '
                    f'interest rate of {rate}%. '
                    f'Interest rates must be greater than zero.'
                )

            if duration <= 0:
                raise ValueError(
                    f'Fixed-rate deal Record {index} has an invalid '
                    f'duration of {duration} years. '
                    f'Duration must be greater than zero.'
                )

        return deals
    
    @field_validator('one_off_overpayments', mode='after')
    @classmethod
    def validate_one_off_overpayments(cls, payments):
        """Reject duplicate one-off payments within the same calendar month."""
        existing_months = {}
        
        for index, (payment_date, amount) in enumerate(payments, start=1):
            lookup_month = (payment_date.year, payment_date.month)

            if lookup_month in existing_months:
                original_index = existing_months[lookup_month]
                raise ValueError(
                    f"Duplicate recurring one-off overpayment for "
                    f"{payment_date.strftime('%B %Y')}. "
                    f"Record {index} conflicts with Record {original_index}."
                )
            existing_months[lookup_month] = index
        return payments


    @field_validator('overpayments' , mode='after')
    @classmethod
    def enforce_unique_recurring_overpayments(cls, payments):
        """ Reject duplicate overpayments"""

        existing_months = {}

        for index, (payment_date, amount) in enumerate(payments, start=1):
            lookup_month = (payment_date.year, payment_date.month)

            if lookup_month in existing_months:
                original_index = existing_months[lookup_month]
                raise ValueError(
                    f"Duplicate recurring overpayment for "
                    f"{payment_date.strftime('%B %Y')}. "
                    f"Record {index} conflicts with Record {original_index}."
                )
            existing_months[lookup_month] = index
        return payments

    @model_validator(mode='after')
    def enforce_contracts(self) -> 'MortgageDataChecker':
        if self.deposit >= self.purchase_price:
            raise ValueError('Deposit contract violated: Deposit must be strictly less than the purchase price.')

        fixed_deal_months = sum([deal_length * 12 for _, deal_length in self.fixed_deals])
        total_term_months = self.term_years * 12

        if fixed_deal_months > total_term_months:
            raise ValueError('Term contract violated: Total length of fixed deals exceeds the mortgage term.')

        if any(amt < 0 for _, amt in self.overpayments) or any(amt < 0 for _, amt in self.one_off_overpayments):
            raise ValueError('Ledger contract violated: Overpayment amounts cannot be negative.')

        return self