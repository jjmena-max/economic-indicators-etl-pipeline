"""Apache Airflow DAG that runs the economic-indicators ETL on a schedule.

Drop this file into your Airflow ``dags/`` folder (the bundled docker-compose
mounts it automatically). The DAG mirrors the pipeline stages as discrete tasks
so retries and observability happen per-stage:

    extract  ->  transform  ->  load

The stages pass data through Airflow's XCom for small payloads; for larger
volumes you would stage to object storage instead. Kept simple here on purpose.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Airflow is only needed in the orchestration environment, not for unit tests.
from airflow import DAG  # type: ignore
from airflow.operators.python import PythonOperator  # type: ignore

from econ_etl.config import load_settings
from econ_etl.db import make_engine, table_count
from econ_etl.extract import extract
from econ_etl.load import load as load_step
from econ_etl.transform import transform

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


def _extract(**context):
    settings = load_settings()
    raw = extract(settings)
    context["ti"].xcom_push(key="raw", value=raw)
    return len(raw)


def _transform(**context):
    raw = context["ti"].xcom_pull(key="raw", task_ids="extract")
    df = transform(raw)
    # Serialise to JSON records so it survives XCom.
    context["ti"].xcom_push(key="curated", value=df.to_json(orient="records"))
    return len(df)


def _load(**context):
    import pandas as pd

    settings = load_settings()
    curated_json = context["ti"].xcom_pull(key="curated", task_ids="transform")
    df = pd.read_json(curated_json, orient="records")
    engine = make_engine(settings.database_url)
    load_step(df, engine, settings.table_name)
    return table_count(engine, settings.table_name)


with DAG(
    dag_id="economic_indicators_etl",
    description="Extract World Bank macro indicators, validate, and load to SQL.",
    default_args=default_args,
    schedule="@monthly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["etl", "world-bank", "economics"],
) as dag:
    extract_task = PythonOperator(task_id="extract", python_callable=_extract)
    transform_task = PythonOperator(task_id="transform", python_callable=_transform)
    load_task = PythonOperator(task_id="load", python_callable=_load)

    extract_task >> transform_task >> load_task
