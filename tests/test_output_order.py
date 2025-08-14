import pandas as pd
import sqlite3
import sys, pathlib
import pytest

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))
from Ybsnow_Order_Scraper import (
    YBSNowScraper,
    ScrapeConfig,
    OPTIONAL_COLUMNS,
)


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


def test_clean_df_missing_required_columns():
    df = pd.DataFrame({"foo": [1], "bar": [2]})
    cfg = ScrapeConfig(base_url="", login_url="", orders_url="", email="", password="")
    scraper = YBSNowScraper(cfg)

    with pytest.raises(ValueError) as exc:
        scraper._clean_df(df)
    assert "Missing required columns" in str(exc.value)


def test_clean_df_fills_optional_columns():
    df = pd.DataFrame({
        "order_id": [1],
        "date": pd.to_datetime(["2024-06-01"]),
        "total": [10],
    })
    cfg = ScrapeConfig(base_url="", login_url="", orders_url="", email="", password="")
    scraper = YBSNowScraper(cfg)

    cleaned = scraper._clean_df(df)
    for col in OPTIONAL_COLUMNS:
        assert col in cleaned.columns
