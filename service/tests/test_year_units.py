import unittest
from decimal import Decimal
from service.normalization import unit_info as extended_unit_info


class YearUnitTests(unittest.TestCase):
    def test_duration_years_is_scalar_and_not_a_reporting_period(self):
        for spelling in ("年","year","years"):
            self.assertEqual(extended_unit_info(spelling),(spelling,Decimal(1),"years"))

    def test_existing_money_and_percentage_units_remain_distinct(self):
        self.assertEqual(extended_unit_info("万元")[1:],(Decimal(10000),"CNY"))
        self.assertEqual(extended_unit_info("%")[1:],(Decimal(1),"percent"))

    def test_english_statement_magnitudes_and_currency_are_independent(self):
        for spelling,factor,currency in [("RMB’000",1000,"CNY"),("HK$'000",1000,"HKD"),
                ("USD (000s)",1000,"USD"),("CNY'000,000",1000000,"CNY"),
                ("USD mn",1000000,"USD"),("EUR bn",1000000000,"EUR"),("RMB",1,"CNY")]:
            with self.subTest(unit=spelling):
                self.assertEqual(extended_unit_info(spelling)[1:],(Decimal(factor),currency))
        for spelling in ["RMB'00","USD unknown_scale"]:
            self.assertEqual(extended_unit_info(spelling),(None,None,"unknown"))


if __name__=="__main__":unittest.main()
