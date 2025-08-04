# keep_alive.py
from flask import Flask
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"
