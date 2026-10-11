import unittest
from decimal import Decimal, ROUND_HALF_UP, getcontext
from datetime import datetime
from pydantic import ValidationError

from src.settings import MAX_MORTGAGE_TERM, MIN_PURCHASE_PRICE, DEFAULT_VARIABLE_ADD_ON, DEFAULT_CURRENCY_SYMBOL
from src.contract_checker import MortgageDataChecker
from src.engine import MortgageCalculations, generate_schedule, calculate_initial_gap_days
getcontext().rounding = ROUND_HALF_UP

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

        # Hard Math Verification using quantized 797.28:
        # Base balance = 220000 - 60000 = 160000
        # Monthly Rate (Quantized to 6 places) = 0.004083
        # Standard Monthly Interest = 160000 * 0.004083 = 653.28
        # Day Rate = (4.9 / 100) / 365 = 0.0001342465...
        # 25 Broken Days Interest = 160000 * 0.0001342465... * 25 = 536.99
        # Expected Total Interest = 653.28 + 536.99 = 1190.27
        expected_interest = Decimal('1190.27')
        self.assertEqual(
            first_row['Interest'], expected_interest,
            f"First month interest should be combined. Expected {expected_interest}, got {first_row['Interest']}"
        )

        # Verify Payment scale-up:
        # Quantized Standard Formula Payment = 797.28
        # First Month Payment = 797.28 + 25 days interest (536.99) = 1334.27
        expected_total_amount = Decimal('1334.27')
        self.assertEqual(
            first_row['Total Monthly Amount'], expected_total_amount,
            f"First payment should be scaled up. Expected {expected_total_amount}, got {first_row['Total Monthly Amount']}"
        )

        # Verify Principal remains untouched by the interest variation
        # Principal = 1334.27 - 1190.27 = 144.00
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
        self.calc = MortgageCalculations(term=12, rate=Decimal('12'), balance_remaining= Decimal('1000.00'))
    
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
            balance_remaining=small_balance
        )
        
        # 2. FIX: Call monthly_drilldown on the *final_month_calc* instance we just made!
        result = final_month_calc.monthly_drilldown(overpayments=Decimal('0'), balance=small_balance, )
        
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