from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import psycopg2
import os
import datetime

app = FastAPI()

API_KEY = os.getenv("API_KEY")

def fetch_odds():
    print("Fetching odds...")

    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={API_KEY}&regions=eu&markets=h2h"
    res = requests.get(url)
    data = res.json()

    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    for match in data:
        home = match["home_team"]
        away = match["away_team"]

        for bookmaker in match["bookmakers"]:
            for market in bookmaker["markets"]:
                for outcome in market["outcomes"]:
                    cur.execute("""
                        INSERT INTO odds_history (home, away, bookmaker, outcome, price, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        home,
                        away,
                        bookmaker["title"],
                        outcome["name"],
                        outcome["price"],
                        datetime.datetime.now()
                    ))

    conn.commit()
    cur.close()
    conn.close()

scheduler = BackgroundScheduler()
scheduler.add_job(fetch_odds, "interval", minutes=15)
scheduler.start()

@app.get("/")
def root():
    return {"status": "running"}
