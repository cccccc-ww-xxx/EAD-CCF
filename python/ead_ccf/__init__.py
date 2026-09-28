"""EAD-CCF model development package (synthetic-data prototype).

Modules, in pipeline order:
    config           - load config/config.yaml
    synthetic_data   - generate synthetic defaulted + performing facilities
    realised_ccf     - compute realised CCF per facility per default
    segmentation     - assign benchmark / calibration segments
    lra              - long-run average CCF (two weighting methods)
    models           - benchmark, fractional logit, gradient-boosting challenger
    quantification   - calibration, downturn, margin of conservatism, input floor
    validation       - performance tests (discrimination, calibration, stability)
    report           - write tables, charts and the model documentation
"""

__version__ = "0.1.0"
