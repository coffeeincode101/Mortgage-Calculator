import unittest
from decimal import Decimal, ROUND_HALF_UP, getcontext
from datetime import datetime
from pydantic import ValidationError

from src.settings import MAX_MORTGAGE_TERM, MIN_PURCHASE_PRICE, DEFAULT_VARIABLE_ADD_ON, DEFAULT_CURRENCY_SYMBOL
from src.contract_checker import MortgageDataChecker
from src.engine import MortgageCalculations
getcontext().rounding = ROUND_HALF_UP



class TestMortgageContract(unittest.TestCase):
    def setUp(self):
        """Establish a clean, baseline dictionary that perfectly conforms to the contract configuration."""
        self.valid_payload = {
            "purchase_price": Decimal("220000.00"),
            "deposit": Decimal("60000.00"),
            "term_years": 35,
            "start_date": datetime(2023, 12, 7),
            "fixed_deals": [(Decimal("4.9"), 5), (Decimal("4.2"), 2)],
            "variable_tracker": Decimal("4.25"),
            "overpayments": [(datetime(2024, 3, 1), Decimal("100.00"))],
            "one_off_overpayments": [(datetime(2024, 3, 2), Decimal("1000.00"))],
        }

    def test_valid_payload_passes_contract(self):
        """Ensure a completely clean payload initialises without any issues."""
        try:
            MortgageDataChecker(**self.valid_payload)
        except (ValidationError, ValueError) as e:
            self.fail(f"Valid payload failed validation unexpectedly: {e}")

    def test_strict_type_enforcement_blocks_floats(self):
        """Verify that strict=True blocks floats to prevent binary precision loss."""
        broken_payload = self.valid_payload.copy()
        broken_payload["purchase_price"] = 220000.00  # Raw float passed

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Input should be an instance of Decimal", str(context.exception))

    def test_strict_type_enforcement_blocks_string_integers(self):
        """Verify that string representations of numbers are rejected under strict validation."""
        broken_payload = self.valid_payload.copy()
        broken_payload["term_years"] = "35"  # String instead of int

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Input should be a valid integer", str(context.exception))

    def test_extra_forbidden_blocks_unknown_parameters(self):
        """Verify extra='forbid' isolates the contract from arbitrary metadata injections."""
        broken_payload = self.valid_payload.copy()
        broken_payload["random_extra_property"] = "malicious_or_accidental_data"

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Extra inputs are not permitted", str(context.exception))

    def test_business_contract_blocks_excessive_deposit(self):
        """Verify value constraints trigger if a deposit matches or exceeds the purchase value."""
        broken_payload = self.valid_payload.copy()
        broken_payload["deposit"] = Decimal("230000.00")  # More than purchase price

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Deposit must be strictly less than the purchase price", str(context.exception))

    def test_business_contract_blocks_excessive_fixed_deals(self):
        """Verify value constraints block structures where the deal horizons exceed the loan maturity."""
        broken_payload = self.valid_payload.copy()
        # 35 years * 12 months = 420 max. This sets up 40 years of fixed deals (480 months)
        broken_payload["fixed_deals"] = [(Decimal("4.9"), 40)]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Total length of fixed deals exceeds the mortgage term", str(context.exception))

    def test_negative_overpayments_are_blocked(self):
        """Verify that ledger values are validated to protect calculations from negative values."""
        broken_payload = self.valid_payload.copy()
        broken_payload["overpayments"] = [(datetime(2024, 3, 1), Decimal("-50.00"))]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn("Overpayment amounts cannot be negative", str(context.exception))

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
