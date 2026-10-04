import unittest
from decimal import Decimal
from service.staged_temporal.units import extended_unit_info


class YearUnitTests(unittest.TestCase):
    def test_duration_years_is_scalar_and_not_a_reporting_period(self):
        for spelling in ("年","year","years"):
            self.assertEqual(extended_unit_info(spelling),(spelling,Decimal(1),"years"))

    def test_existing_money_and_percentage_units_remain_distinct(self):
        self.assertEqual(extended_unit_info("万元")[1:],(Decimal(10000),"CNY"))
        self.assertEqual(extended_unit_info("%")[1:],(Decimal(1),"percent"))


if __name__=="__main__":unittest.main()
