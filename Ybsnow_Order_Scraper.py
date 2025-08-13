#!/usr/bin/env python3
"""
YBSNow Order Scraper — CLI + GUI (customtkinter)

Features
- Logs into https://www.ybsnow.com/ using the email/password fields described.
- Navigates to a provided, authenticated Orders page URL and extracts the Orders table.
- Saves results to CSV, XLSX, and a user-selected SQLite database and shows a preview in a simple GUI.
- CLI for automation; GUI for convenience.

Dependencies
  pip install requests beautifulsoup4 lxml pandas openpyxl python-dotenv customtkinter

Optional (only if you later enable the Selenium fallback):
  pip install selenium webdriver-manager

Security
- Credentials are accepted via CLI flags, GUI fields, or environment variables.
- For safety, you can create a .env file next to this script with:
      YBSNOW_EMAIL="your@email"
      YBSNOW_PASSWORD="your_password"
      YBSNOW_BASE_URL="https://www.ybsnow.com/"
      YBSNOW_ORDERS_URL="https://www.ybsnow.com/some/orders/page"

Notes
- This script uses requests + BeautifulSoup/Pandas to parse HTML tables. If the Orders page is heavily JS-driven,
  uncomment and use the Selenium fallback provided near the bottom (disabled by default to keep things simple).
- The login flow is based on the form snippet you shared: POST to /index.php with fields email, password, action=signin.
- Adjust SELECTORS in parse_orders_table(...) if the target table has a known id/class.
"""

from __future__ import annotations
import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv

# GUI imports (lazy-loaded inside main to allow headless CLI usage)
# import customtkinter as ctk

DEFAULT_BASE_URL = "https://www.ybsnow.com/"
LOGIN_PATH = "index.php"           # from your form action
DEFAULT_LOGIN_URL = DEFAULT_BASE_URL + LOGIN_PATH

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

@dataclass
class ScrapeConfig:
    base_url: str
    login_url: str
    orders_url: str
    email: str
    password: str
    out_csv: str = "orders.csv"
    out_xlsx: str = "orders.xlsx"
    out_db: str = "orders.db"
    timeout: int = 30


class YBSNowScraper:
    def __init__(self, cfg: ScrapeConfig):
        self.cfg = cfg
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": cfg.base_url,
        })

    def login(self) -> None:
        """Perform login using the form fields: email, password, action=signin."""
        # Get landing page first (cookies, any hidden form bits if needed later)
        try:
            r0 = self.sess.get(self.cfg.base_url, timeout=self.cfg.timeout)
            r0.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed initial GET to base URL: {e}")

        payload = {
            "email": self.cfg.email,
            "password": self.cfg.password,
            "action": "signin",
        }
        try:
            r = self.sess.post(self.cfg.login_url, data=payload, timeout=self.cfg.timeout)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Login POST failed: {e}")

        # Basic sanity check: after login, ensure we're not still on the login form.
        if self._looks_like_login_page(r.text):
            raise PermissionError("Login appears to have failed — still seeing the sign-in form.")

    def _looks_like_login_page(self, html: str) -> bool:
        soup = BeautifulSoup(html, "lxml")
        form = soup.find("form", attrs={"name": "signin", "id": "signin"})
        # Heuristic: if the sign-in form is present, assume not logged in.
        return form is not None

    def fetch_orders_html(self) -> str:
        try:
            r = self.sess.get(self.cfg.orders_url, timeout=self.cfg.timeout)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Failed to GET Orders URL: {e}")

        if self._looks_like_login_page(r.text):
            raise PermissionError("Session not authenticated when fetching Orders page. Check credentials or URL.")

        return r.text

    def parse_orders_table(self, html: str) -> pd.DataFrame:
        """Try a few strategies to extract the orders table into a DataFrame.
        1) If a specific id/class is known, target it (adjust SELECTORS).
        2) Else, fall back to pandas.read_html and pick the most relevant table.
        """
        soup = BeautifulSoup(html, "lxml")

        # === Strategy 1: Known selectors (adjust to your DOM) ===
        SELECTORS = [
            {"name": "table", "attrs": {"id": "orders"}},
            {"name": "table", "attrs": {"class": "orders"}},
            {"name": "table", "attrs": {"class": "table table-striped"}},
        ]
        for sel in SELECTORS:
            table = soup.find(sel["name"], attrs=sel["attrs"])  # type: ignore
            if table:
                df_list = pd.read_html(str(table))
                if df_list:
                    df = df_list[0]
                    return self._clean_df(df)

        # === Strategy 2: Any HTML tables via pandas ===
        try:
            tables = pd.read_html(html)
        except ValueError:
            tables = []

        # Heuristic to choose best table: look for columns that match common fields
        preferred_cols = [
            "Order", "Order #", "Order ID", "PO", "Customer", "Workstation", "Status", "Date", "Due"
        ]
        best_idx = None
        best_score = -1
        for i, df in enumerate(tables):
            score = sum(1 for c in df.columns if any(pc.lower() in str(c).lower() for pc in preferred_cols))
            if score > best_score and len(df.columns) > 1 and len(df) > 0:
                best_score = score
                best_idx = i
        if best_idx is None:
            if not tables:
                raise ValueError("No HTML tables found on Orders page.")
            df = tables[0]
        else:
            df = tables[best_idx]
        return self._clean_df(df)

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        # Normalize column names
        df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]
        # Drop completely empty columns
        df = df.dropna(axis=1, how="all")
        # Strip whitespace in string cells
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.strip()
        return df

    def save_outputs(self, df: pd.DataFrame) -> Tuple[str, str, str]:
        df.to_csv(self.cfg.out_csv, index=False)
        df.to_excel(self.cfg.out_xlsx, index=False)
        import sqlite3
        conn = sqlite3.connect(self.cfg.out_db)
        df.to_sql("orders", conn, if_exists="replace", index=False)
        conn.close()
        return (
            os.path.abspath(self.cfg.out_csv),
            os.path.abspath(self.cfg.out_xlsx),
            os.path.abspath(self.cfg.out_db),
        )


