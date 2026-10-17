import calendar
import json
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests
from pydantic import ValidationError

from src.boe_scraper import load_db, save_db, setup
from src.contract_checker import MortgageDataChecker
from src.engine import (
    MortgageCalculations,
    calculate_initial_gap_days,
    generate_schedule,
)


getcontext().rounding = ROUND_HALF_UP


class RunMortgageSchedule(unittest.TestCase):

    def setUp(self):
        """Establish baseline mortgage parameters for schedule testing."""

        self.term_years = 35
        self.term_months = self.term_years * 12
        self.interest_rate = Decimal('4.5')
        self.balance = Decimal('200000.00')
        self.start_date = datetime(2024, 1, 10)

        self.purchase_price = Decimal('250000.00')
        self.deposit = Decimal('50000.00')

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
                baseline.iloc[i]['Balance'] <= baseline.iloc[i - 1]['Balance']
                for i in range(1, len(baseline))
            )
        )

        self.assertEqual(
            sum(baseline['Principal']),
            self.balance
        )

        self.assertTrue(
            all(
                amount == Decimal('0.00')
                for amount in baseline['Overpayments']
            )
        )

        self.assertLessEqual(len(baseline), self.term_months)

    def test_fixed_rate_transition(self):
        """Verify recalculation when transitioning between fixed-rate deals."""

        # Arrange: Two consecutive fixed-rate periods.
        term_years = 2
        first_rate = Decimal('4.5')
        second_rate = Decimal('3.0')

        fixed_deals = [
            (first_rate, 1),
            (second_rate, 1),
        ]

        # Act: Generate the complete repayment schedule.
        schedule = generate_schedule(
            purchase_price=self.purchase_price,
            deposit=self.deposit,
            term_years=term_years,
            start_date=self.start_date,
            fixed_deals=fixed_deals,
            variable_tracker=None,
            overpayments=[],
            one_off_overpayments=[],
            fixed_deal_lengths=2,
            months_remaining=24
        )

        # Assert: The schedule contains all 24 months.
        self.assertEqual(len(schedule), 24)

        # Verify the transition occurs in the correct month.
        self.assertEqual(schedule.iloc[11]['Date'], 'Jan - 2025')
        self.assertEqual(schedule.iloc[12]['Date'], 'Feb - 2025')

        # Verify month 12 uses the original 4.5% rate.
        balance_month_11 = schedule.iloc[10]['Balance']

        expected_first_interest = (
            balance_month_11 * first_rate / Decimal('1200')
        ).quantize(Decimal('0.01'))

        self.assertEqual(
            schedule.iloc[11]['Interest'],
            expected_first_interest
        )

        # Verify month 13 uses the new 3.0% rate.
        balance_month_12 = schedule.iloc[11]['Balance']

        expected_second_interest = (
            balance_month_12 * second_rate / Decimal('1200')
        ).quantize(Decimal('0.01'))

        self.assertEqual(
            schedule.iloc[12]['Interest'],
            expected_second_interest
        )

        # Verify monthly repayment decreases after the rate reduction.
        self.assertLess(
            schedule.iloc[12]['Total Monthly Amount'],
            schedule.iloc[11]['Total Monthly Amount']
        )

        # Verify the mortgage is completely repaid.
        self.assertEqual(
            schedule.iloc[-1]['Balance'],
            Decimal('0.00')
        )

        # Verify all original principal has been repaid.
        self.assertEqual(
            sum(schedule['Principal']),
            self.balance
        )

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
            Decimal('100.00')
        )

        self.assertEqual(
            baseline_with_overpayments.iloc[-1]['Balance'],
            Decimal('0.00')
        )

        self.assertEqual(
            sum(baseline_with_overpayments['Principal']),
            self.balance
        )

        # Verify the mortgage finishes before its original term.
        self.assertLess(
            len(baseline_with_overpayments),
            self.term_months,
        )

    def test_zero_variable_tracker(self):
        """Verify a 0% variable rate is processed correctly."""

        schedule = generate_schedule(
            purchase_price=self.purchase_price,
            deposit=self.deposit,
            term_years=2,
            start_date=self.start_date,
            fixed_deals=[(self.interest_rate, 1)],
            variable_tracker=Decimal('0.00'),
            overpayments=[],
            one_off_overpayments=[],
            fixed_deal_lengths=1,
            months_remaining=24
        )

        # Verify the entire mortgage schedule is generated.
        self.assertEqual(len(schedule), 24)

        # Verify the variable-rate period charges no interest.
        self.assertTrue(
            all(
                interest == Decimal('0.00')
                for interest in schedule.iloc[12:]['Interest']
            )
        )

        # Verify the mortgage is fully repaid.
        self.assertEqual(
            schedule.iloc[-1]['Balance'],
            Decimal('0.00')
        )

    def test_missing_variable_tracker(self):
        """Verify missing required tracker rates raise ValueError."""

        with self.assertRaisesRegex(
            ValueError,
            'Variable tracker rate is required'
        ):
            generate_schedule(
                purchase_price=self.purchase_price,
                deposit=self.deposit,
                term_years=2,
                start_date=self.start_date,
                fixed_deals=[(self.interest_rate, 1)],
                variable_tracker=None,
                overpayments=[],
                one_off_overpayments=[],
                fixed_deal_lengths=1,
                months_remaining=24
            )


