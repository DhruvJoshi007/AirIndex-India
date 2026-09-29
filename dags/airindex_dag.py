"""Apache Airflow DAG: hourly scrape -> clean -> index -> publish.

Drop this file in your Airflow `dags/` folder with the airindex package on the
PYTHONPATH. In the demo the same steps run from `python -m airindex.pipeline`.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "error502",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def scrape_and_clean(**ctx):
    from airindex import pipeline, storage
    with storage.connect() as con:
        report = pipeline.run_day(con, ctx["logical_date"].date(), hours=(ctx["logical_date"].hour,))
    if report["pass_rate"] < 0.90:
        raise ValueError(f"Data-quality gate failed: pass rate {report['pass_rate']:.1%}")
    return report


def publish_index(**_):
    import json
    from airindex import snapshot
    from airindex.config import DATA_DIR
    snap = snapshot.build()
    (DATA_DIR / "snapshot.json").write_text(json.dumps(snap))
    return snap["kpi"]


with DAG(
    dag_id="airindex_hourly",
    description="AirIndex India: scrape airline & OTA fares, clean, recompute the index",
    start_date=datetime(2026, 4, 1),
    schedule="0 * * * *",
    catchup=False,
    default_args=default_args,
    tags=["sih2026", "cpi", "airfare"],
) as dag:
    t1 = PythonOperator(task_id="scrape_and_clean", python_callable=scrape_and_clean)
    t2 = PythonOperator(task_id="publish_index", python_callable=publish_index)
    t1 >> t2
