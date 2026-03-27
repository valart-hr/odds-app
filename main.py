from fastapi import FastAPI
import requests
import psycopg2
import os
import datetime
import time
import threading

app = FastAPI()

API_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

FETCH_INTERVAL_SECONDS = 60
MIN_BOOKMAKERS_PER_OUTCOME = 3
MIN_PRICE = 1.50
MAX_PRICE = 5.00
MIN_DEVIATION_PERCENT = 8.0


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/health")
def health():
    return {"ok": True}


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def normalize_text(value: str) -> str:
    return (value or "").strip()


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
            if market_spread_percent > 80:
                continue

            for item in filtered:
                bookmaker_price = item["price"]
                deviation_percent = ((bookmaker_price - market_avg) / market_avg) * 100

                if deviation_percent < MIN_DEVIATION_PERCENT:
                    continue

                anomaly_key = (home, away, outcome_name, item["bookmaker"], round(bookmaker_price, 4))
                if anomaly_key in seen_anomalies:
                    continue

                cur.execute(
                    """
                    INSERT INTO odds_anomalies
                    (home, away, bookmaker, outcome, market_avg, bookmaker_price, deviation_percent, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
                    ),
                )

                seen_anomalies.add(anomaly_key)
                anomaly_rows += 1

                print(
                    f"ANOMALY | {home} vs {away} | {outcome_name} | "
                    f"{item['bookmaker']} | price={bookmaker_price:.2f} | "
                    f"avg={market_avg:.2f} | dev={deviation_percent:.2f}%"
                )

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