class TestMortgageLeapYearLogic(unittest.TestCase):

    def setUp(self):
        """Set up boilerplate baseline parameters for class instantiations."""
        self.term_months = 360
        self.rate = Decimal('4.5')  # 4.5% interest rate
        self.balance = Decimal('150000')

    def test_day_rate_divisor_for_regular_year(self):
        """Verify the engine uses 365 days in a non-leap year."""
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
            (
                'Regular year daily rate mismatch. '
                'Expected division by 365, '
                f'got raw day rate: {calc_regular.day_rate}'
            ),
        )

    def test_day_rate_divisor_for_leap_year(self):
        """Verify the engine uses 366 days in a leap year."""
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
            (
                'Leap year daily rate mismatch. '
                'Expected division by 366, '
                f'got raw day rate: {calc_leap.day_rate}'
            ),
        )

        # A 366-day divisor must produce a smaller daily rate.
        expected_regular_rate = (self.rate / Decimal('100')) / Decimal('365')
        self.assertLess(
            calc_leap.day_rate,
            expected_regular_rate,
            (
                'Leap year daily rate should be strictly lower than standard '
                'year daily rate due to 366 days division.'
            ),
        )


class TestMortgageEngine(unittest.TestCase):

    def setUp(self):
        """Set up standard test inputs matching the application state."""
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
        """Verify that December completion produces 25 broken days."""
        # 7th Dec to 31st Dec inclusive = (31 - 7) + 1 = 25 days
        gap_days = calculate_initial_gap_days(self.start_date)
        self.assertEqual(
            gap_days, 25, f'Expected 25 broken days, got {gap_days}'
        )

    def test_first_month_combined_payment_and_interest(self):
        """Verify January's payment includes completion-period interest.

        The first payment includes both the standard monthly interest and
        interest accrued during the broken completion month.
        """
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
        self.assertFalse(
            df.empty, 'The generated schedule DataFrame is empty.'
        )

        # Check the first payment date and its components.
        first_row = df.iloc[0]
        self.assertEqual(first_row['Date'], 'Jan - 2024')


        expected_interest = Decimal('1190.32')
        self.assertEqual(
            first_row['Interest'],
            expected_interest,
            (
                'First month interest should be combined. '
                f'Expected {expected_interest}, '
                f"got {first_row['Interest']}"
            ),
        )

        # Verify Payment scale-up:
        expected_total_amount = Decimal('1334.32')
        self.assertEqual(
            first_row['Total Monthly Amount'],
            expected_total_amount,
            (
                'First payment should be scaled up. '
                f'Expected {expected_total_amount}, '
                f"got {first_row['Total Monthly Amount']}"
            ),
        )

        # Verify Principal remains untouched by the interest variation
        expected_principal = Decimal('144.00')
        self.assertEqual(
            first_row['Principal'],
            expected_principal,
            (
                'Principal reduction should stay aligned. '
                f'Expected {expected_principal}, '
                f"got {first_row['Principal']}"
            ),
        )


