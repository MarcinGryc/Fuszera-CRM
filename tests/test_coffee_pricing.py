import math
import unittest
from pathlib import Path

from flask import Flask
from werkzeug.datastructures import MultiDict

from routes.coffee import DEFAULTS, calculate_price, calculate_quote, coffee_bp
from routes.auth import auth_bp


def form(**overrides):
    values = {**DEFAULTS, **overrides}
    return MultiDict((key, str(item)) for key, value in values.items()
                     for item in (value if isinstance(value, list) else [value]))


class CoffeeCostTests(unittest.TestCase):
    def test_full_cost_includes_real_overhead_and_production_once(self):
        # 32.80 / 82% = 40; 1500 / 200 = 7.50; production = 5.
        kg = calculate_price(32.8, 1, 5, .75)
        self.assertEqual(kg['cost_net'], 57.5)
        self.assertEqual(kg['beans'], 40)
        self.assertEqual(kg['fixed'], 7.5)
        self.assertEqual(kg['production'], 5)
        self.assertEqual(kg['packaging'], 5)
        self.assertEqual(kg['net'], 100.63)
        quarter = calculate_price(32.8, .25, 5, .75)
        self.assertEqual(quarter['cost_net'], 18.13)
        self.assertEqual(quarter['fixed'], 1.88)
        self.assertEqual(quarter['production'], 1.25)
        self.assertEqual(quarter['net'], 31.72)

    def test_weighted_blend_and_single(self):
        quote = calculate_quote(form(blend_price=[30, 40, 50], blend_percentage=[20, 30, 50]))
        self.assertEqual(quote['green_price'], 43)
        self.assertEqual(quote['fixed_per_kg'], 7.5)
        single = calculate_quote(form(blend_price=[40, 0, 0]))
        self.assertEqual(single['green_price'], 40)

    def test_default_brazil_matches_requested_retail_prices(self):
        quote = calculate_quote(form())
        self.assertEqual(quote['b2c_250']['gross'], 49)
        self.assertEqual(quote['b2c_1000']['gross'], 159)
        self.assertEqual(quote['b2c_250']['cost_net'], 20.32)
        self.assertEqual(quote['b2c_1000']['cost_net'], 66.28)

    def test_markups_are_independent_and_discount_limit_protects_both_sizes(self):
        quote = calculate_quote(form())
        changed = calculate_quote(form(markup_250=0))
        self.assertEqual(changed['b2c_1000'], quote['b2c_1000'])
        self.assertLess(changed['b2c_250']['net'], quote['b2c_250']['net'])
        for markup in (0, 100):
            values = dict(markup_250=markup, markup_1000=markup)
            retail = calculate_quote(form(**values))
            discounted = calculate_quote(form(**values, discount=retail['max_discount_pct']))
            self.assertFalse(discounted['b2b_250']['below_cost'])
            self.assertFalse(discounted['b2b_1000']['below_cost'])

    def test_discount_after_markup_and_vat(self):
        quote = calculate_price(32.8, 1, 5, .75, .2)
        self.assertEqual(quote['net'], 80.51)
        self.assertEqual(quote['gross'], 99.03)
        self.assertEqual(quote['profit'], 23.01)
        self.assertFalse(quote['below_cost'])

    def test_extreme_sliders_are_finite_and_truthful(self):
        for markup in (0, 1):
            quote = calculate_price(32.8, 1, 5, markup)
            self.assertFalse(quote['below_cost'])
            self.assertEqual(quote['net'], 57.5 * (1 + markup))
        free = calculate_price(32.8, 1, 5, .75, 1)
        self.assertEqual(free['net'], 0)
        self.assertEqual(free['profit'], -57.5)
        self.assertIsNone(free['margin_pct'])
        self.assertIsNone(free['break_even_kg'])
        self.assertTrue(free['below_cost'])

    def test_discount_limit_covers_cost_and_excess_discount_warns(self):
        for weight in (.25, 1):
            retail = calculate_price(40, weight, 5, .75)
            limit = retail['max_discount_pct'] / 100
            self.assertFalse(calculate_price(40, weight, 5, .75, limit)['below_cost'])
            self.assertTrue(calculate_price(40, weight, 5, .75, .5)['below_cost'])

    def test_volume_sensitivity_and_break_even(self):
        quote = calculate_price(32.8, 1, 5, 0)
        self.assertEqual(quote['break_even_kg'], 200)
        self.assertEqual(quote['monthly_profit'], 0)
        lower_volume = calculate_price(32.8, 1, 5, 0, monthly_kg=100)
        self.assertEqual(lower_volume['cost_net'], 65)

    def test_optional_costs_and_commissions_affect_profit(self):
        quote = calculate_price(32.8, 1, 5, .75, extra_per_bag=2, sales_fee=.1)
        self.assertEqual(quote['cost_net'], 59.5)
        self.assertEqual(quote['net'], 115.7)
        self.assertEqual(quote['fee'], 11.57)
        self.assertEqual(quote['profit'], 44.63)
        no_fixed = calculate_price(32.8, 1, 5, .75, fixed_monthly=0)
        self.assertEqual(no_fixed['break_even_kg'], 0)

    def test_invalid_inputs_are_rejected(self):
        for kwargs in ({'monthly_kg': 0}, {'monthly_kg': 1e-300}, {'roast_loss': 1}, {'sales_fee': 1},
                       {'markup': 1.01}, {'discount': -1}, {'green_price_net_per_kg': math.nan},
                       {'production_cost_per_kg_roasted': math.inf}, {'packaging': -1}):
            inputs = dict(green_price_net_per_kg=40, pack_weight_kg=1,
                          production_cost_per_kg_roasted=5, markup=.75)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                calculate_price(**{**inputs, **kwargs})
        for data in (form(blend_percentage=[50, 40, 0]), form(blend_percentage=[101, 0, 0]),
                     form(blend_price=[0, 40, 40]), form(monthly_kg='nan'),
                     form(markup_250=101), form(markup_1000=101)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                calculate_quote(data)


class CoffeeRouteTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'), static_folder=str(root / 'static'))
        self.app.config.update(TESTING=True, SECRET_KEY='pricing-tests')
        self.app.register_blueprint(coffee_bp)
        self.app.register_blueprint(auth_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['logged_in'] = True

    def test_render_default_sliders(self):
        response = self.client.get('/coffee-pricing')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertEqual(page.count('type="range"'), 9)
        self.assertIn('name="markup_250"', page)
        self.assertIn('name="markup_1000"', page)
        self.assertIn('Brazylia', page)
        self.assertIn('B2B · kawiarnie', page)

    def test_json_quote_and_validation(self):
        response = self.client.post('/coffee-pricing', data=form(), headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['result']['fixed_per_kg'], 7.5)
        response = self.client.post('/coffee-pricing', data=form(blend_percentage=[50, 40, 0]),
                                    headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(response.json['result'])
        self.assertIn('100%', response.json['error'])

    def test_without_javascript_preserves_inputs_and_results(self):
        response = self.client.post('/coffee-pricing', data=form(packaging='6.25', markup_250=100, markup_1000=100))
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="6.25"', page)
        self.assertIn('data-result="b2c_250.net">43.15', page)
        response = self.client.post('/coffee-pricing', data=form(discount=100))
        self.assertEqual(response.status_code, 200)
        self.assertIn('Cena nie pokrywa pełnego kosztu', response.get_data(as_text=True))

    def test_requires_login(self):
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.post('/coffee-pricing', data=form())
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)


if __name__ == '__main__':
    unittest.main()
