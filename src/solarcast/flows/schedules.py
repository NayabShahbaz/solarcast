"""[Member 1] Serves the scheduled Prefect deployments (daily ingestion + monitoring)."""

if __name__ == "__main__":
    # from prefect import serve
    # from solarcast.flows.ingestion_flow import ingestion_flow
    # from solarcast.flows.retraining_flow import monitor_and_retrain_flow
    # serve(
    #     ingestion_flow.to_deployment(name="daily-ingestion", cron="0 1 * * *"),
    #     monitor_and_retrain_flow.to_deployment(name="daily-monitoring", cron="0 3 * * *"),
    # )
    raise NotImplementedError
