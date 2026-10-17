import unittest
import calendar
from decimal import Decimal, ROUND_HALF_UP, getcontext
from datetime import datetime
from pydantic import ValidationError

from src.settings import MAX_MORTGAGE_TERM, MIN_PURCHASE_PRICE, DEFAULT_VARIABLE_ADD_ON, DEFAULT_CURRENCY_SYMBOL
from src.contract_checker import MortgageDataChecker
from src.engine import MortgageCalculations, generate_schedule, calculate_initial_gap_days
getcontext().rounding = ROUND_HALF_UP

class RunMortgageSchedule(unittest.TestCase):

    def setUp(self):
        """Establish baseline mortgage parameters for schedule testing."""

        self.term_years = 35
        self.term_months = self.term_years * 12
        self.interest_rate = Decimal("4.5")
        self.balance = Decimal("200000.00")
        self.start_date = datetime(2024, 1, 10)

        self.purchase_price = Decimal("250000.00")
        self.deposit = Decimal("50000.00")

        self.fixed_deals = [(self.interest_rate, 35)]

    def test_full_amortisation(self):

        baseline = generate_schedule(
            purchase_price=self.purchase_price,
            deposit=self.deposit,
            term_years=self.term_years,
            start_date=self.start_date,
            fixed_deals=self.fixed_deals,
            variable_tracker=None,
            overpayments=[],
            one_off_overpayments=[],
            fixed_deal_lengths=self.term_years,
            months_remaining=self.term_months
        )

        self.assertFalse(baseline.empty)

        self.assertEqual(
            baseline.iloc[-1]['Balance'],
            Decimal('0.00')
        )

        self.assertTrue(
            all(
                baseline.iloc[i]['Balance'] <= baseline.iloc[i-1]['Balance']
                for i in range(1, len(baseline))
            )
        )

        self.assertEqual(
            sum(baseline['Principal']),
            self.balance
        )

        self.assertTrue(
            all(amount == Decimal("0.00") for amount in baseline["Overpayments"])
        )

        self.assertLessEqual(len(baseline), self.term_months)

    def test_overpayments(self):
            
        baseline_with_overpayments = generate_schedule(
            purchase_price=self.purchase_price,
            deposit=self.deposit,
            term_years=self.term_years,
            start_date=self.start_date,
            fixed_deals=self.fixed_deals,
            variable_tracker=None,
            overpayments=[(datetime(2024, 2, 1), Decimal('100.00'))],
            one_off_overpayments=[],
            fixed_deal_lengths=self.term_years,
            months_remaining=self.term_months,
        )

        self.assertFalse(baseline_with_overpayments.empty)

        self.assertEqual(
            baseline_with_overpayments.iloc[0]['Overpayments'], 
            Decimal('100.00')
        )

        self.assertEqual(
            baseline_with_overpayments.iloc[1]['Overpayments'],
            Decimal("100.00")
        )

        self.assertEqual(
            baseline_with_overpayments.iloc[-1]['Balance'],
            Decimal('0.00') 
        )

        self.assertEqual(
            sum(baseline_with_overpayments["Principal"]),
            self.balance
        )

        # Verify the mortgage finishes before its original term.
        self.assertLess(
            len(baseline_with_overpayments),
            self.term_months,
        )

class TestMortgageLeapYearLogic(unittest.TestCase):

    def setUp(self):
        """Set up boilerplate baseline parameters for class instantiations."""
        self.term_months = 360
        self.rate = Decimal('4.5')  # 4.5% interest rate
        self.balance = Decimal('150000')

    def test_day_rate_divisor_for_regular_year(self):
        """Verify that a non-leap year (2023) correctly utilizes a 365-day engine divisor."""
        regular_date = datetime(2023, 6, 15)
        
        # Ensure the calendar utility confirms it is a normal year
        self.assertFalse(calendar.isleap(regular_date.year))

        calc_regular = MortgageCalculations(
            term=self.term_months,
            rate=self.rate,
            balance_remaining=self.balance,
            comp_date=regular_date
        )

        # Expected Math: (4.5 / 100) / 365 = 0.045 / 365
        expected_regular_rate = (self.rate / Decimal('100')) / Decimal('365')
        
        self.assertEqual(
            calc_regular.day_rate, 
            expected_regular_rate,
            f"Regular year daily rate mismatch. Expected division by 365, got raw day rate: {calc_regular.day_rate}"
        )

    def test_day_rate_divisor_for_leap_year(self):
        """Verify that a leap year (2024) dynamically switches to a 366-day engine divisor."""
        leap_date = datetime(2024, 2, 20)
        
        # Ensure the calendar utility confirms it is a leap year
        self.assertTrue(calendar.isleap(leap_date.year))

        calc_leap = MortgageCalculations(
            term=self.term_months,
            rate=self.rate,
            balance_remaining=self.balance,
            comp_date=leap_date
        )

        # Expected Math: (4.5 / 100) / 366 = 0.045 / 366
        expected_leap_rate = (self.rate / Decimal('100')) / Decimal('366')
        
        self.assertEqual(
            calc_leap.day_rate, 
            expected_leap_rate,
            f"Leap year daily rate mismatch. Expected division by 366, got raw day rate: {calc_leap.day_rate}"
        )
        
        # Verify the leap day rate is lower than the regular day rate due to the higher denominator
        expected_regular_rate = (self.rate / Decimal('100')) / Decimal('365')
        self.assertLess(
            calc_leap.day_rate, 
            expected_regular_rate,
            "Leap year daily rate should be strictly lower than standard year daily rate due to 366 days division."
        )