class TestMortgageContract(unittest.TestCase):

    def setUp(self):
        """Create a baseline dictionary that satisfies the input contract."""
        self.valid_payload = {
            'purchase_price': Decimal('220000.00'),
            'deposit': Decimal('60000.00'),
            'term_years': 35,
            'start_date': datetime(2023, 12, 7),
            'fixed_deals': [(Decimal('4.9'), 5), (Decimal('4.2'), 2)],
            'variable_tracker': Decimal('4.25'),
            'overpayments': [(datetime(2024, 3, 1), Decimal('100.00'))],
            'one_off_overpayments': [
                (datetime(2024, 3, 2), Decimal('1000.00'))
            ],
        }

    def test_invalid_fixed_interest_rates(self):
        '''Reject zero and negative fixed interest rates.'''

        for invalid_rate in [Decimal('0'), Decimal('-0.5')]:
            with self.subTest(rate=invalid_rate):
                broken_payload = self.valid_payload.copy()

                broken_payload['fixed_deals'] = [
                    (invalid_rate, 5),
                    (Decimal('4.2'), 2),
                ]

                with self.assertRaises(ValidationError):
                    MortgageDataChecker(**broken_payload)

    def test_zero_variable_tracker_rejected(self):
        '''Reject a zero variable interest rate.'''

        broken_payload = self.valid_payload.copy()
        broken_payload['variable_tracker'] = Decimal('0')

        with self.assertRaises(ValidationError):
            MortgageDataChecker(**broken_payload)

    def test_duplicate_one_off_overpayments(self):
        """Reject multiple one-off overpayments within a single month."""

        broken_payload = self.valid_payload.copy()

        broken_payload['one_off_overpayments'] = [
            (datetime(2025, 3, 1), Decimal('1000.00')),
            (datetime(2025, 6, 1), Decimal('2000.00')),
            (datetime(2025, 3, 15), Decimal('500.00')),
        ]

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Record 3 conflicts with Record 1',
            str(context.exception)
        )

    def test_invalid_mortgage_terms(self):
        """Reject zero and negative mortgage terms."""

        for invalid_term in [0, -1]:
            with self.subTest(term=invalid_term):
                broken_payload = self.valid_payload.copy()
                broken_payload['term_years'] = invalid_term

                with self.assertRaises(ValidationError):
                    MortgageDataChecker(**broken_payload)

    def test_valid_payload_passes_contract(self):
        """Ensure a completely clean payload initialises without any issues."""
        try:
            MortgageDataChecker(**self.valid_payload)
        except (ValidationError, ValueError) as e:
            self.fail(f'Valid payload failed validation unexpectedly: {e}')

    def test_strict_type_enforcement_blocks_floats(self):
        """Reject floats under strict validation to preserve precision."""
        broken_payload = self.valid_payload.copy()
        broken_payload['purchase_price'] = 220000.00  # Raw float passed

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Input should be an instance of Decimal',
            str(context.exception),
        )

    def test_invalid_fixed_deal_durations(self):
        """Reject fixed-rate deals with zero or negative durations."""

        for invalid_duration in [0, -1]:
            with self.subTest(duration=invalid_duration):
                broken_payload = self.valid_payload.copy()

                broken_payload['fixed_deals'] = [
                    (Decimal('4.9'), 5),
                    (Decimal('4.2'), invalid_duration),
                ]

                with self.assertRaises(ValidationError) as context:
                    MortgageDataChecker(**broken_payload)

                self.assertIn(
                    'Fixed-rate deal Record 2',
                    str(context.exception)
                )

    def test_strict_type_enforcement_blocks_string_integers(self):
        """Reject numeric strings under strict validation."""
        broken_payload = self.valid_payload.copy()
        broken_payload['term_years'] = '35'  # String instead of int

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Input should be a valid integer', str(context.exception)
        )

    def test_extra_forbidden_blocks_unknown_parameters(self):
        """Reject unexpected fields when extra is forbidden."""
        broken_payload = self.valid_payload.copy()
        broken_payload['random_extra_property'] = (
            'malicious_or_accidental_data'
        )

        with self.assertRaises(ValidationError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn('Extra inputs are not permitted', str(context.exception))

    def test_business_contract_blocks_excessive_deposit(self):
        """Reject a deposit that equals or exceeds the purchase price."""
        broken_payload = self.valid_payload.copy()
        # Deposit exceeds the purchase price.
        broken_payload['deposit'] = Decimal('230000.00')

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Deposit must be strictly less than the purchase price',
            str(context.exception),
        )

    def test_business_contract_blocks_excessive_fixed_deals(self):
        """Reject fixed-rate deals extending beyond the mortgage term."""
        broken_payload = self.valid_payload.copy()
        # The mortgage lasts 35 years; the fixed deal lasts 40 years.
        broken_payload['fixed_deals'] = [(Decimal('4.9'), 40)]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Total length of fixed deals exceeds the mortgage term',
            str(context.exception),
        )

    def test_negative_overpayments_are_blocked(self):
        """Reject negative overpayments under the business contract."""
        broken_payload = self.valid_payload.copy()
        broken_payload['overpayments'] = [
            (datetime(2024, 3, 1), Decimal('-50.00'))
        ]

        with self.assertRaises(ValueError) as context:
            MortgageDataChecker(**broken_payload)

        self.assertIn(
            'Overpayment amounts cannot be negative',
            str(context.exception),
        )


