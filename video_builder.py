
import os
import re
import json
import time
import base64
import logging
import tempfile
import subprocess
import requests
import threading
from pathlib import Path
from flask import Flask, request, jsonify, send_file

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("VideoBuilder")

app = Flask(__name__)

PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
GOOGLE_TTS_KEY = os.environ.get("GOOGLE_TTS_API_KEY", "")
PORT = int(os.environ.get("PORT", 8080))
OUTPUT_DIR = Path("/tmp/swa_videos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

job_status = {}

def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:])
    return result

def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", str(path)],
        capture_output=True, text=True
    )
    try:
        for s in json.loads(r.stdout).get("streams", []):
            if s.get("duration"):
                return float(s["duration"])
    except:
        pass
    return 0.0

def generate_tts(text, out_path):
    chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
    parts = []
    for i, chunk in enumerate(chunks):
        url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={GOOGLE_TTS_KEY}"
        payload = {
            "input": {"text": chunk},
            "voice": {"languageCode": "en-US", "name": "en-US-Wavenet-D"},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95}
        }
        r = requests.post(url, json=payload, timeout=30)
        if not r.ok:
            raise RuntimeError(f"TTS failed: {r.text[:200]}")
        p = out_path.parent / f"part_{i}.mp3"
        p.write_bytes(base64.b64decode(r.json()["audioContent"]))
        parts.append(p)

    if len(parts) == 1:
        import shutil
        shutil.copy(parts[0], out_path)
    else:
        concat = out_path.parent / "tts_concat.txt"
        concat.write_text("\n".join(f"file '{p}'" for p in parts))
        run_cmd(["ffmpeg", "-f", "concat", "-safe", "0",
                 "-i", str(concat), "-c", "copy", str(out_path), "-y"])
    return get_duration(out_path)

def get_pexels_clips(keywords, needed_secs, work_dir):
    headers = {"Authorization": PEXELS_KEY}
    clips = []
    terms = keywords[:5] + ["finance", "money", "business", "investing"]
    for term in terms:
        if sum(c[1] for c in clips) >= needed_secs + 20:
            break
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": term, "per_page": 5,
                        "min_duration": 5, "max_duration": 20,
                        "orientation": "landscape"},
                timeout=15
            )
            if not r.ok:
                continue
            for vid in r.json().get("videos", []):
                files = [f for f in vid["video_files"]
                         if 640 <= f.get("width", 0) <= 1920
                         and f.get("file_type") == "video/mp4"]
                if not files:
                    continue
                best = sorted(files, key=lambda f: abs(f.get("width", 0) - 1280))[0]
                out = work_dir / f"raw_{len(clips)}.mp4"
                with requests.get(best["link"], stream=True, timeout=30) as dl:
                    if dl.ok:
                        out.write_bytes(dl.content)
                        if out.stat().st_size > 10000:
                            clips.append((out, vid["duration"]))
        except Exception as e:
            log.warning("Pexels error: %s", e)
        time.sleep(0.2)
    if not clips:
        raise RuntimeError("No Pexels clips downloaded")
    return clips

def build_video_job(job_id, script, title, keywords):
    try:
        job_status[job_id] = "running"
        log.info("Job %s starting", job_id)

        with tempfile.TemporaryDirectory(prefix="swa_") as tmp:
            work = Path(tmp)
            voice = work / "voice.mp3"

            # Step 1: TTS
            log.info("Generating TTS...")
            duration = generate_tts(script, voice)
            log.info("TTS done: %.1fs", duration)

            # Step 2: Pexels clips
            log.info("Fetching Pexels clips...")
            clips = get_pexels_clips(keywords, duration, work)
            log.info("Got %d clips", len(clips))

            # Step 3: Normalise clips
            norm = []
            for i, (clip, _) in enumerate(clips):
                out = work / f"norm_{i}.mp4"
                try:
                    run_cmd(["ffmpeg", "-i", str(clip),
                             "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=25",
                             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                             "-an", str(out), "-y"])
                    norm.append(out)
                except:
                    continue

            if not norm:
                raise RuntimeError("No clips normalised")

            # Step 4: Loop clips to cover duration
            needed = duration + 3
            looped = []
            total = 0.0
            idx = 0
            while total < needed:
                src = norm[idx % len(norm)]
                d = get_duration(src) or 8.0
                looped.append(src)
                total += d
                idx += 1
                if idx > 100:
                    break

            concat_file = work / "concat.txt"
            concat_file.write_text("\n".join(f"file '{p}'" for p in looped))

            raw_video = work / "raw.mp4"
            run_cmd(["ffmpeg", "-f", "concat", "-safe", "0",
                     "-i", str(concat_file),
                     "-t", str(needed),
                     "-c", "copy", str(raw_video), "-y"])

            # Step 5: Add title overlay
            safe_title = title[:50].replace("'", "\\'").replace(":", "\\:")
            vf = (f"drawtext=text='{safe_title}':"
                  f"fontsize=40:fontcolor=white:bordercolor=black:borderw=2:"
                  f"x=(w-tw)/2:y=(h/2)-30:enable='between(t,0,3)',"
                  f"drawtext=text='Smart Wealth Academy':"
                  f"fontsize=22:fontcolor=yellow:bordercolor=black:borderw=1:"
                  f"x=w-tw-10:y=h-th-10")

            # Step 6: Final render
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", title)[:35]
            out_path = OUTPUT_DIR / f"{safe_name}_{job_id}.mp4"

            run_cmd(["ffmpeg",
                     "-i", str(raw_video),
                     "-i", str(voice),
                     "-filter_complex", f"[0:v]{vf}[vout]",
                     "-map", "[vout]", "-map", "1:a",
                     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                     "-c:a", "aac", "-b:a", "128k",
                     "-t", str(duration + 1),
                     "-movflags", "+faststart",
                     str(out_path), "-y"])

            size_mb = round(out_path.stat().st_size / 1_048_576, 1)
            log.info("Job %s complete: %s (%.1fMB)", job_id, out_path.name, size_mb)
            job_status[job_id] = {
                "status": "complete",
                "video_url": f"/download/{out_path.name}",
                "size_mb": size_mb,
                "duration_s": round(duration, 1)
            }

    except Exception as e:
        log.exception("Job %s failed", job_id)
        job_status[job_id] = {"status": "failed", "error": str(e)}


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"healthy": True})


@app.route("/build-video", methods=["POST"])
def build_video():
    data = request.get_json(force=True, silent=True) or {}
    script = data.get("script", "").strip()
    title = data.get("title", "Smart Wealth Academy")
    keywords = data.get("keywords", ["finance", "money", "investing"])
    job_id = str(data.get("job_id", int(time.time())))

    if not script:
        return jsonify({"error": "script required"}), 400

    thread = threading.Thread(
        target=build_video_job,
        args=(job_id, script, title, keywords),
        daemon=True
    )
    thread.start()

    return jsonify({
        "message": "Video build started",
        "job_id": job_id,
        "status_url": f"/status/{job_id}"
    }), 202


@app.route("/status/<job_id>", methods=["GET"])
def status(job_id):
    s = job_status.get(job_id, "not_found")
    return jsonify({"job_id": job_id, "result": s})


@app.route("/download/<filename>", methods=["GET"])
def download(filename):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return jsonify({"error": "not found"}), 404
    return send_file(str(path), mimetype="video/mp4",
                     as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