# ----------------------------- CLI ---------------------------------

def run_cli(cfg: ScrapeConfig) -> int:
    scraper = YBSNowScraper(cfg)
    print("[*] Logging in...")
    scraper.login()
    print("[*] Fetching Orders page...")
    html = scraper.fetch_orders_html()
    print("[*] Parsing Orders table...")
    df = scraper.parse_orders_table(html)
    print(f"[*] Parsed {len(df)} rows and {len(df.columns)} columns.")
    csv_path, xlsx_path, db_path = scraper.save_outputs(df)
    print(f"[*] Saved: \n  CSV : {csv_path}\n  XLSX: {xlsx_path}\n  DB  : {db_path}")
    return 0


# ----------------------------- GUI ---------------------------------

def launch_gui(default_cfg: ScrapeConfig) -> None:
    import customtkinter as ctk
    import threading
    from tkinter import filedialog

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    app = ctk.CTk()
    app.title("YBSNow Order Scraper")
    app.geometry("760x560")

    # GRID LAYOUT
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(14, weight=1)

    # Inputs
    base_url_var = ctk.StringVar(value=default_cfg.base_url)
    login_url_var = ctk.StringVar(value=default_cfg.login_url)
    orders_url_var = ctk.StringVar(value=default_cfg.orders_url)
    email_var = ctk.StringVar(value=default_cfg.email)
    password_var = ctk.StringVar(value=default_cfg.password)
    db_file_var = ctk.StringVar(value=default_cfg.out_db)

    def labeled_entry(row: int, label: str, var: ctk.StringVar, show: Optional[str] = None):
        ctk.CTkLabel(app, text=label).grid(row=row, column=0, padx=12, pady=(8, 0), sticky="w")
        entry = ctk.CTkEntry(app, textvariable=var, show=show, width=720)
        entry.grid(row=row+1, column=0, padx=12, pady=(0, 8), sticky="ew")
        return entry

    def file_entry(row: int, label: str, var: ctk.StringVar, command) -> ctk.CTkEntry:
        ctk.CTkLabel(app, text=label).grid(row=row, column=0, padx=12, pady=(8, 0), sticky="w")
        frame = ctk.CTkFrame(app)
        frame.grid(row=row+1, column=0, padx=12, pady=(0, 8), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        entry = ctk.CTkEntry(frame, textvariable=var)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(frame, text="Browse", command=command).grid(row=0, column=1)
        return entry

    labeled_entry(0, "Base URL", base_url_var)
    labeled_entry(2, "Login URL", login_url_var)
    labeled_entry(4, "Orders URL", orders_url_var)
    labeled_entry(6, "Email", email_var)
    labeled_entry(8, "Password", password_var, show="*")

    def browse_db_file() -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")],
        )
        if path:
            db_file_var.set(path)

    file_entry(10, "Database File", db_file_var, browse_db_file)

    # Buttons
    btn_frame = ctk.CTkFrame(app)
    btn_frame.grid(row=12, column=0, padx=12, pady=6, sticky="ew")
    btn_frame.grid_columnconfigure(0, weight=0)
    btn_frame.grid_columnconfigure(1, weight=0)
    btn_frame.grid_columnconfigure(2, weight=1)

    status_var = ctk.StringVar(value="Idle.")
    status_label = ctk.CTkLabel(app, textvariable=status_var)
    status_label.grid(row=13, column=0, padx=12, pady=(0, 6), sticky="w")

    preview = ctk.CTkTextbox(app, height=220)
    preview.grid(row=14, column=0, padx=12, pady=8, sticky="nsew")

    def do_scrape():
        status_var.set("Logging in…")
        preview.delete("1.0", "end")
        cfg = ScrapeConfig(
            base_url=base_url_var.get().strip() or DEFAULT_BASE_URL,
            login_url=login_url_var.get().strip() or DEFAULT_LOGIN_URL,
            orders_url=orders_url_var.get().strip(),
            email=email_var.get().strip(),
            password=password_var.get().strip(),
            out_db=db_file_var.get().strip() or default_cfg.out_db,
        )
        try:
            scraper = YBSNowScraper(cfg)
            scraper.login()
            status_var.set("Fetching Orders page…")
            html = scraper.fetch_orders_html()
            status_var.set("Parsing table…")
            df = scraper.parse_orders_table(html)
            csv_path, xlsx_path, db_path = scraper.save_outputs(df)
            status_var.set("Done.")
            head = df.head(20).to_string(index=False)
            preview.insert(
                "1.0",
                f"Rows: {len(df)}  Cols: {len(df.columns)}\nSaved CSV: {csv_path}\nSaved XLSX: {xlsx_path}\nSaved DB: {db_path}\n\nPreview (first 20 rows):\n{head}\n",
            )
        except Exception as e:
            status_var.set("Error.")
            preview.insert("1.0", f"[ERROR] {e}\n")

    def on_click_scrape():
        threading.Thread(target=do_scrape, daemon=True).start()

    scrape_btn = ctk.CTkButton(btn_frame, text="Login + Scrape", command=on_click_scrape)
    scrape_btn.grid(row=0, column=0, padx=6, pady=6)

    quit_btn = ctk.CTkButton(btn_frame, text="Quit", command=app.destroy)
    quit_btn.grid(row=0, column=1, padx=6, pady=6)

    app.mainloop()