class TestMortgageMath(unittest.TestCase):

    def setUp(self):
        self.calc = MortgageCalculations(
            term=12,
            rate=Decimal('12'),
            balance_remaining=Decimal('1000.00'),
            comp_date=datetime(2023, 12, 7),
        )

    def test_monthly_interest(self):
        # Annual interest of 12% yields 1% monthly: 1% of 1000 is 10.
        result = self.calc.monthly_drilldown(
            overpayments=Decimal('0'), balance=Decimal('1000.00')
        )
        self.assertEqual(result['Interest'], Decimal('10.00'))

    def test_final_payment(self):
        small_balance = Decimal('90.00').quantize(Decimal('0.01'))

        # Create a calculator for the final payment.
        final_month_calc = MortgageCalculations(
            term=1,
            rate=Decimal('5.0'),
            balance_remaining=small_balance,
            comp_date=datetime(2023, 12, 7)
        )

        # Calculate the final payment with the dedicated calculator.
        result = final_month_calc.monthly_drilldown(
            overpayments=Decimal('0'), balance=small_balance
        )

        # Verify the final balance is zero.
        self.assertEqual(result['Balance'], Decimal('0.00'))

        # Now this will correctly use the 5.0% rate configured above
        expected_interest = (
            small_balance * final_month_calc.monthly_interest
        ).quantize(Decimal('0.01'))
        expected_bill = (
            small_balance + expected_interest
        ).quantize(Decimal('0.01'))

        self.assertEqual(result['Total Monthly Amount'], expected_bill)

    def test_overpayment(self):
        start_balance = Decimal('1000.00')
        overpayment = Decimal('100.00')
        result = self.calc.monthly_drilldown(
            overpayments=overpayment, balance=start_balance
        )

        expected_value = (
            self.calc.monthly_total_payment - Decimal('10.00')
        ) + overpayment

        self.assertEqual(
            result['Principal'], expected_value.quantize(Decimal('0.01'))
        )


