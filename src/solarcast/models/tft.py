"""[Member 2] Temporal Fusion Transformer (PyTorch Forecasting), small config from params.yaml.

Inputs: 7d history (generation + weather), next-day weather forecast, calendar, site_id,
panel_capacity_kw. Output: 24 hourly forecasts with quantiles (prediction intervals).
"""


def build_dataset(df):
    """Build the pytorch_forecasting.TimeSeriesDataSet."""
    raise NotImplementedError


def build_model(dataset):
    raise NotImplementedError
