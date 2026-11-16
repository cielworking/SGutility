import importlib.util
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


sgpools = module("update_sgpools", "update-sgpools.py")


def fixture(winning, additional, date="Thu, 12 Nov 2026", draw="4234"):
    cells = "".join(
        f'<td class="win{index}">{number}</td>'
        for index, number in enumerate(winning, 1)
    )
    return BeautifulSoup(
        f"""
        <li>
          <table><tr><th class="drawDate">{date}</th><th class="drawNumber">Draw No. {draw}</th></tr></table>
          <table><tr>{cells}</tr></table>
          <table><tr><td class="additional">{additional}</td></tr></table>
        </li>
        """,
        "html.parser",
    ).find("li")


class TotoParserTests(unittest.TestCase):
    def test_date_day_is_not_treated_as_a_winning_number(self):
        block = fixture(["17", "24", "30", "31", "44", "49"], "32")
        winning, additional = sgpools.parse_toto_block(block)
        self.assertEqual(winning, ["17", "24", "30", "31", "44", "49"])
        self.assertEqual(additional, "32")
        self.assertNotIn("12", winning)

    def test_single_digit_winning_and_additional_numbers(self):
        block = fixture(["7", "11", "19", "28", "35", "42"], "3")
        winning, additional = sgpools.parse_toto_block(block)
        self.assertEqual(winning, ["7", "11", "19", "28", "35", "42"])
        self.assertEqual(additional, "3")

    def test_repeated_winning_number_is_rejected(self):
        block = fixture(["7", "7", "19", "28", "35", "42"], "3")
        with self.assertRaises(RuntimeError):
            sgpools.parse_toto_block(block)

    def test_additional_matching_winning_number_is_rejected(self):
        block = fixture(["7", "11", "19", "28", "35", "42"], "42")
        with self.assertRaises(RuntimeError):
            sgpools.parse_toto_block(block)

    def test_out_of_range_number_is_rejected(self):
        block = fixture(["7", "11", "19", "28", "35", "50"], "3")
        with self.assertRaises(RuntimeError):
            sgpools.parse_toto_block(block)


if __name__ == "__main__":
    unittest.main()
