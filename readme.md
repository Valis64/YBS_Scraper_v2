YBSNow Order Scraper

CLI + GUI (CustomTkinter) tool to log into ybsnow.com, navigate to an authenticated Orders page, scrape the orders table, and save it to CSV/XLSX.

📌 Features

Secure Login — Uses the site’s form (email, password, action=signin) to authenticate.

Data Extraction — Grabs the orders table from the authenticated page.

Multiple Outputs — Saves results to .csv, .xlsx, and a user-selected SQLite database.

Dual Interface —

CLI mode for automation.

GUI mode for convenience with a built-in preview.

Environment Variables — Uses .env for credentials and URLs so you don’t hard-code secrets.

📦 Install
git clone https://github.com/<your-username>/ybsnow-order-scraper.git
cd ybsnow-order-scraper
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt

⚙️ Configure

Copy the example environment file and edit it:

cp .env.example .env


Edit .env:

YBSNOW_EMAIL="you@example.com"
YBSNOW_PASSWORD="your_password"
YBSNOW_BASE_URL="https://www.ybsnow.com/"
YBSNOW_ORDERS_URL="https://www.ybsnow.com/<orders-page-after-login>"


Tip: The YBSNOW_ORDERS_URL should be the URL of the page showing the orders table after you are logged in.

🚀 Usage
CLI Mode
python ybsnow_order_scraper.py


Relies on .env for credentials and orders URL.

Or pass them explicitly:

python ybsnow_order_scraper.py \
  --orders-url "https://www.ybsnow.com/<orders-page>" \
  --email "you@example.com" \
  --password "secret"


Output:

orders.csv

orders.xlsx

orders.db

GUI Mode
python ybsnow_order_scraper.py --gui


Enter Base URL, Login URL, Orders URL, Email, and Password.

Click Login + Scrape.

View the first 20 rows in the preview panel.

🛠 How It Works

Starts a requests.Session() and visits the base page for cookies.

Sends a POST request to index.php with login form data.

Requests the Orders page URL.

Parses the HTML to find a table (id="orders", class="orders", or .table.table-striped).

Cleans and normalizes the table with pandas.

Saves to CSV/XLSX/SQLite and displays a preview in GUI mode.

❗ Troubleshooting

Login failed → Double-check credentials in .env and verify manual login works.

No tables found → The Orders page might load via JavaScript; in that case, a Selenium fallback may be needed.

403 or CSRF issues → The site might require a CSRF token; adjust the login payload accordingly.
