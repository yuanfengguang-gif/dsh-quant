# -*- coding: utf-8 -*-
"""_video_research/pipeline.py —— 批量：抓流 → 下载合并 → 转写

用法： python pipeline.py            # 跑全部未完成的
       python pipeline.py 02 05      # 只跑指定编号
每步幂等：已有 mp4 就跳过下载；已有 transcript 就跳过转写。
"""
import sys, json, re, time, subprocess, traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
import urllib.request

OUT = Path(r"C:\Users\Administrator\ DSH 量化交易系统\_video_research")
FFMPEG = r"C:\Users\Administrator\ffmpeg\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
MEDIA_HINT = re.compile(r"(douyinvod|video/tos|/playwm/|media-video|media-audio)", re.I)

# 编号 → (作者/主题 短名, 抖音短链)
VIDEOS = {
    "01": ("彤彤观市_AI泡沫",      "https://v.douyin.com/QCGG5zuPY8M/"),
    "02": ("银行螺丝钉_红利估值指标", "https://v.douyin.com/vwPMydr_FfM/"),
    "03": ("ETF罗盘_红利策略信号",   "https://v.douyin.com/oSdZL4RNRIo/"),
    "04": ("林姐财经_读懂金融危机",   "https://v.douyin.com/ZtVfx0xuZMw/"),
    "05": ("王死有钱_历史金融危机",   "https://v.douyin.com/seZlffTdBck/"),
    "06": ("MrKC_8个恐慌指标",      "https://v.douyin.com/p_IJmur32rg/"),
    "07": ("廖一山_全球TOP5指标",    "https://v.douyin.com/R9HhW4FZ4OA/"),
    "08": ("小姨随聊_红利ETF要管",   "https://v.douyin.com/qtIepJQHeiU/"),
    "09": ("光总_红利择时密码",      "https://v.douyin.com/4Rkzm-EG8xo/"),
    "10": ("ETF研学社_涨30还是分红9", "https://v.douyin.com/kLapvOhCsDY/"),
}


def log(tag, msg):
    print(f"[{tag}] {msg}", flush=True)


def grab(tag, url, headless=True):
    media, title = [], ""
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge", headless=headless,
                               args=["--autoplay-policy=no-user-gesture-required"])
        ctx = b.new_context(user_agent=UA, viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        pg = ctx.new_page()
        pg.on("request", lambda r: media.append(r.url) if MEDIA_HINT.search(r.url) else None)
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(3500)
        title = pg.title()
        try:
            pg.click("video", timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(2500)
        try:
            pg.keyboard.press("Space")
        except Exception:
            pass
        for _ in range(10):
            pg.wait_for_timeout(1000)
            if any("media-video" in u for u in media) and any("media-audio" in u for u in media):
                break
        try:
            dur = pg.evaluate("()=>{const v=document.querySelector('video');return v?v.duration:null}")
        except Exception:
            dur = None
        b.close()
    uniq = list(dict.fromkeys(media))
    vids = [u for u in uniq if "media-video" in u]
    auds = [u for u in uniq if "media-audio" in u]
    (OUT / f"{tag}_net.json").write_text(json.dumps(
        {"title": title, "duration": dur, "media": uniq}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(tag, f"标题={title[:52]!r} 时长={dur} 视频轨={len(vids)} 音频轨={len(auds)}")
    return vids[0] if vids else None, auds[0] if auds else None, title, dur


def dl(url, dst):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.douyin.com/",
        "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9", "Range": "bytes=0-"})
    n = 0
    with urllib.request.urlopen(req, timeout=180) as r, open(dst, "wb") as f:
        while True:
            c = r.read(1 << 20)
            if not c:
                break
            f.write(c)
            n += len(c)
    return n


def build(tag, vurl, aurl):
    v = OUT / f"{tag}_v.m4s"
    a = OUT / f"{tag}_a.m4s"
    n1 = dl(vurl, v)
    log(tag, f"视频轨 {n1/1024/1024:.2f} MB")
    mp4 = OUT / f"{tag}.mp4"
    if aurl:
        n2 = dl(aurl, a)
        log(tag, f"音频轨 {n2/1024/1024:.2f} MB")
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(v), "-i", str(a),
               "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", str(mp4)]
    else:
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(v), "-c", "copy", str(mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", str(v), "-i", str(a),
               "-c:v", "copy", "-c:a", "aac", str(mp4)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg 失败: {r.stderr[-300:]}")
    for f in (v, a):
        if f.exists():
            f.unlink()
    pr = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration,size",
                         "-of", "json", str(mp4)], capture_output=True, text=True)
    info = json.loads(pr.stdout or "{}").get("format", {})
    log(tag, f"✅ 合并 {float(info.get('duration',0)):.1f}s "
             f"{int(info.get('size',0))/1024/1024:.1f}MB")


def transcribe(tag, model_size="small"):
    wav = OUT / f"{tag}.wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(OUT / f"{tag}.mp4"),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    t0 = time.time()
    segs, info = model.transcribe(str(wav), language="zh", beam_size=5, vad_filter=True,
                                  initial_prompt="以下是关于金融、投资、红利ETF、量化交易、金融危机的中文讲解。")
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segs]
    el = time.time() - t0
    (OUT / f"{tag}_transcript.json").write_text(json.dumps(
        {"tag": tag, "model": model_size, "duration": info.duration, "segments": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / f"{tag}_transcript.txt").write_text(
        "\n".join(f"[{r['start']:>7.2f}-{r['end']:>7.2f}] {r['text']}" for r in rows),
        encoding="utf-8")
    wav.unlink(missing_ok=True)
    log(tag, f"✅ 转写 {len(rows)} 段 / {info.duration:.0f}s，用时 {el:.0f}s")


def main():
    want = [a for a in sys.argv[1:] if a in VIDEOS] or list(VIDEOS)
    print(f"  待处理：{want}", flush=True)
    summary = []
    for tag in want:
        name, url = VIDEOS[tag]
        mp4 = OUT / f"{tag}.mp4"
        tr = OUT / f"{tag}_transcript.json"
        if tr.exists():
            log(tag, "已转写，跳过")
            summary.append((tag, name, "skip", ""))
            continue
        try:
            if not mp4.exists():
                vurl, aurl, title, dur = grab(tag, url)
                if not vurl:
                    raise RuntimeError("未抓到视频轨")
                build(tag, vurl, aurl)
            else:
                log(tag, "已有 mp4，跳过下载")
            transcribe(tag)
            summary.append((tag, name, "ok", ""))
        except Exception as e:
            log(tag, f"❌ {type(e).__name__}: {e}")
            summary.append((tag, name, "FAIL", f"{type(e).__name__}: {e}"))
            traceback.print_exc()
    print("\n" + "=" * 70, flush=True)
    for tag, name, st, err in summary:
        print(f"  {tag} {name:<26s} {st}  {err[:70]}", flush=True)


if __name__ == "__main__":
    main()
