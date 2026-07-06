from flask import Flask, request, jsonify, send_file
import os
import requests
import subprocess
import uuid

app = Flask(__name__)

# Load API keys from environment variables
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY")
PORT = int(os.getenv("PORT", 8080))

# Temporary folder for outputs
OUTPUT_FOLDER = "/tmp/swa_videos"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route("/")
def home():
    return jsonify(status="running", message="Video Builder API is active")

@app.route("/health")
def health():
    return jsonify(healthy=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
