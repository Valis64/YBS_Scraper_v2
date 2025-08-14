import pandas as pd
import sqlite3
import sys, pathlib

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from Ybsnow_Order_Scraper import YBSNowScraper, ScrapeConfig


def test_save_outputs_preserves_order(tmp_path):
    df = pd.DataFrame({
        "order_id": [2, 1, 1, 3],
        "date": pd.to_datetime([
            "2024-06-02",
            "2024-06-01",
            "2024-06-01",
            "2024-06-03",
        ]),
        "total": [20, 10, 10, 30],
    })

    cfg = ScrapeConfig(
        base_url="",
        login_url="",
        orders_url="",
        email="",
        password="",
        out_csv=str(tmp_path / "orders.csv"),
        out_xlsx=str(tmp_path / "orders.xlsx"),
        out_json=str(tmp_path / "orders.json"),
        out_db=str(tmp_path / "orders.db"),
    )
    scraper = YBSNowScraper(cfg)

    cleaned = scraper._clean_df(df)
    assert len(cleaned) == 3
    expected = cleaned.sort_values(["order_id", "date"]).reset_index(drop=True)

    csv_path, xlsx_path, json_path, db_path = scraper.save_outputs(cleaned)

    df_csv = pd.read_csv(csv_path, parse_dates=["date"])
    df_xlsx = pd.read_excel(xlsx_path, parse_dates=["date"])
    df_json = pd.read_json(json_path)
    conn = sqlite3.connect(db_path)
    df_sql = pd.read_sql_query("SELECT * FROM orders", conn, parse_dates=["date"])
    conn.close()

    pd.testing.assert_frame_equal(df_csv, expected, check_dtype=False)
    pd.testing.assert_frame_equal(df_xlsx, expected, check_dtype=False)
    pd.testing.assert_frame_equal(df_json, expected, check_dtype=False)
    pd.testing.assert_frame_equal(df_sql, expected, check_dtype=False)
