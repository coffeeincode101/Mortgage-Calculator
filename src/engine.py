from decimal import Decimal, ROUND_HALF_UP, getcontext
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import logging
import calendar
from typing import Dict, List, Any, Tuple

getcontext().rounding = ROUND_HALF_UP
logger = logging.getLogger(__name__)


class MortgageCalculations:
    TWOPLACES = Decimal("0.01")
    
    def __init__(self, term: int, rate: Decimal, balance_remaining: Decimal, start_date: datetime):
        self.term = term
        balance_clean = balance_remaining.quantize(self.TWOPLACES)
        raw_rate = (rate / Decimal("100")) / Decimal("12")

        # FIXED: Dynamically toggle between 365 and 366 based on the completion year
        days_in_year = 366 if calendar.isleap(start_date.year) else 365

        self.day_rate = (rate / Decimal("100")) / Decimal(str(days_in_year))
        self.monthly_interest = raw_rate.quantize(Decimal("0.000001"))
        # Calculate baseline payment with standard clean inputs
        self.monthly_total_payment = self.calculate_monthly_payment(balance_clean)
        logger.info(f'Initialised new calculation period using {rate}% , Term is {term} months')

    def calculate_monthly_payment(self, balance: Decimal) -> Decimal:
        '''Calculates the fixed baseline monthly amount using the standard amortization formula'''
        monthly_rate = self.monthly_interest
        one = Decimal("1")
        
        if self.term <= 0:
            return Decimal(balance).quantize(self.TWOPLACES)
        if monthly_rate == 0:
            return Decimal(balance / Decimal(str(self.term))).quantize(self.TWOPLACES)
            
        common = (one + monthly_rate) ** self.term
        monthly_total_payment = (balance * (monthly_rate * common)) / (common - one)
        
        return Decimal(str(monthly_total_payment)).quantize(self.TWOPLACES)

    def monthly_drilldown(
            self, 
            overpayments: Decimal, 
            balance: Decimal, 
            initial_days_accrued: int = 0, # Represents the broken completion month days
            is_last_month: bool = False, 
            is_first_month: bool = False,
            ) -> Dict[str, Any]:
        '''Breaks down the monthly amount by interest, overpayment and updates the remaining balance'''

        overpayments = (overpayments).quantize(self.TWOPLACES)
        balance = (balance).quantize(self.TWOPLACES)

        # Base interest component for a standard full calendar payment period
        standard_monthly_interest = (balance * self.monthly_interest).quantize(self.TWOPLACES)

        if is_first_month:
            # 25 days of broken daily interest PLUS full upcoming standard month interest run
            extra_broken_days_interest = (balance * self.day_rate * Decimal(str(initial_days_accrued))).quantize(self.TWOPLACES)
            interest_amount = standard_monthly_interest + extra_broken_days_interest
            
            # Elevate the payment collected to handle the added broken days safely
            monthly_payment_cast = Decimal(str(self.monthly_total_payment)) + extra_broken_days_interest
        else:
            interest_amount = standard_monthly_interest
            monthly_payment_cast = Decimal(str(self.monthly_total_payment))

        monthly_payment_cast = monthly_payment_cast.quantize(self.TWOPLACES)
        principal_from_payment = (monthly_payment_cast - interest_amount).quantize(self.TWOPLACES)
        total_principal_reduction = (principal_from_payment + overpayments).quantize(self.TWOPLACES)     

        # TRAP DOOR: If the principal covers it OR we're dynamically flagged as the last calendar month
        if total_principal_reduction >= balance or is_last_month:
            amt = (balance + interest_amount).quantize(self.TWOPLACES)
            total_principal_reduction = balance.quantize(self.TWOPLACES)
            balance = Decimal("0.00")
            overpayments = Decimal("0.00")
            logger.info(f'Final payment process triggered. Balance cleared to zero.')
        else:
            amt = Decimal(monthly_payment_cast + overpayments).quantize(self.TWOPLACES)
            balance = Decimal(balance - total_principal_reduction).quantize(self.TWOPLACES)
            logger.debug(f'Monthly payment processed. New balance: {balance}')

        return {
            "Total Monthly Amount": amt,
            "Principal": total_principal_reduction,
            "Interest": interest_amount,
            "Overpayments": overpayments,
            "Raw Balance": balance,
            "Balance": balance,
        }


