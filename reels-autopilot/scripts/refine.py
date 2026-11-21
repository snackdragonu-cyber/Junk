#!/usr/bin/env python3
"""Retranscrie doar fragmentele alese cu un model Whisper mai precis.

Transcrierea întregului video cu `small` e rapidă, dar greșește cuvinte. Fragmentele
din clips.json (cu puțină margine) se refac cu `medium` și le înlocuiesc pe cele vechi.

Utilizare:
  python refine.py VIDEO TRANSCRIPT_JSON CLIPS_JSON OUT_JSON [--model medium] [--language ro]
"""
import argparse
import json
import os
import subprocess

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--language", default="ro")
    ap.add_argument("--margin", type=float, default=2.0)
    a = ap.parse_args()

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from faster_whisper import WhisperModel

    with open(a.transcript, encoding="utf-8") as f:
        d = json.load(f)
    with open(a.clips, encoding="utf-8") as f:
        clips = json.load(f)
    if isinstance(clips, dict):
        clips = clips["clips"]

    model = WhisperModel(a.model, device="cpu", compute_type="int8",
                         cpu_threads=os.cpu_count() or 4)
    for c in clips:
        s0, s1 = max(0.0, c["start"] - a.margin), c["end"] + a.margin
        raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(s0), "-t", str(s1 - s0),
                              "-i", a.video, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             check=True, capture_output=True).stdout
        segs, _ = model.transcribe(np.frombuffer(raw, np.float32), language=a.language,
                                   word_timestamps=True, beam_size=5, vad_filter=True)
        new = []
        for s in segs:
            ws = [{"start": round(w.start + s0, 3), "end": round(w.end + s0, 3), "word": w.word.strip()}
                  for w in (s.words or []) if w.word.strip()]
            if ws:
                new.append({"start": round(s.start + s0, 3), "end": round(s.end + s0, 3),
                            "text": s.text.strip(), "words": ws})
                print(f"[{s.start + s0:.1f}-{s.end + s0:.1f}] {s.text.strip()}")
        print("---")
        d["segments"] = [s for s in d["segments"] if s["end"] <= s0 or s["start"] >= s1] + new
        d["segments"].sort(key=lambda s: s["start"])

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
