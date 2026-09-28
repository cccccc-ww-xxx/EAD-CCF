# Calibration of the synthetic data to public BNP Paribas Fortis disclosures

The synthetic data (`python/ead_ccf/synthetic_data.py`) is calibrated to **public**
figures only, so it resembles the real portfolio's structure without using any client
data. Decision D012.

## Sources

| Ref | Document | Date |
|---|---|---|
| P3-25 | BNP Paribas Fortis, *Pillar 3 disclosure 2025* | 31 Dec 2025 |
| AP3-25 | BNP Paribas Fortis, *Additional Pillar 3 disclosure 2025* | 31 Dec 2025 |
| P3-Q2 | BNP Paribas Fortis, *Pillar 3 disclosure Q2 2026* | 30 Jun 2026 |
| AR-25 | BNP Paribas Fortis, *Annual Report 2025* (consolidated financial statements) | 31 Dec 2025 |

All four are published on the BNP Paribas Fortis investor relations website.

## What is calibrated

| Target | Public figure | Source | Setting in `config/config.yaml` |
|---|---|---|---|
| **Large-corporate share** of corporate revolving limits (drives D011 scope) | Corporates – General: F-IRB gross exposure 32,144 vs A-IRB 31,242 (EUR m) → 50.7% F-IRB. 30 Jun 2026: 48,379 vs 45,598 → 51.5% | AP3-25 p. 20 (EU CR7-A); P3-Q2 p. 21–22 | `large_corporate_limit_share: 0.50` |
| **Rating scale** | 20 counterparty ratings: 17 performing, 3 default | P3-25 p. 21 | `performing_grades: 17` |
| **Product mix** | Retail – qualifying revolving (cards) is tiny: gross 3 (Dec 2025) / 672 (Jun 2026) vs Retail – other 25,375 / 27,668 (EUR m). Non-financial corporates: SMEs are 54,390 of 112,438 loans | AP3-25 p. 20; P3-Q2 p. 15, 21 | `product_mix`: overdraft 45%, card 5%, SME line 30%, corporate RCF 20% |

The product mix is a **judgement** informed by these aggregates. Pillar 3 does not split
revolving products, so the exact shares cannot be derived.

**Check after calibration** (run of 2026-09-28): large-corporate share of corporate
limits = 50.0% in both the performing and the defaulted data; product shares
45.7% / 5.1% / 29.9% / 19.4%; grades 1–17.

## What is NOT calibrated, and why

| Item | Reason |
|---|---|
| **CCF levels** | BNP Paribas Fortis does not publish template EU CR6, the one with exposure-weighted average CCF by exposure class. Neither the annual nor the Q2 2026 report contains it. The bank states only that it models EAD where allowed and back-tests the CCF annually (P3-25 p. 21). |
| Utilisation / undrawn share of revolving lines | Only aggregate commitments are public: confirmed financing commitments 49,443 vs loans to customers 203,793 (EUR m) (AR-25 note 5.a, 4.e). These mix revolving and non-revolving items. |
| Default rates by product | Pillar 3 gives non-performing shares (households 2.0%, non-financial corporates 3.9%, P3-Q2 p. 15), not default rates by revolving product. |

**Possible next source for CCF levels:** the BNP Paribas **group** Pillar 3, published in
the group's Universal Registration Document. As a group-level disclosure it would
normally include EU CR6 with average CCFs. It covers the whole group, not Fortis only,
so it would be a benchmark rather than a Fortis figure.

## Observations worth checking internally

- Retail – qualifying revolving exposure rose from EUR 3m (Dec 2025) to EUR 672m
  (Jun 2026) (P3-Q2 p. 21). This is likely a reclassification between exposure
  classes; it matters for which products are in the revolving CCF scope.
- Over half of Corporates – General is under F-IRB. Under D011, own CCF estimates can
  therefore cover at most about half of the corporate book.