# --------------------------- Utilities ------------------------------

def load_config_from_env() -> dict:
    load_dotenv()
    return {
        "email": os.getenv("YBSNOW_EMAIL", ""),
        "password": os.getenv("YBSNOW_PASSWORD", ""),
        "base_url": os.getenv("YBSNOW_BASE_URL", DEFAULT_BASE_URL),
        "orders_url": os.getenv("YBSNOW_ORDERS_URL", ""),
    }


def build_cfg(args: argparse.Namespace) -> ScrapeConfig:
    env = load_config_from_env()

    base_url = args.base_url or env["base_url"]
    login_url = args.login_url or (base_url.rstrip("/") + "/" + LOGIN_PATH)
    orders_url = args.orders_url or env["orders_url"]
    email = args.email or env["email"]
    password = args.password or env["password"]

    if not orders_url:
        raise SystemExit("Orders URL is required (use --orders-url or YBSNOW_ORDERS_URL in .env)")
    if not email or not password:
        raise SystemExit("Email and Password are required (use --email/--password or .env)")

    return ScrapeConfig(
        base_url=base_url,
        login_url=login_url,
        orders_url=orders_url,
        email=email,
        password=password,
        out_csv=args.out_csv,
        out_xlsx=args.out_xlsx,
        out_db=args.db_file,
        timeout=args.timeout,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Orders table from YBSNow (CLI + GUI)")
    p.add_argument("--base-url", default=None, help=f"Base site URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--login-url", default=None, help=f"Login URL (default: {DEFAULT_LOGIN_URL})")
    p.add_argument("--orders-url", default=None, help="Authenticated Orders page URL (REQUIRED if no .env)")
    p.add_argument("--email", default=None, help="Login email (or set YBSNOW_EMAIL in .env)")
    p.add_argument("--password", default=None, help="Login password (or set YBSNOW_PASSWORD in .env)")
    p.add_argument("--out-csv", default="orders.csv", help="Path to save CSV (default: orders.csv)")
    p.add_argument("--out-xlsx", default="orders.xlsx", help="Path to save Excel (default: orders.xlsx)")
    p.add_argument("--db-file", default="orders.db", help="Path to SQLite DB file (default: orders.db)")
    p.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds (default: 30)")
    p.add_argument("--gui", action="store_true", help="Launch the customtkinter GUI")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # If GUI requested, build a config (orders_url/email/password must come from args or env)
    if args.gui:
        env = load_config_from_env()
        base_url = args.base_url or env["base_url"]
        login_url = args.login_url or (base_url.rstrip("/") + "/" + LOGIN_PATH)
        orders_url = args.orders_url or env["orders_url"]
        email = args.email or env["email"]
        password = args.password or env["password"]
        default_cfg = ScrapeConfig(
            base_url=base_url,
            login_url=login_url,
            orders_url=orders_url,
            email=email,
            password=password,
            out_db=args.db_file,
        )
        launch_gui(default_cfg)
        return 0

    # Otherwise run CLI mode
    cfg = build_cfg(args)
    return run_cli(cfg)


if __name__ == "__main__":
    sys.exit(main())