class TestMortgageEngine(unittest.TestCase):

    def setUp(self):
        '''Set up standard test inputs matching the application state.'''
        self.purchase_price = Decimal('220000')
        self.deposit = Decimal('60000')
        self.term_years = 35
        self.start_date = datetime(2023, 12, 7)
        self.fixed_deals = [(Decimal('4.9'), 5)]  # 4.9% for 5 years
        self.variable_tracker = Decimal('3.75')
        self.overpayments = []
        self.one_off_overpayments = []
        self.fixed_deal_lengths = 5
        self.total_months = self.term_years * 12

    def test_calculate_initial_gap_days(self):
        '''Verify that the broken days calculation inside December is exactly 25 days.'''
        # 7th Dec to 31st Dec inclusive = (31 - 7) + 1 = 25 days
        gap_days = calculate_initial_gap_days(self.start_date)
        self.assertEqual(gap_days, 25, f'Expected 25 broken days, got {gap_days}')

    def test_first_month_combined_payment_and_interest(self):
        '''
        Verify that the first schedule row (Jan 2024) calculates elevated 
        interest and an elevated total monthly payment to cover the broken period.
        '''
        df = generate_schedule(
            purchase_price=self.purchase_price,
            deposit=self.deposit,
            term_years=self.term_years,
            start_date=self.start_date,
            fixed_deals=self.fixed_deals,
            variable_tracker=self.variable_tracker,
            overpayments=self.overpayments,
            one_off_overpayments=self.one_off_overpayments,
            fixed_deal_lengths=self.fixed_deal_lengths,
            months_remaining=self.total_months
        )

        # Ensure we received data back
        self.assertFalse(df.empty, 'The generated schedule DataFrame is empty.')
        
        # Isolate the very first row (Jan - 2024) & check correct month
        first_row = df.iloc[0]
        self.assertEqual(first_row['Date'], 'Jan - 2024')


        expected_interest = Decimal('1190.32')
        self.assertEqual(
            first_row['Interest'], expected_interest,
            f"First month interest should be combined. Expected {expected_interest}, got {first_row['Interest']}"
        )

        # Verify Payment scale-up:
        expected_total_amount = Decimal('1334.32')
        self.assertEqual(
            first_row['Total Monthly Amount'], expected_total_amount,
            f"First payment should be scaled up. Expected {expected_total_amount}, got {first_row['Total Monthly Amount']}"
        )

        # Verify Principal remains untouched by the interest variation
        expected_principal = Decimal('144.00')
        self.assertEqual(
            first_row['Principal'], expected_principal,
            f"Principal reduction should stay aligned. Expected {expected_principal}, got {first_row['Principal']}"
        )

