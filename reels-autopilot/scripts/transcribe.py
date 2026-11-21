#!/usr/bin/env python3
"""Transcrie un video cu faster-whisper, cu timpi pe fiecare cuvânt.

Scrie două fișiere în OUT_DIR:
  transcript.json - segmente + cuvinte cu timpi (input pentru render.py)
  transcript.txt  - text compact "[mm:ss.s-mm:ss.s] text" pentru citit și ales momentele

Utilizare:
  python transcribe.py VIDEO OUT_DIR [--model small] [--language ro]
"""
import argparse
import json
import os
import subprocess
import sys


def fmt(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="small",
                    help="tiny|base|small|medium|large-v3 (mai mare = mai precis, mai lent)")
    ap.add_argument("--language", default="ro")
    args = ap.parse_args()

    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from faster_whisper import WhisperModel

    os.makedirs(args.out_dir, exist_ok=True)

    # Audio mono 16 kHz decodat de ffmpeg direct în memorie: evită dependența de PyAV,
    # care diferă des ca versiune între medii.
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", args.video, "-vn",
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    wav = np.frombuffer(raw, dtype=np.float32)
    if True:
        model = WhisperModel(args.model, device="cpu", compute_type="int8",
                             cpu_threads=os.cpu_count() or 4)
        segments, info = model.transcribe(
            wav, language=args.language, word_timestamps=True,
            vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
            beam_size=5)

        out_segments = []
        for seg in segments:
            words = [{"start": round(w.start, 3), "end": round(w.end, 3),
                      "word": w.word.strip()} for w in (seg.words or []) if w.word.strip()]
            if not words:
                continue
            out_segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                                 "text": seg.text.strip(), "words": words})
            print(f"[{fmt(seg.start)}-{fmt(seg.end)}] {seg.text.strip()}", file=sys.stderr)

    data = {"language": info.language, "duration": round(info.duration, 3),
            "segments": out_segments}
    with open(os.path.join(args.out_dir, "transcript.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out_dir, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write(f"# durata: {fmt(info.duration)}  limba: {info.language}\n")
        for s in out_segments:
            f.write(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}\n")
    print(f"OK: {len(out_segments)} segmente, {fmt(info.duration)}", file=sys.stderr)


if __name__ == "__main__":
    main()