def calculate_initial_gap_days(start_date: datetime) -> int:
    """
    Finds the total count of broken initial days from completion date 
    up to the final day of that initial month (inclusive).
    """
    # For a start date of 07/12/2023, this accurately isolates 31/12/2023
    end_of_completion_month = (start_date + relativedelta(months=1)).replace(day=1) - relativedelta(days=1)
    
    # Mathematical delta (07/12 to 31/12 = 24 days. Banks add 1 day to cover the completion day itself = 25)
    return (end_of_completion_month - start_date).days + 1


def generate_schedule(
    purchase_price: Decimal,
    deposit: Decimal,
    term_years: int,
    start_date: datetime,
    fixed_deals: List[Tuple[Decimal, int]],
    variable_tracker: Decimal,
    overpayments: List[Tuple[datetime, Decimal]],
    one_off_overpayments: List[Tuple[datetime, Decimal]],
    fixed_deal_lengths: int,
    months_remaining: int
) -> pd.DataFrame:
    """Creates the separate buckets for each fixed deal entered."""

    TWOPLACES = Decimal("0.01")
    schedule = []
    balance = (Decimal(str(purchase_price)) - Decimal(str(deposit))).quantize(TWOPLACES)
    
    # Sets the calendar pointer for the first payment date to 01st of the following month
    cur_month = (start_date + relativedelta(months=1)).replace(day=1)
    
    all_deals = list(fixed_deals)
    ongoing_monthly_extra = Decimal("0.00")
    extra_amount_map = {date.replace(day=1): Decimal(str(amount)).quantize(TWOPLACES) for date, amount in overpayments}
    one_off_extra_map = {
        date.replace(day=1): Decimal(str(amount)).quantize(TWOPLACES) for date, amount in one_off_overpayments
    }
    
    # Count from completion day to first payment (e.g. 25 days)
    initial_gap_days = calculate_initial_gap_days(start_date)
    logger.info(f"Calculated {initial_gap_days} extra broken days inside the completion month.")

    if fixed_deal_lengths < term_years:
        variable_months = int((term_years - fixed_deal_lengths))
        if variable_tracker:
            all_deals.append((variable_tracker, variable_months))

    for rate, deal_length in all_deals:
        months = deal_length * 12
        calc_monthly = MortgageCalculations(months_remaining, rate, balance, start_date=cur_month)

        for _ in range(months):
            if balance <= 0:
                break

            lookup_date = cur_month.replace(day=1)
            is_first = (months_remaining == (term_years * 12))
          
            if lookup_date in extra_amount_map:
                ongoing_monthly_extra = extra_amount_map[lookup_date]

            one_off = one_off_extra_map.get(lookup_date, Decimal("0.00"))
            extra_payment = Decimal(ongoing_monthly_extra + one_off).quantize(TWOPLACES)
            
            is_last = (months_remaining == 1)
            
            # Pass the accurate broken day count metric cleanly into the drilldown executor
            result = calc_monthly.monthly_drilldown(
                extra_payment, 
                balance, 
                initial_days_accrued=initial_gap_days, 
                is_last_month=is_last, 
                is_first_month=is_first
            )
            balance = result['Raw Balance'] 
            
            schedule.append(
                {
                    "Date": cur_month.strftime("%b - %Y"),
                    "Total Monthly Amount": result["Total Monthly Amount"],
                    "Principal": result["Principal"],
                    "Interest": result["Interest"],
                    "Overpayments": result["Overpayments"],
                    "Balance": result["Balance"]
                }
            )

            months_remaining -= 1
            cur_month += relativedelta(months=1)
            
            if balance <= 0:
                break

    return pd.DataFrame(schedule)
