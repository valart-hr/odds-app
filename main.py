import requests
import psycopg2
import os
import datetime
import time

API_KEY = os.getenv("API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

def fetch_odds():
    print("Fetching odds...")

    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={API_KEY}&regions=eu&markets=h2h"

    res = requests.get(url)
    data = res.json()

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    for match in data:
        home = match["home_team"]
        away = match["away_team"]

        outcomes_dict = {}

        for bookmaker in match["bookmakers"]:
            bookmaker_name = bookmaker["title"]

            for market in bookmaker["markets"]:
                for outcome in market["outcomes"]:
                    outcome_name = outcome["name"]
                    price = float(outcome["price"])

                    # INSERT u history
                    cur.execute("""
                        INSERT INTO odds_history (home, away, bookmaker, outcome, price, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        home,
                        away,
                        bookmaker_name,
                        outcome_name,
                        price,
                        datetime.datetime.utcnow()
                    ))

                    # grupiranje po outcome-u
                    if outcome_name not in outcomes_dict:
                        outcomes_dict[outcome_name] = []

                    outcomes_dict[outcome_name].append({
                        "bookmaker": bookmaker_name,
                        "price": price
                    })

        # ANALIZA PO OUTCOME (KLJUČNO!)
        for outcome_name, odds_list in outcomes_dict.items():
            prices = [o["price"] for o in odds_list]
            avg_price = sum(prices) / len(prices)

            for o in odds_list:
                deviation = ((o["price"] - avg_price) / avg_price) * 100

                if deviation > 10:  # 🔥 VALUE BET
                    cur.execute("""
                        INSERT INTO odds_anomalies
                        (home, away, bookmaker, outcome, market_avg, bookmaker_price, deviation_percent, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        home,
                        away,
                        o["bookmaker"],
                        outcome_name,
                        avg_price,
                        o["price"],
                        deviation,
                        datetime.datetime.utcnow()
                    ))

    conn.commit()
    cur.close()
    conn.close()

    print("Done. Sleeping...")

if __name__ == "__main__":
    while True:
        fetch_odds()
        time.sleep(60)
