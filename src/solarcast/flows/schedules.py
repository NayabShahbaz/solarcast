"""[Member 1] Serves the scheduled Prefect deployments. Keep this process running (on EC2 later).

  daily-ingestion   20:00 PKT (15:00 UTC): recent weather + actuals, tomorrow's forecast inputs
  daily-monitoring  20:30 PKT (15:30 UTC): drift + errors -> retrain if triggered

Run: python -m solarcast.flows.schedules   (needs a Prefect server: `prefect server start`)
"""

from prefect import serve

from solarcast.flows.ingestion_flow import ingestion_flow
from solarcast.flows.retraining_flow import monitor_and_retrain_flow

if __name__ == "__main__":
    serve(
        ingestion_flow.to_deployment(
            name="daily-ingestion", cron="0 15 * * *", parameters={"mode": "daily"}
        ),
        monitor_and_retrain_flow.to_deployment(name="daily-monitoring", cron="30 15 * * *"),
    )
