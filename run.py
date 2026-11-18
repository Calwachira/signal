"""Start Signalboard:  python run.py"""
import os

import uvicorn

from app.config import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