class TestMortgageContract(unittest.TestCase):
    def setUp(self):
        '''Establish a clean, baseline dictionary that perfectly conforms to the contract configuration.'''
        self.valid_payload = {
            'purchase_price': Decimal('220000.00'),
            'deposit': Decimal('60000.00'),
            'term_years': 35,
            'start_date': datetime(2023, 12, 7),
            'fixed_deals': [(Decimal('4.9'), 5), (Decimal('4.2'), 2)],
            'variable_tracker': Decimal('4.25'),
            'overpayments': [(datetime(2024, 3, 1), Decimal('100.00'))],
            'one_off_overpayments': [(datetime(2024, 3, 2), Decimal('1000.00'))],
        }

    def test_valid_payload_passes_contract(self):
        '''Ensure a completely clean payload initialises without any issues.'''
        try:
            MortgageDataChecker(**self.valid_payload)
        except (ValidationError, ValueError) as e:
            self.fail(f'Valid payload failed validation unexpectedly: {e}')

    def test_strict_type_enforcement_blocks_floats(self):
        '''Verify that strict=True blocks floats to prevent binary precision loss.'''
        broken_payload = self.valid_payload.copy()
        broken_payload['purchase_price'] = 220000.00  # Raw float passed

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Input should be an instance of Decimal', str(context.exception))

    def test_strict_type_enforcement_blocks_string_integers(self):
        '''Verify that string representations of numbers are rejected under strict validation.'''
        broken_payload = self.valid_payload.copy()
        broken_payload['term_years'] = '35'  # String instead of int

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Input should be a valid integer', str(context.exception))

    def test_extra_forbidden_blocks_unknown_parameters(self):
        '''Verify extra='forbid' isolates the contract from arbitrary metadata injections.'''
        broken_payload = self.valid_payload.copy()
        broken_payload['random_extra_property'] = 'malicious_or_accidental_data'

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Extra inputs are not permitted', str(context.exception))

    def test_business_contract_blocks_excessive_deposit(self):
        '''Verify value constraints trigger if a deposit matches or exceeds the purchase value.'''
        broken_payload = self.valid_payload.copy()
        broken_payload['deposit'] = Decimal('230000.00')  # More than purchase price

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Deposit must be strictly less than the purchase price', str(context.exception))

    def test_business_contract_blocks_excessive_fixed_deals(self):
        '''Verify value constraints block structures where the deal horizons exceed the loan maturity.'''
        broken_payload = self.valid_payload.copy()
        # 35 years * 12 months = 420 max. This sets up 40 years of fixed deals (480 months)
        broken_payload['fixed_deals'] = [(Decimal('4.9'), 40)]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Total length of fixed deals exceeds the mortgage term', str(context.exception))

    def test_negative_overpayments_are_blocked(self):
        '''Verify that ledger values are validated to protect calculations from negative values.'''
        broken_payload = self.valid_payload.copy()
        broken_payload['overpayments'] = [(datetime(2024, 3, 1), Decimal('-50.00'))]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Overpayment amounts cannot be negative', str(context.exception))

class TestMortgageMath(unittest.TestCase):
    def setUp(self):
        self.calc = MortgageCalculations(term=12, rate=Decimal('12'), balance_remaining= Decimal('1000.00'), comp_date=datetime(2023, 12, 7))
    
    def test_monthly_interest(self):
        # Test example has a monthly interest of 1% (12% / 12 months = 1% interest a month). 1% of 1000 is 10
        result = self.calc.monthly_drilldown(overpayments=Decimal('0'),balance=Decimal('1000.00'))
        self.assertEqual(result['Interest'], Decimal('10.00'))
    
    def test_final_payment(self):
        small_balance = Decimal('90.00').quantize(Decimal('0.01'))
        
        # 1. Initialize a specific calculator instance for this test
        final_month_calc = MortgageCalculations(
            term=1, 
            rate=Decimal('5.0'), 
            balance_remaining=small_balance,
            comp_date=datetime(2023, 12, 7)  
        )
        
        # 2. FIX: Call monthly_drilldown on the *final_month_calc* instance we just made!
        result = final_month_calc.monthly_drilldown(overpayments=Decimal('0'), balance=small_balance,)
        
        # 3. Assertions
        self.assertEqual(result['Balance'], Decimal('0.00'))
        
        # Now this will correctly use the 5.0% rate configured above
        expected_interest = (small_balance * final_month_calc.monthly_interest).quantize(Decimal('0.01'))
        expected_bill = (small_balance + expected_interest).quantize(Decimal('0.01'))
        
        self.assertEqual(result['Total Monthly Amount'], expected_bill)
    
    def test_overpayment(self):
        start_balance = Decimal('1000.00')
        overpayment = Decimal('100.00')
        result = self.calc.monthly_drilldown(overpayments=overpayment, balance=start_balance)

        expected_value = (self.calc.monthly_total_payment - Decimal('10.00')) + overpayment

        self.assertEqual(result['Principal'], expected_value.quantize(Decimal('0.01')), )

if __name__== '__main__':
    unittest.main()