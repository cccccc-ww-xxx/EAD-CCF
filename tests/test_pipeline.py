"""Unit tests - run with:  python -m unittest discover -s tests -v

Each test uses a tiny hand-calculated example, so a reviewer can check the
expected value with a calculator. This is the kind of evidence internal
validation asks for ("does the code do what the documentation says?").
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from ead_ccf import lra, models, quantification, realised_ccf, segmentation, validation  # noqa: E402
from ead_ccf.config import load_config  # noqa: E402

CFG = load_config()


def facility(limit, drawn, ead, product="RET_OVD", year=2015, grade=8.0):
    return {"facility_id": f"F{limit}-{drawn}-{ead}", "product": product, "limit_ref": limit,
            "drawn_ref": drawn, "ead_default": ead, "default_year": year,
            "reference_date": "2014-01-01", "default_date": "2015-01-01", "grade_ref": grade}


class TestRealisedCCF(unittest.TestCase):
    def setUp(self):
        self.df = realised_ccf.compute_realised_ccf(pd.DataFrame([
            facility(1000, 400, 700),    # standard: (700-400)/(1000-400) = 0.5
            facility(1000, 400, 300),    # repayment: raw -1/6, floored to 0
            facility(1000, 400, 1100),   # over-limit: (1100-400)/600 = 1.1667 (no cap)
            facility(1000, 990, 1020),   # ROI: raw 3.0; stabilised 30/max(10, 50) = 0.6
            facility(1000, 1000, 1025),  # fully drawn: raw n/a; stabilised 25/50 = 0.5
        ]), CFG)

    def test_standard(self):
        self.assertAlmostEqual(self.df.loc[0, "ccf_realised"], 0.5)
        self.assertEqual(self.df.loc[0, "facility_type"], "STANDARD")

    def test_negative_floored(self):
        self.assertAlmostEqual(self.df.loc[1, "ccf_raw"], -100 / 600)
        self.assertEqual(self.df.loc[1, "ccf_realised"], 0.0)
        self.assertEqual(self.df.loc[1, "flag_negative_raw"], 1)

    def test_above_one_not_capped(self):
        self.assertAlmostEqual(self.df.loc[2, "ccf_realised"], 700 / 600)
        self.assertEqual(self.df.loc[2, "ccf_model_target"], 1.0)  # capped for the fit only

    def test_region_of_instability(self):
        self.assertEqual(self.df.loc[3, "facility_type"], "ROI")
        self.assertAlmostEqual(self.df.loc[3, "ccf_raw"], 3.0)
        self.assertAlmostEqual(self.df.loc[3, "ccf_realised"], 0.6)

    def test_fully_drawn(self):
        self.assertEqual(self.df.loc[4, "facility_type"], "FULLY_DRAWN")
        self.assertTrue(np.isnan(self.df.loc[4, "ccf_raw"]))
        self.assertAlmostEqual(self.df.loc[4, "ccf_realised"], 0.5)


class TestSegmentsAndLRA(unittest.TestCase):
    def test_bands(self):
        df = segmentation.assign_segments(pd.DataFrame([
            facility(100, 10, 10), facility(100, 50, 50), facility(100, 96, 96),
            facility(100, 100, 100)]), CFG)
        self.assertEqual(list(df["util_band"]), ["U1_lt50", "U2_50_95", "U3_ge95", "U3_ge95"])
        self.assertEqual(df.loc[0, "calib_segment"], "RET_OVD/U1_lt50")

    def test_two_lra_methods(self):
        # year 2015: CCFs 0.2, 0.4, 0.6 (mean 0.4); year 2016: CCF 1.0
        # facility weighted = 2.2/4 = 0.55 ; yearly average = (0.4 + 1.0)/2 = 0.70
        df = pd.DataFrame({"calib_segment": ["S"] * 4, "default_year": [2015, 2015, 2015, 2016],
                           "ccf_realised": [0.2, 0.4, 0.6, 1.0]})
        t = lra.lra_by_segment(df).iloc[0]
        self.assertAlmostEqual(t["lra_facility_weighted"], 0.55)
        self.assertAlmostEqual(t["lra_yearly_average"], 0.70)


class TestFractionalLogit(unittest.TestCase):
    def test_recovers_true_coefficients(self):
        rng = np.random.default_rng(1)
        n = 20000
        X = pd.DataFrame({"x1": rng.normal(size=n), "x2": rng.binomial(1, 0.4, n)})
        mu = 1 / (1 + np.exp(-(-0.5 + 1.0 * X["x1"] - 0.8 * X["x2"])))
        y = rng.beta(mu * 5, (1 - mu) * 5)  # fractional outcome with mean mu
        fl = models.FractionalLogit().fit(X, y)
        np.testing.assert_allclose(fl.coef_, [-0.5, 1.0, -0.8], atol=0.05)
        self.assertTrue(fl.converged_)
        self.assertTrue((fl.summary()["robust_se"] > 0).all())


class TestQuantificationAndValidation(unittest.TestCase):
    def test_calibration_factor(self):
        dev = pd.DataFrame({"calib_segment": ["A", "A", "B"]})
        cf = quantification.calibration_factors(dev, np.array([0.2, 0.4, 0.5]),
                                                pd.Series({"A": 0.45, "B": 0.5}))
        self.assertAlmostEqual(cf["A"], 1.5)   # 0.45 / 0.30
        self.assertAlmostEqual(cf["B"], 1.0)

    def test_input_floor(self):
        df = pd.DataFrame({"calib_segment": ["CORP_RCF/U1_lt50"], "product": ["CORP_RCF"],
                           "facility_type": ["STANDARD"], "util_band": ["U1_lt50"]})
        dt = pd.DataFrame({"calib_segment": ["CORP_RCF/U1_lt50"], "lra": [0.1],
                           "downturn_factor": [1.0]})
        moc = pd.DataFrame({"calib_segment": ["CORP_RCF/U1_lt50"], "moc_total": [0.0]})
        out = quantification.final_ccf(df, np.array([0.05]), pd.Series({"CORP_RCF/U1_lt50": 1.0}),
                                       dt, moc, CFG)
        self.assertAlmostEqual(out["ccf_final"].iloc[0], 0.20)   # 50% x SA CCF 40%
        self.assertEqual(out["floor_binding"].iloc[0], 1)

    def test_ttest_detects_underestimation(self):
        rng = np.random.default_rng(3)
        df = pd.DataFrame({"calib_segment": ["S"] * 500,
                           "ccf_realised": rng.normal(0.6, 0.2, 500)})
        low = validation.calibration_ttest(df, np.full(500, 0.4), 0.05).iloc[0]
        high = validation.calibration_ttest(df, np.full(500, 0.8), 0.05).iloc[0]
        self.assertEqual(low["result"], "UNDERESTIMATION")
        self.assertEqual(high["result"], "ok")


if __name__ == "__main__":
    unittest.main()
