#!/usr/bin/env python3
"""Montează reels 9:16 dintr-un video lung: tăieturi, eliminarea pauzelor,
reîncadrare verticală, subtitrări dinamice (cuvânt cu cuvânt) și sunet normalizat.

Utilizare:
  python render.py VIDEO TRANSCRIPT_JSON CLIPS_JSON OUT_DIR [opțiuni]

CLIPS_JSON = listă de obiecte (sau {"fixes": {"greșit": "corect"}, "clips": [...]}):
  [{"id": 1, "start": 125.4, "end": 171.0, "hook": "Text scurt sus, primele 3 s (opțional)",
    "crop_x": 0.5}]            # crop_x opțional: 0 = stânga, 0.5 = centru, 1 = dreapta

Ieșire: OUT_DIR/reel_01.mp4, ... și OUT_DIR/render_report.json
"""
import argparse
import json
import os
import re
import subprocess
import sys

W, H = 1080, 1920
PUNCT_END = re.compile(r"[.!?…;:]$")


def probe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", video],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])


def words_in(transcript, start, end):
    ws = []
    for seg in transcript["segments"]:
        for w in seg["words"]:
            if w["start"] >= start - 0.05 and w["end"] <= end + 0.05:
                ws.append(dict(w))
    return ws


def keep_ranges(words, clip_start, clip_end, gap, pad, jumpcut):
    """Intervalele de păstrat. Cu jumpcut, pauzele mai lungi de `gap` secunde sunt tăiate."""
    if not words:
        return [(clip_start, clip_end)]
    if not jumpcut:
        return [(max(clip_start, words[0]["start"] - pad), min(clip_end, words[-1]["end"] + pad))]
    ranges = []
    cur = [words[0]["start"] - pad, words[0]["end"] + pad]
    for w in words[1:]:
        if w["start"] - (cur[1] - pad) > gap:
            ranges.append(cur)
            cur = [w["start"] - pad, w["end"] + pad]
        else:
            cur[1] = w["end"] + pad
    ranges.append(cur)
    # limite, fără suprapuneri, fără bucăți minuscule (produc pocnituri în audio)
    out = []
    for a, b in ranges:
        a, b = max(a, clip_start), min(b, clip_end)
        if out and a < out[-1][1]:
            a = out[-1][1]
        if b - a >= 0.25:
            out.append((round(a, 3), round(b, 3)))
    return out or [(clip_start, clip_end)]


def remap(words, ranges):
    """Mută timpii cuvintelor pe cronologia de după tăieturi."""
    offsets, acc = [], 0.0
    for a, b in ranges:
        offsets.append(acc)
        acc += b - a
    out = []
    for w in words:
        for (a, b), off in zip(ranges, offsets):
            if a - 0.01 <= w["start"] <= b:
                out.append({"word": w["word"],
                            "start": off + w["start"] - a,
                            "end": off + min(w["end"], b) - a})
                break
    return out, acc


def ass_time(t):
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


EMOJI = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200D]")


def ass_escape(s):
    # fonturile de sistem nu au emoji: ar apărea ca pătrățele, deci le scoatem
    s = EMOJI.sub("", s).strip()
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def chunk_words(words, max_words, max_chars):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        text_len = sum(len(x["word"]) + 1 for x in cur)
        if (nxt is None or len(cur) >= max_words or text_len >= max_chars
                or PUNCT_END.search(w["word"]) or nxt["start"] - w["end"] > 0.5):
            chunks.append(cur)
            cur = []
    return chunks


def build_ass(words, total, hook, a):
    hi = a.highlight  # format ASS: &HBBGGRR
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{a.font},{a.font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{a.margin_v},1
Style: Hook,{a.font},62,&H00FFFFFF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(3.0, total))},Hook,,0,0,0,,"
                     f"{{\\fad(150,250)}}{ass_escape(hook)}")
    chunks = chunk_words(words, a.words_per_line, a.max_chars)
    for ci, ch in enumerate(chunks):
        next_start = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        chunk_end = min(ch[-1]["end"] + 0.25, next_start)
        tokens = [ass_escape(w["word"]).upper() if a.uppercase else ass_escape(w["word"]) for w in ch]
        for k, w in enumerate(ch):
            st = w["start"]
            en = ch[k + 1]["start"] if k + 1 < len(ch) else chunk_end
            if en <= st:
                continue
            parts = []
            for j, tok in enumerate(tokens):
                if j == k:
                    parts.append(f"{{\\c{hi}\\fscx100\\fscy100\\t(0,90,\\fscx{a.pop}\\fscy{a.pop})}}"
                                 f"{tok}{{\\r}}")
                else:
                    parts.append(tok)
            lines.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},Cap,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"


def video_chain(src_w, src_h, mode, crop_x):
    cover = (f"scale=w='if(gt(a,{W}/{H}),-2,{W})':h='if(gt(a,{W}/{H}),{H},-2)',"
             f"crop={W}:{H}:x='(iw-{W})*{crop_x}':y='(ih-{H})/2'")
    if mode == "auto":
        # orizontală la rezoluție mică → pătrat (un crop 9:16 ar fi mărit de 5x și neclar);
        # altfel crop vertical pe vorbitor
        mode = "square" if (src_w > src_h and src_h < 900) else "crop"
    if mode == "crop":
        return f"[vc]{cover},setsar=1[vr]"
    if mode == "square":
        # pătrat ih×ih pe vorbitor, mărit la 1080×1080, peste fundal estompat;
        # titlul stă deasupra pătratului, subtitrările dedesubt
        return (f"[vc]split[bgs][fgs];[bgs]{cover},gblur=sigma=40,eq=brightness=-0.15[bg];"
                f"[fgs]crop=ih:ih:x='(iw-ih)*{crop_x}':y=0,scale={W}:{W}:flags=lanczos,"
                f"unsharp=5:5:0.6[fg];[bg][fg]overlay=0:(H-h)/2,setsar=1[vr]")
    # blur: fundal estompat + imaginea întreagă la mijloc
    return (f"[vc]split[bgs][fgs];[bgs]{cover},gblur=sigma=40,eq=brightness=-0.08[bg];"
            f"[fgs]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[vr]")