class TestBoEFile(unittest.TestCase):
    """Verify Bank of England JSON persistence behaviour."""

    def test_save_db_creates_json(self):
        """Verify save_db creates a valid JSON file."""

        # Arrange: Create an isolated temporary directory.
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / 'boe_rate.json'

            test_data = {
                'Successful': [
                    {
                        'Rate': 4.5,
                        'Date accessed': '17-10-2026'
                    }
                ],
                'Failed': []
            }

            # Confirm the file does not already exist.
            self.assertFalse(file_path.exists())

            # Act: Save the test data.
            save_db(file_path, test_data)

            # Assert: Verify the file was created.
            self.assertTrue(file_path.exists())

            # Read the file and verify the stored contents.
            with open(file_path, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)

            self.assertEqual(saved_data, test_data)

            # Verify the temporary file was replaced.
            self.assertFalse(
                file_path.with_suffix('.tmp').exists()
            )

    def test_save_db_preserves_history(self):
        """Verify existing rate history survives subsequent JSON writes."""

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / 'boe_rate.json'

            # Arrange: Create an existing historical record.
            original_data = {
                'Successful': [
                    {
                        'Rate': 4.5,
                        'Date accessed': '01-10-2026'
                    }
                ],
                'Failed': []
            }

            save_db(file_path, original_data)

            # Act: Load history and append a new rate.
            db = load_db(file_path)

            new_record = {
                'Rate': 4.25,
                'Date accessed': '17-10-2026'
            }

            db['Successful'].append(new_record)

            save_db(file_path, db)

            # Assert: Verify both records have been preserved.
            updated_db = load_db(file_path)

            self.assertEqual(
                len(updated_db['Successful']),
                2
            )

            self.assertEqual(
                updated_db['Successful'][0],
                original_data['Successful'][0]
            )

            self.assertEqual(
                updated_db['Successful'][1],
                new_record
            )

    def test_failed_write_preserves_original(self):
        """Verify a failed JSON write does not corrupt existing data."""

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / 'boe_rate.json'

            # Arrange: Save an existing valid record.
            original_data = {
                'Successful': [
                    {
                        'Rate': 4.5,
                        'Date accessed': '01-10-2026'
                    }
                ],
                'Failed': []
            }

            save_db(file_path, original_data)

            updated_data = {
                'Successful': [
                    {
                        'Rate': 4.25,
                        'Date accessed': '17-10-2026'
                    }
                ],
                'Failed': []
            }

            # Act: Simulate a failure during JSON writing.
            with patch(
                'src.boe_scraper.json.dump',
                side_effect=OSError('Simulated disk write failure')
            ):
                with self.assertRaises(OSError):
                    save_db(file_path, updated_data)

            # Assert: Original data must remain intact.
            preserved_data = load_db(file_path)

            self.assertEqual(
                preserved_data,
                original_data,
                'Original JSON must survive an interrupted write.'
            )

    def test_boe_timeout_uses_cached_rate(self):
        """Verify an HTTP timeout falls back to the last successful rate."""

        # Arrange: Create a cached rate that is 10 days old.
        stale_date = (
            date.today() - timedelta(days=10)
        ).strftime('%d-%m-%Y')

        cached_data = {
            'Successful': [
                {
                    'Rate': 4.5,
                    'Date accessed': stale_date
                }
            ],
            'Failed': []
        }

        # Simulate the existing cache and an HTTP timeout.
        with (
            patch(
                'src.boe_scraper.load_db',
                return_value=cached_data
            ),
            patch(
                'src.boe_scraper.requests.get',
                side_effect=requests.exceptions.Timeout(
                    'Simulated connection timeout'
                )
            ) as mock_request,
            patch('src.boe_scraper.save_db') as mock_save
        ):

            # Act: Attempt to retrieve the Bank of England rate.
            result = setup()

            # Assert: The cached rate is returned.
            self.assertEqual(result, 4.5)

            # Verify that a live request was attempted.
            mock_request.assert_called_once()

            # Verify that the updated history was saved.
            mock_save.assert_called_once()

            # Verify that the failed attempt was recorded.
            self.assertEqual(
                len(cached_data['Failed']),
                1
            )

            self.assertIn(
                'Simulated connection timeout',
                cached_data['Failed'][0]['Failure Reason']
            )

    def test_boe_timeout_without_history(self):
        """Verify a timeout without historical rates raises ValueError."""

        # Arrange: Simulate an empty BoE database.
        empty_db = {
            'Successful': [],
            'Failed': []
        }

        with (
            patch('src.boe_scraper.load_db', return_value=empty_db),
            patch(
                'src.boe_scraper.requests.get',
                side_effect=requests.exceptions.Timeout(
                    'Simulated connection timeout'
                )
            ) as mock_request,
            patch('src.boe_scraper.save_db') as mock_save
        ):

            # Act & Assert: No valid interest rate is available.
            with self.assertRaisesRegex(
                ValueError,
                'No live or historical rate available'
            ):
                setup()

            # Verify the live request was attempted.
            mock_request.assert_called_once()

            # Verify the failed retrieval was recorded.
            self.assertEqual(len(empty_db['Failed']), 1)

            # Verify the failure history was passed to persistence.
            mock_save.assert_called_once()


if __name__== '__main__':
    unittest.main()