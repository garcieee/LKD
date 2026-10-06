"""Lakad API. Health route only until kickoff (Tue 1:00 PM)."""
from fastapi import FastAPI

app = FastAPI(title="Lakad API")


@app.get("/health")
def health():
    return {"ok": True}