def apply_fixes(words, fixes):
    """Corectează cuvinte greșit transcrise; păstrează punctuația lipită de cuvânt."""
    if not fixes:
        return words
    low = {k.lower(): v for k, v in fixes.items()}
    for w in words:
        m = re.match(r"^(\W*)(.*?)(\W*)$", w["word"])
        pre, core, post = m.groups()
        if core.lower() in low:
            w["word"] = pre + low[core.lower()] + post
    return words


def render_clip(video, src_w, src_h, transcript, clip, out_dir, a, fixes=None):
    cid = int(clip.get("id", 1))
    words = words_in(transcript, clip["start"], clip["end"])
    words = apply_fixes(words, {**(fixes or {}), **clip.get("fixes", {})})
    ranges = keep_ranges(words, clip["start"], clip["end"], a.gap, a.pad, not a.no_jumpcut)
    new_words, total = remap(words, ranges)

    ass_name = f"reel_{cid:02d}.ass"
    with open(os.path.join(out_dir, ass_name), "w", encoding="utf-8") as f:
        f.write(build_ass(new_words, total, clip.get("hook", "") if not a.no_hook else "", a))

    seek = max(0.0, ranges[0][0] - 1.0)
    span = ranges[-1][1] - seek + 0.5
    parts, labels = [], []
    for i, (s, e) in enumerate(ranges):
        s, e = s - seek, e - seek
        parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d=0.02,afade=t=out:st={max(0, e - s - 0.02):.3f}:d=0.02[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append(f"{''.join(labels)}concat=n={len(ranges)}:v=1:a=1[vc][ac]")
    parts.append(video_chain(src_w, src_h, a.reframe, float(clip.get("crop_x", a.crop_x))))
    parts.append(f"[vr]fps=30,ass={ass_name},format=yuv420p[vout]")
    parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

    out_name = f"reel_{cid:02d}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{seek:.3f}", "-t", f"{span:.3f}",
           "-i", os.path.abspath(video), "-filter_complex", ";".join(parts),
           "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", a.preset,
           "-crf", str(a.crf), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
           out_name]
    subprocess.run(cmd, check=True, cwd=out_dir)
    out_path = os.path.join(out_dir, out_name)
    _, _, dur = probe(out_path)
    return {"id": cid, "file": out_path, "duration": round(dur, 2),
            "source_start": clip["start"], "source_end": clip["end"],
            "cuts_removed": len(ranges) - 1,
            "seconds_removed": round((clip["end"] - clip["start"]) - total, 2),
            "words": len(new_words), "size_mb": round(os.path.getsize(out_path) / 1e6, 1),
            "facebook_ok": 3 <= dur <= 90}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("transcript")
    ap.add_argument("clips")
    ap.add_argument("out_dir")
    ap.add_argument("--reframe", choices=["auto", "crop", "blur", "square"], default="auto")
    ap.add_argument("--crop-x", type=float, default=0.5)
    ap.add_argument("--gap", type=float, default=0.45, help="pauzele mai lungi de atât se taie (s)")
    ap.add_argument("--pad", type=float, default=0.12, help="aer lăsat în jurul vorbirii (s)")
    ap.add_argument("--no-jumpcut", action="store_true")
    ap.add_argument("--no-hook", action="store_true")
    ap.add_argument("--font", default="DejaVu Sans")
    ap.add_argument("--font-size", type=int, default=88)
    ap.add_argument("--margin-v", type=int, default=None, help="implicit 560; 300 în modul square (sub pătrat)")
    ap.add_argument("--words-per-line", type=int, default=3)
    ap.add_argument("--max-chars", type=int, default=18)
    ap.add_argument("--highlight", default="&H0000E6FF&", help="culoare ASS &HBBGGRR& (implicit galben)")
    ap.add_argument("--pop", type=int, default=115, help="mărirea cuvântului curent, în %%")
    ap.add_argument("--no-uppercase", dest="uppercase", action="store_false")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--crf", type=int, default=20)
    a = ap.parse_args()

    with open(a.transcript, encoding="utf-8") as f:
        transcript = json.load(f)
    with open(a.clips, encoding="utf-8") as f:
        clips = json.load(f)
    fixes = {}
    if isinstance(clips, dict):  # {"fixes": {...}, "clips": [...]}
        fixes, clips = clips.get("fixes", {}), clips["clips"]
    os.makedirs(a.out_dir, exist_ok=True)
    src_w, src_h, _ = probe(a.video)
    if a.margin_v is None:
        square = a.reframe == "square" or (a.reframe == "auto" and src_w > src_h and src_h < 900)
        a.margin_v = 300 if square else 560

    report = []
    for clip in clips:
        r = render_clip(a.video, src_w, src_h, transcript, clip, a.out_dir, a, fixes)
        print(json.dumps(r, ensure_ascii=False), file=sys.stderr)
        report.append(r)
    with open(os.path.join(a.out_dir, "render_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
