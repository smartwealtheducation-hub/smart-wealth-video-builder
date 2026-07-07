from flask import Flask, request, jsonify, send_file
import os
import requests
import uuid

app = Flask(__name__)

# Load API Keys from environment variables
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

@app.route("/test", methods=["GET"])
def test():
    return jsonify(status="build-video endpoint ready", url="/build-video")

@app.route("/build-video", methods=["POST"])
def build_video():
    try:
        data = request.get_json()
        if not data or "script" not in data:
            return jsonify({"error": "Missing 'script' field"}), 400
        
        # Confirmation response
        return jsonify({
            "status": "accepted",
            "job_id": data.get("job_id"),
            "message": "Video build request received successfully"
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
