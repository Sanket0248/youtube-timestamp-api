import os, re, time, tempfile
from fastapi import FastAPI
from pydantic import BaseModel
import google.generativeai as genai
import yt_dlp

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

class AskRequest(BaseModel):
    video_url: str
    topic: str

@app.get("/")
def root():
    return {"status": "running"}

@app.post("/ask")
async def ask(req: AskRequest):
    tmp_dir = tempfile.mkdtemp()
    audio_path = os.path.join(tmp_dir, "audio.mp3")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "audio.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([req.video_url])

    for f in os.listdir(tmp_dir):
        if f.endswith(".mp3"):
            audio_path = os.path.join(tmp_dir, f)
            break

    uploaded = genai.upload_file(audio_path, mime_type="audio/mpeg")

    while uploaded.state.name != "ACTIVE":
        time.sleep(2)
        uploaded = genai.get_file(uploaded.name)

    model = genai.GenerativeModel("gemini-2.0-flash")
    prompt = f"""Listen to this audio carefully.
Find the exact moment when the topic "{req.topic}" is first spoken or discussed.
Return ONLY the timestamp in HH:MM:SS format (e.g. 00:05:47).
Do not include any explanation, just the timestamp."""

    response = model.generate_content([uploaded, prompt])
    raw = response.text.strip()

    match = re.search(r'\d{1,2}:\d{2}:\d{2}', raw)
    if match:
        parts = match.group().split(":")
        timestamp = f"{int(parts[0]):02d}:{parts[1]}:{parts[2]}"
    else:
        match2 = re.search(r'\d{1,2}:\d{2}', raw)
        if match2:
            parts = match2.group().split(":")
            timestamp = f"00:{int(parts[0]):02d}:{parts[1]}"
        else:
            timestamp = "00:00:00"

    try:
        os.remove(audio_path)
        genai.delete_file(uploaded.name)
    except:
        pass

    return {
        "timestamp": timestamp,
        "video_url": req.video_url,
        "topic": req.topic
    }
