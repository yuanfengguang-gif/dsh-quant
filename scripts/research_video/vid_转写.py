# -*- coding: utf-8 -*-
"""_video_research/transcribe.py —— faster-whisper 转写（支持切片试跑）

用法：
    python transcribe.py v01            # 全片
    python transcribe.py v01 --slice 60 # 只跑前 60 秒（测速）
    python transcribe.py v01 --model small
"""
import sys, json, time, subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT = Path(r"C:\Users\Administrator\ DSH 量化交易系统\_video_research")
FFMPEG = r"C:\Users\Administrator\ffmpeg\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "v01"
    model_size = "small"
    sl = None
    for i, a in enumerate(sys.argv):
        if a == "--model" and i + 1 < len(sys.argv):
            model_size = sys.argv[i + 1]
        if a == "--slice" and i + 1 < len(sys.argv):
            sl = float(sys.argv[i + 1])

    mp4 = OUT / f"{tag}.mp4"
    if not mp4.exists():
        sys.exit(f"❌ 找不到 {mp4}")

    wav = OUT / f"{tag}.wav"
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(mp4), "-vn",
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"]
    if sl:
        cmd += ["-t", str(sl)]
    cmd += [str(wav)]
    subprocess.run(cmd, check=True)
    print(f"  音频已提取 {wav.name}  {wav.stat().st_size/1024/1024:.2f} MB")

    from faster_whisper import WhisperModel
    t0 = time.time()
    print(f"  加载模型 {model_size} …")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"  模型就绪（{time.time()-t0:.1f}s），开始转写 …")
    t1 = time.time()
    segments, info = model.transcribe(
        str(wav), language="zh", beam_size=5, vad_filter=True,
        initial_prompt="以下是关于金融、投资、红利ETF、量化交易的中文讲解。")
    print(f"  识别语言 {info.language}（置信度 {info.language_probability:.2f}），"
          f"音频时长 {info.duration:.1f}s")

    rows = []
    for seg in segments:
        rows.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                     "text": seg.text.strip()})
        if len(rows) % 20 == 0:
            print(f"    …已转 {rows[-1]['end']:.0f}s / {info.duration:.0f}s")
    el = time.time() - t1
    print(f"  ✅ 转写完成：{len(rows)} 段，用时 {el:.1f}s "
          f"（实时率 {info.duration/el:.2f}x）")

    suffix = f"_slice{int(sl)}" if sl else ""
    (OUT / f"{tag}_transcript{suffix}.json").write_text(
        json.dumps({"tag": tag, "model": model_size, "duration": info.duration,
                    "segments": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    txt = "\n".join(f"[{r['start']:>7.2f}-{r['end']:>7.2f}] {r['text']}" for r in rows)
    (OUT / f"{tag}_transcript{suffix}.txt").write_text(txt, encoding="utf-8")
    print(f"  已保存 {tag}_transcript{suffix}.json / .txt")
    print(f"\n  ── 前 8 段 ──")
    for r in rows[:8]:
        print(f"    [{r['start']:.1f}-{r['end']:.1f}] {r['text'][:80]}")


if __name__ == "__main__":
    main()
