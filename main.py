from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import requests
import psycopg2
import os
import datetime
import time
import threading

app = FastAPI()

API_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

FETCH_INTERVAL_SECONDS = 60

MIN_BOOKMAKERS_PER_OUTCOME = 3
MIN_PRICE = 1.40
MAX_PRICE = 6.00
MIN_DEVIATION_PERCENT = 5.0
MIN_EXPECTED_VALUE = 0.03
MAX_MARKET_SPREAD_PERCENT = 60.0


def normalize_text(value: str) -> str:
    return (value or "").strip()


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def send_telegram_message(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
    except Exception as e:
        print("Telegram error:", e)


def format_dt(value):
    return str(value) if value else ""


def render_layout(title: str, body: str):
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
        <meta name="theme-color" content="#111827" />
        <title>{title}</title>
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: #f3f4f6;
                color: #111827;
            }}
            .app {{
                max-width: 760px;
                margin: 0 auto;
                padding: 14px;
            }}
            .header {{
                background: linear-gradient(135deg, #111827, #1f2937);
                color: white;
                border-radius: 18px;
                padding: 18px;
                margin-bottom: 14px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.18);
            }}
            .header h1 {{
                margin: 0 0 6px 0;
                font-size: 26px;
            }}
            .muted {{
                color: #9ca3af;
                font-size: 14px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
                margin-bottom: 14px;
            }}
            .stat {{
                background: white;
                border-radius: 16px;
                padding: 14px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }}
            .stat .label {{
                font-size: 13px;
                color: #6b7280;
                margin-bottom: 6px;
            }}
            .stat .value {{
                font-size: 22px;
                font-weight: 700;
            }}
            .nav {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-bottom: 14px;
            }}
            .nav a {{
                display: inline-block;
                padding: 10px 14px;
                background: #111827;
                color: white;
                text-decoration: none;
                border-radius: 12px;
                font-size: 14px;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 14px;
                margin-bottom: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            }}
            .title {{
                font-size: 18px;
                font-weight: 700;
                margin-bottom: 8px;
                line-height: 1.3;
            }}
            .row {{
                margin: 5px 0;
                font-size: 15px;
            }}
            .time {{
                margin-top: 8px;
                font-size: 12px;
                color: #6b7280;
            }}
            .badge {{
                display: inline-block;
                padding: 3px 8px;
                border-radius: 999px;
                background: #e5e7eb;
                font-size: 12px;
                margin-left: 6px;
            }}
            .good {{
                background: #dcfce7;
                color: #166534;
            }}
            .mid {{
                background: #fef3c7;
                color: #92400e;
            }}
            .low {{
                background: #e5e7eb;
                color: #374151;
            }}
            .empty {{
                text-align: center;
                color: #6b7280;
                padding: 24px 10px;
            }}
            .footer {{
                text-align: center;
                font-size: 12px;
                color: #6b7280;
                padding: 12px 0 20px;
            }}
            @media (max-width: 560px) {{
                .grid {{
                    grid-template-columns: 1fr 1fr;
                }}
                .header h1 {{
                    font-size: 22px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="app">
            {body}
            <div class="footer">Odds Scanner mobile view</div>
        </div>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def home():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM odds_history")
    history_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM odds_anomalies")
    anomaly_count = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*)
        FROM odds_anomalies
        WHERE created_at > NOW() - INTERVAL '24 hours'
    """)
    anomaly_24h = cur.fetchone()[0]

    cur.execute("""
        SELECT MAX(created_at)
        FROM odds_anomalies
    """)
    last_signal = cur.fetchone()[0]

    cur.close()
    conn.close()

    body = f"""
    <div class="header">
        <h1>Odds Scanner</h1>
        <div class="muted">Mini app za mobitel</div>
    </div>

    <div class="grid">
        <div class="stat">
            <div class="label">History rows</div>
            <div class="value">{history_count}</div>
        </div>
        <div class="stat">
            <div class="label">Anomalies total</div>
            <div class="value">{anomaly_count}</div>
        </div>
        <div class="stat">
            <div class="label">Anomalies 24h</div>
            <div class="value">{anomaly_24h}</div>
        </div>
        <div class="stat">
            <div class="label">Last signal</div>
            <div class="value" style="font-size:14px;">{format_dt(last_signal) if last_signal else "Nema"}</div>
        </div>
    </div>

    <div class="nav">
        <a href="/signals">Zadnji signali</a>
        <a href="/top-signals">Top signali</a>
        <a href="/health">Health</a>
        <a href="/latest-anomalies">JSON</a>
    </div>

    <div class="card">
        <div class="title">Kako koristiti</div>
        <div class="row">1. Otvori <b>Zadnji signali</b> za najnovije zapise.</div>
        <div class="row">2. Otvori <b>Top signali</b> za jače scoreove u zadnja 24 sata.</div>
        <div class="row">3. Dodaj ovu stranicu na početni ekran mobitela za brzi pristup.</div>
    </div>
    """
    return render_layout("Odds Scanner", body)


@app.get("/health")
def health():
    return {"ok": True, "status": "running"}


@app.get("/latest-anomalies")
def latest_anomalies():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT home, away, outcome, bookmaker, bookmaker_price, market_avg,
               deviation_percent, expected_value, signal_score, created_at
        FROM odds_anomalies
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "home": row[0],
            "away": row[1],
            "outcome": row[2],
            "bookmaker": row[3],
            "bookmaker_price": row[4],
            "market_avg": row[5],
            "deviation_percent": row[6],
            "expected_value": row[7],
            "signal_score": row[8],
            "created_at": str(row[9]),
        })
    return result


@app.get("/signals", response_class=HTMLResponse)
def signals():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT home, away, outcome, bookmaker, bookmaker_price, market_avg,
               deviation_percent, expected_value, signal_score, created_at
        FROM odds_anomalies
        ORDER BY id DESC
        LIMIT 30
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    cards = ""

    if not rows:
        cards = """
        <div class="card empty">
            Nema signala još. Pričekaj malo i osvježi stranicu.
        </div>
        """
    else:
        for row in rows:
            home, away, outcome, bookmaker, bookmaker_price, market_avg, deviation_percent, expected_value, signal_score, created_at = row

            if signal_score >= 12:
                badge_class = "good"
                badge_text = "Jak"
            elif signal_score >= 9:
                badge_class = "mid"
                badge_text = "Srednji"
            else:
                badge_class = "low"
                badge_text = "Slabiji"

            cards += f"""
            <div class="card">
                <div class="title">{home} vs {away}</div>
                <div class="row"><b>Ishod:</b> {outcome}</div>
                <div class="row"><b>Bookmaker:</b> {bookmaker}</div>
                <div class="row"><b>Kvota:</b> {bookmaker_price}</div>
                <div class="row"><b>Market avg:</b> {market_avg}</div>
                <div class="row"><b>Dev:</b> {deviation_percent}%</div>
                <div class="row"><b>EV:</b> {expected_value}</div>
                <div class="row"><b>Score:</b> {signal_score} <span class="badge {badge_class}">{badge_text}</span></div>
                <div class="time">{created_at}</div>
            </div>
            """

    body = f"""
    <div class="header">
        <h1>Zadnji signali</h1>
        <div class="muted">Prikaz zadnjih 30 anomaly zapisa</div>
    </div>
    <div class="nav">
        <a href="/">Početna</a>
        <a href="/top-signals">Top signali</a>
    </div>
    {cards}
    """
    return render_layout("Zadnji signali", body)


@app.get("/top-signals", response_class=HTMLResponse)
def top_signals():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT home, away, outcome, bookmaker, bookmaker_price, market_avg,
               deviation_percent, expected_value, signal_score, created_at
        FROM odds_anomalies
        WHERE created_at > NOW() - INTERVAL '24 hours'
        ORDER BY signal_score DESC, id DESC
        LIMIT 20
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    cards = ""

    if not rows:
        cards = """
        <div class="card empty">
            Nema top signala u zadnja 24 sata.
        </div>
        """
    else:
        for row in rows:
            home, away, outcome, bookmaker, bookmaker_price, market_avg, deviation_percent, expected_value, signal_score, created_at = row

            if signal_score >= 12:
                badge_class = "good"
                badge_text = "Jak"
            elif signal_score >= 9:
                badge_class = "mid"
                badge_text = "Srednji"
            else:
                badge_class = "low"
                badge_text = "Slabiji"

            cards += f"""
            <div class="card">
                <div class="title">{home} vs {away}</div>
                <div class="row"><b>Ishod:</b> {outcome}</div>
                <div class="row"><b>Bookmaker:</b> {bookmaker}</div>
                <div class="row"><b>Kvota:</b> {bookmaker_price}</div>
                <div class="row"><b>Market avg:</b> {market_avg}</div>
                <div class="row"><b>Dev:</b> {deviation_percent}%</div>
                <div class="row"><b>EV:</b> {expected_value}</div>
                <div class="row"><b>Score:</b> {signal_score} <span class="badge {badge_class}">{badge_text}</span></div>
                <div class="time">{created_at}</div>
            </div>
            """

    body = f"""
    <div class="header">
        <h1>Top signali</h1>
        <div class="muted">Najjači signali u zadnja 24 sata</div>
    </div>
    <div class="nav">
        <a href="/">Početna</a>
        <a href="/signals">Zadnji signali</a>
    </div>
    {cards}
    """
    return render_layout("Top signali", body)


def fetch_odds():
    if not API_KEY:
        print("Error: API_KEY missing")
        return

    if not DATABASE_URL:
        print("Error: DATABASE_URL missing")
        return

    print("Fetching odds...")

    url = (
        "https://api.the-odds-api.com/v4/sports/soccer/odds/"
        f"?apiKey={API_KEY}&regions=eu&markets=h2h"
    )

    res = requests.get(url, timeout=30)
    res.raise_for_status()
    data = res.json()

    if not isinstance(data, list) or not data:
        print("No odds data received")
        return

    conn = get_conn()
    cur = conn.cursor()

    now_utc = datetime.datetime.utcnow()
    history_rows = 0
    anomaly_rows = 0

    for match in data:
        bookmakers = match.get("bookmakers", [])
        if not bookmakers:
            continue

        home = normalize_text(match.get("home_team"))
        away = normalize_text(match.get("away_team"))

        if not home or not away:
            continue

        outcomes_dict = {}
        seen_history = set()

        for bookmaker in bookmakers:
            bookmaker_name = normalize_text(bookmaker.get("title"))
            if not bookmaker_name:
                continue

            for market in bookmaker.get("markets", []):
                for outcome in market.get("outcomes", []):
                    outcome_name = normalize_text(outcome.get("name"))
                    raw_price = outcome.get("price")

                    if outcome_name == "" or raw_price is None:
                        continue

                    try:
                        price = float(raw_price)
                    except (TypeError, ValueError):
                        continue

                    if price <= 1.0:
                        continue

                    history_key = (home, away, bookmaker_name, outcome_name, price)
                    if history_key not in seen_history:
                        cur.execute(
                            """
                            INSERT INTO odds_history
                            (home, away, bookmaker, outcome, price, timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (
                                home,
                                away,
                                bookmaker_name,
                                outcome_name,
                                price,
                                now_utc,
                            ),
                        )
                        seen_history.add(history_key)
                        history_rows += 1

                    outcomes_dict.setdefault(outcome_name, []).append(
                        {
                            "bookmaker": bookmaker_name,
                            "price": price,
                        }
                    )

        seen_anomalies = set()

        for outcome_name, odds_list in outcomes_dict.items():
            per_bookmaker = {}
            for item in odds_list:
                name = item["bookmaker"]
                price = item["price"]
                if name not in per_bookmaker or price > per_bookmaker[name]:
                    per_bookmaker[name] = price

            filtered = [
                {"bookmaker": bmk, "price": price}
                for bmk, price in per_bookmaker.items()
                if MIN_PRICE <= price <= MAX_PRICE
            ]

            if len(filtered) < MIN_BOOKMAKERS_PER_OUTCOME:
                continue

            prices = [x["price"] for x in filtered]
            market_avg = sum(prices) / len(prices)

            min_price = min(prices)
            max_price = max(prices)
            if min_price <= 0:
                continue

            market_spread_percent = ((max_price - min_price) / min_price) * 100
            if market_spread_percent > MAX_MARKET_SPREAD_PERCENT:
                continue

            for item in filtered:
                bookmaker_price = item["price"]
                deviation_percent = ((bookmaker_price - market_avg) / market_avg) * 100

                if deviation_percent < MIN_DEVIATION_PERCENT:
                    continue

                market_prob = 1 / market_avg
                implied_prob = 1 / bookmaker_price
                expected_value = (market_prob * bookmaker_price) - 1
                signal_score = (deviation_percent * 0.7) + (expected_value * 100 * 0.3)

                if expected_value < MIN_EXPECTED_VALUE:
                    continue

                anomaly_key = (
                    home,
                    away,
                    outcome_name,
                    item["bookmaker"],
                    round(bookmaker_price, 4),
                )

                if anomaly_key in seen_anomalies:
                    continue

                cur.execute(
                    """
                    INSERT INTO odds_anomalies
                    (
                        home, away, bookmaker, outcome,
                        market_avg, bookmaker_price, deviation_percent, created_at,
                        implied_prob, market_prob, expected_value, signal_score
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        home,
                        away,
                        item["bookmaker"],
                        outcome_name,
                        round(market_avg, 4),
                        round(bookmaker_price, 4),
                        round(deviation_percent, 2),
                        now_utc,
                        round(implied_prob, 6),
                        round(market_prob, 6),
                        round(expected_value, 4),
                        round(signal_score, 2),
                    ),
                )

                seen_anomalies.add(anomaly_key)
                anomaly_rows += 1

                print(
                    f"ANOMALY | {home} vs {away} | {outcome_name} | "
                    f"{item['bookmaker']} | price={bookmaker_price:.2f} | "
                    f"avg={market_avg:.2f} | dev={deviation_percent:.2f}% | "
                    f"ev={expected_value:.4f} | score={signal_score:.2f}"
                )

                if signal_score >= 10:
                    message = (
                        f"Anomaly signal\n"
                        f"{home} vs {away}\n"
                        f"Ishod: {outcome_name}\n"
                        f"Bookmaker: {item['bookmaker']}\n"
                        f"Kvota: {bookmaker_price:.2f}\n"
                        f"Market avg: {market_avg:.2f}\n"
                        f"Dev: {deviation_percent:.2f}%\n"
                        f"EV: {expected_value:.4f}\n"
                        f"Score: {signal_score:.2f}"
                    )
                    send_telegram_message(message)

    conn.commit()
    cur.close()
    conn.close()

    print(f"Saved history rows: {history_rows}")
    print(f"Saved anomaly rows: {anomaly_rows}")
    print("Done. Sleeping...")


def worker_loop():
    while True:
        try:
            fetch_odds()
        except Exception as e:
            print("Error:", e)

        time.sleep(FETCH_INTERVAL_SECONDS)


@app.on_event("startup")
def start_background_worker():
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()
