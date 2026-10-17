from decimal import Decimal, ROUND_HALF_UP, getcontext, ROUND_CEILING
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import logging
import calendar
from typing import Dict, List, Any, Tuple

getcontext().rounding = ROUND_HALF_UP
logger = logging.getLogger(__name__)


class MortgageCalculations:
    """
    Calculate mortgage repayments using decimal-based amortisation.

    Determine monthly repayment amounts, interest charges, principal
    reductions and outstanding balances. Support additional overpayments,
    broken-period interest and final mortgage settlement.
    """

    TWOPLACES = Decimal("0.01")
    
    def __init__(
            self, 
            term: int, 
            rate: Decimal, 
            balance_remaining: Decimal,  
            comp_date: datetime,
            ):

        """
        Initialise mortgage calculations for a repayment period.

        Args:
            term: Remaining mortgage term expressed in months.
            rate: Annual mortgage interest rate expressed as a percentage.
            balance_remaining: Outstanding mortgage principal.
            comp_date: Original mortgage completion date used to determine
                the daily interest divisor for the broken-interest period.
        """

        self.term = term
        balance_clean = balance_remaining.quantize(self.TWOPLACES)
        raw_rate = (rate / Decimal("100")) / Decimal("12")

        # FIXED: Dynamically toggle between 365 and 366 based on the completion year
        days_in_year = 366 if calendar.isleap(comp_date.year) else 365

        self.day_rate = (rate / Decimal("100")) / Decimal(str(days_in_year))
        self.monthly_interest = raw_rate
        # Calculate baseline payment with standard clean inputs
        self.monthly_total_payment = self.calculate_monthly_payment(balance_clean)
        logger.info(f'Initialised new calculation period using {rate}% , Term is {term} months')

    def calculate_monthly_payment(self, balance: Decimal) -> Decimal:
        """
        Calculate the baseline monthly mortgage repayment.

        Apply the standard amortisation formula using the outstanding
        principal, monthly interest rate and remaining repayment term.
        Handle zero-interest mortgages and non-positive repayment terms.

        Args:
            balance: Outstanding mortgage principal.

        Returns:
            The calculated monthly repayment as a Decimal, rounded to
            two decimal places. Positive-term repayments are rounded
            upwards when the standard amortisation formula is used.
        """
        
        monthly_rate = self.monthly_interest
        one = Decimal("1")
        
        if self.term <= 0:
            return Decimal(balance).quantize(self.TWOPLACES)
        if monthly_rate == 0:
            return Decimal(balance / Decimal(str(self.term))).quantize(self.TWOPLACES)
            
        common = (one + monthly_rate) ** self.term
        monthly_total_payment = (balance * (monthly_rate * common)) / (common - one)
        
        return Decimal(str(monthly_total_payment)).quantize(self.TWOPLACES, rounding=ROUND_CEILING)

    def monthly_drilldown(
            self, 
            overpayments: Decimal, 
            balance: Decimal, 
            initial_days_accrued: int = 0, # Represents the broken completion month days
            is_last_month: bool = False, 
            is_first_month: bool = False,
            ) -> Dict[str, Any]:
        """
        Calculate the monthly mortgage repayment breakdown.

        Determine the interest charged, principal repaid and remaining
        mortgage balance for a single repayment period. Account for
        additional overpayments, broken-period interest during the
        first repayment month and adjustments required to settle
        the outstanding balance in the final repayment period.

        Args:
            overpayments: Additional amount paid towards the mortgage
                principal during the current repayment period.
            balance: Outstanding mortgage principal before repayment.
            initial_days_accrued: Number of broken-period interest days
                accrued during the completion month. Defaults to 0.
            is_last_month: Whether the current period is the final
                scheduled mortgage repayment month. Defaults to False.
            is_first_month: Whether the current period is the first
                repayment month, requiring broken-period interest.
                Defaults to False.

        Returns:
            A dictionary containing the repayment breakdown:

                Total Monthly Amount: Total amount payable for the period.
                Principal: Total principal reduction, including overpayments.
                Interest: Interest charged during the repayment period.
                Overpayments: Additional payment applied to the principal.
                Raw Balance: Outstanding principal after repayment.
                Balance: Outstanding principal after repayment.

            All monetary values are Decimal instances rounded to
            two decimal places."""

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
        # Calculate the remaining principal before clearing the balance.
            remaining_principal = max(
                Decimal("0.00"),
                balance - principal_from_payment
            )
            # Cap the overpayment to the amount actually required.
            overpayments = min(overpayments, remaining_principal)

            amt = (balance + interest_amount).quantize(self.TWOPLACES)
            total_principal_reduction = balance
            balance = Decimal("0.00")

            logger.info("Final payment processed. Balance cleared to zero.")
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
    Calculate the inclusive broken-period days following completion.

    Determine the number of calendar days between the mortgage
    completion date and the final day of the completion month,
    including the completion date itself.

    Args:
        start_date: Date on which the mortgage completes.

    Returns:
        Number of calendar days in the initial broken-interest period.
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
    """
    Generate a mortgage repayment schedule across successive rate periods.

    Process fixed-rate deals and an optional variable-rate period,
    recalculating monthly repayments at each rate transition using
    the outstanding balance and remaining mortgage term.

    Apply recurring and one-off overpayments, account for initial
    broken-period interest and stop when the mortgage is fully repaid
    or the configured rate periods are exhausted.

    Args:
        purchase_price: Total purchase price of the property.
        deposit: Initial deposit deducted from the purchase price.
        term_years: Original mortgage repayment term in years.
        start_date: Mortgage completion date.
        fixed_deals: List of tuples containing annual interest rates
            and their respective fixed-period durations in years.
        variable_tracker: Annual interest rate applied after the
            fixed-rate periods, expressed as a percentage.
        overpayments: List of tuples specifying the effective date
            and amount of recurring monthly overpayments.
        one_off_overpayments: List of tuples specifying the date
            and amount of individual additional repayments.
        fixed_deal_lengths: Combined duration of fixed-rate deals
            expressed in years.
        months_remaining: Remaining mortgage repayment term in months.

    Returns:
        A pandas DataFrame containing the monthly repayment schedule,
        including dates, total payments, principal reductions,
        interest charges, overpayments and outstanding balances.
    """

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
        if variable_tracker is None:
            raise ValueError(
                'Variable tracker rate is required when fixed-rate'
                'deals do not cover the full mortgage term.'
            )
        
        all_deals.append((variable_tracker, variable_months))

    for rate, deal_length in all_deals:
        months = deal_length * 12
        calc_monthly = MortgageCalculations(months_remaining, rate, balance, comp_date=start_date)

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
