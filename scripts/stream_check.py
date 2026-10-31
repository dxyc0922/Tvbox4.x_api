#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析播放地址，判断源的来源类型和广告风险。

判断依据（按可靠性排序）：

1. **平台搬运**：播放地址落在抖音/快手/西瓜/B站等平台 CDN 上（如 `douyinvod.com`），
   这类源是把平台视频扒下来的，画质/音轨不可控，且常带水印、贴片。
2. **解析源**：`playerContent` 返回 `parse=1`，需要第三方解析器才能在网页里播放，
   广告和弹窗基本都在解析器那一侧。
3. **广告分片**：m3u8 的分片指向多个域名，少数域名只占几个分片 —— 这是插入广告最常见的形态。
4. **广告标记**：`#EXT-X-CUE-OUT` / `#EXT-X-DATERANGE` / `SCTE35`，标准的中插广告标记。
5. **自营源**：播放地址和站点主域名一致，说明是自己转码自己发，质量最可控。

注意：**不能**用「分片时长不规则」判断广告。实测大量正常转码源（VFR）同样存在
0.2–1 秒的短分片和大量 `#EXT-X-DISCONTINUITY`，按这个判会把正常源全判成广告。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import urllib.parse
from typing import Any

import requests
import urllib3

urllib3.disable_warnings()

UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

# 平台 CDN：命中即视为「搬运源」
PLATFORM_HOSTS = {
    "douyinvod.com": "抖音",
    "douyinpic.com": "抖音",
    "douyinstatic.com": "抖音",
    "douyincdn.com": "抖音",
    "ixigua.com": "西瓜视频",
    "ixiguavideo.com": "西瓜视频",
    "kuaishou.com": "快手",
    "kwimgs.com": "快手",
    "gifshow.com": "快手",
    "bilivideo.com": "B站",
    "bilivideo.cn": "B站",
    "hdslb.com": "B站",
    "iqiyi.com": "爱奇艺",
    "qiyipic.com": "爱奇艺",
    "youku.com": "优酷",
    "mgtv.com": "芒果TV",
    "gtimg.com": "腾讯视频",
    "sohu.com": "搜狐视频",
    "pptv.com": "PPTV",
    "le.com": "乐视",
    "weixin.qq.com": "微信",
}

MULTI_PART_SUFFIXES = {
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn",
    "com.hk", "com.tw", "co.jp", "co.uk", "com.au",
}

AD_KEYWORD = re.compile(
    r"(^|[/_.\-])(ad|ads|adv|advert|guanggao|gg|preroll|midroll|sponsor)([/_.\-]|$)",
    re.I,
)

# 字节系 VOD 存储路径：域名会轮换（douyinvod.com / zjcdn.com / ...），但路径稳定。
BYTEDANCE_PATH = re.compile(r"/video/tos/|/tos-cn-|tos-cn-v-", re.I)

GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3}


def registrable_domain(host: str) -> str:
    host = (host or "").strip()
    if "://" in host:
        host = urllib.parse.urlparse(host).netloc
    host = host.split("@")[-1].split(":")[0].lower().strip(".")
    if not host or re.fullmatch(r"[\d.]+", host):
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in MULTI_PART_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def platform_of(url_or_host: str) -> str | None:
    """命中平台 CDN 返回平台名。

    除了域名名单，还要看路径特征：字节的 VOD 存储路径形如
    `/video/tos/cn/tos-cn-v-xxxx/`，即使域名轮换成 zjcdn.com 也能认出来。
    """
    value = url_or_host or ""
    if "://" in value:
        parsed = urllib.parse.urlparse(value)
        host, path = parsed.netloc, parsed.path
    else:
        host, path = value, ""
    domain = registrable_domain(host)
    if domain in PLATFORM_HOSTS:
        return PLATFORM_HOSTS[domain]
    for suffix, name in PLATFORM_HOSTS.items():
        if domain == suffix or domain.endswith("." + suffix):
            return name
    if BYTEDANCE_PATH.search(path):
        return "抖音"
    return None


def site_relation(stream_url: str, site_hosts: list[str], final_url: str = "") -> str:
    """self / platform / third"""
    if platform_of(stream_url) or (final_url and platform_of(final_url)):
        return "platform"
    value = stream_url if "://" in stream_url else "http://" + stream_url
    target = registrable_domain(urllib.parse.urlparse(value).netloc)
    for site in site_hosts:
        if target and target == registrable_domain(site):
            return "self"
    return "third"


def request(
    url: str,
    referer: str | None = None,
    timeout: float = 12.0,
    stream: bool = False,
    headers: dict[str, str] | None = None,
):
    merged = {"User-Agent": UA}
    if referer:
        merged["Referer"] = referer
    if headers:
        merged.update(headers)
    return requests.get(
        url,
        headers=merged,
        timeout=timeout,
        verify=False,
        allow_redirects=True,
        stream=stream,
    )


FFPROBE = shutil.which("ffprobe")


def probe_media(url: str, referer: str | None, timeout: float = 8.0) -> dict[str, Any]:
    """用 ffprobe 读取视频流的分辨率和码率。

    mp4/直链视频直接读；HLS 也用它复核真实分辨率——master 里的 `RESOLUTION`
    经常是 `1080x608` 这种模板占位值（ffprobe 会把 dimensions 放在
    `programs[0].streams` 里）。
    没装 ffprobe、超时、流不可解析都返回空字典，调用方按「未知」处理。
    """
    if not FFPROBE:
        return {}
    headers = f"User-Agent: {UA}\r\n"
    if referer:
        headers += f"Referer: {referer}\r\n"
    limit = max(float(timeout), 3.0)
    command = [
        FFPROBE,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=bit_rate,height,width,avg_frame_rate",
        "-of", "json",
        "-probesize", "1000000",
        "-analyzeduration", "2000000",
        "-headers", headers,
        "-rw_timeout", str(int(limit * 1_000_000)),
        "-i", url,
    ]
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            timeout=limit + 2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if done.returncode != 0:
        return {}
    try:
        payload = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return {}
    streams = payload.get("streams") or []
    if not streams:
        programs = payload.get("programs") or []
        if programs and isinstance(programs[0], dict):
            streams = programs[0].get("streams") or []
    if not streams or not isinstance(streams[0], dict):
        return {}
    stream = streams[0]
    bitrate = stream.get("bit_rate")
    height = stream.get("height")
    width = stream.get("width")
    result: dict[str, Any] = {}
    if str(bitrate).isdigit() and int(bitrate) > 0:
        result["bitrate_kbps"] = round(int(bitrate) / 1000)
    if str(height).isdigit() and int(height) > 0:
        result["height"] = int(height)
    if str(width).isdigit() and int(width) > 0:
        result["width"] = int(width)
    rate = str(stream.get("avg_frame_rate") or "")
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            fps = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        if 0 < fps <= 120:
            result["fps"] = round(fps, 2)
    return result


def parse_master(text: str, base: str) -> list[dict[str, Any]]:
    variants = []
    pending: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF:"):
            pending = {}
            for item in line.split(":", 1)[1].split(","):
                key, _, value = item.partition("=")
                pending[key.strip().upper()] = value.strip()
        elif not line.startswith("#") and pending:
            variant = {
                "url": urllib.parse.urljoin(base, line),
                "bandwidth": int(pending.get("BANDWIDTH") or 0) if str(pending.get("BANDWIDTH", "")).isdigit() else 0,
                "resolution": pending.get("RESOLUTION") or "",
            }
            variants.append(variant)
            pending = {}
    return variants


def parse_media(text: str, base: str) -> dict[str, Any]:
    segments: list[str] = []
    durations: list[float] = []
    entries: list[dict[str, Any]] = []
    current: float | None = None
    tags: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            tags.append(line)
            if line.startswith("#EXTINF:"):
                try:
                    current = float(line.split(":", 1)[1].split(",")[0])
                except ValueError:
                    current = None
            continue
        url = urllib.parse.urljoin(base, line)
        duration = current if current is not None else 0.0
        segments.append(url)
        durations.append(duration)
        entries.append({"url": url, "duration": duration})
        current = None

    hosts: dict[str, int] = {}
    for segment in segments:
        host = urllib.parse.urlparse(segment).netloc
        hosts[host] = hosts.get(host, 0) + 1

    real = [value for value in durations if value > 0]
    return {
        "segments": len(segments),
        "hosts": hosts,
        "durations": real,
        "entries": entries,
        "tags": tags,
    }


def segment_size(url: str, referer: str | None, timeout: float) -> int:
    """取分片总字节数。用 Range 只请求 2 字节，靠 Content-Range 拿总大小。

    有些服务器不认 Range，会返回 200 + 完整 Content-Length；这里用 stream=True，
    拿到响应头就关闭，不会真的下载整个分片。
    """
    try:
        resp = request(
            url, referer, timeout, stream=True, headers={"Range": "bytes=0-1"}
        )
    except Exception:  # noqa: BLE001
        return 0
    try:
        if resp.status_code >= 400:
            return 0
        content_range = resp.headers.get("Content-Range") or ""
        if "/" in content_range:
            total = content_range.rsplit("/", 1)[-1].strip()
            if total.isdigit():
                return int(total)
        length = resp.headers.get("Content-Length") or ""
        return int(length) if length.isdigit() else 0
    finally:
        resp.close()


def estimate_bitrate(
    entries: list[dict[str, Any]],
    referer: str | None,
    timeout: float,
    samples: int = 24,
) -> int:
    """媒体列表没有 BANDWIDTH 时，用分片大小和 EXTINF 时长估算码率。

    实测这类源的 EXTINF 是 VFR 的（同一条线路里 0.2–10 秒的分片混排），
    单个分片的瞬时码率能从 249 kbps 跳到 6 Mbps，所以：
    - 按「总字节 / 总时长」算平均码率，不用中位数（会被静态画面拉低）；
    - 均匀取 24 个分片：实测 6 个样本个别源能偏 16%，12 个仍会受周期性内容影响，
      24 个基本能压到 ±6%，足够卡在阈值空档里。
    """
    usable = [entry for entry in entries if float(entry.get("duration") or 0) > 0]
    if not usable:
        return 0
    step = max(1, len(usable) // max(samples, 1))
    picks = usable[::step][:samples]
    total_bytes = 0
    total_seconds = 0.0
    for entry in picks:
        size = segment_size(str(entry["url"]), referer, timeout)
        if size <= 0:
            continue
        total_bytes += size
        total_seconds += float(entry["duration"])
    if total_seconds <= 0 or total_bytes <= 0:
        return 0
    return round(total_bytes * 8 / total_seconds / 1000)


def analyze_hls(url: str, referer: str | None, timeout: float) -> dict[str, Any]:
    resp = request(url, referer, timeout)
    text = resp.text
    if "#EXTM3U" not in text:
        return {"kind": "unknown", "status": resp.status_code, "url": resp.url}

    variants = parse_master(text, resp.url)
    resolution = ""
    bandwidth = 0
    final_url = resp.url
    if variants:
        best = max(variants, key=lambda v: (v["resolution"], v["bandwidth"]))
        resolution, bandwidth = best["resolution"], best["bandwidth"]
        media_resp = request(best["url"], resp.url, timeout)
        if "#EXTM3U" in media_resp.text:
            text = media_resp.text
            final_url = media_resp.url

    media = parse_media(text, final_url)
    tags = media["tags"]
    hosts = media["hosts"]
    total = sum(media["durations"])
    median = statistics.median(media["durations"]) if media["durations"] else 0

    # master 的 RESOLUTION 不可信：实测大量源写的是 1080x608 这种模板占位值
    # （26 条标 1080x608 的线路里 17 条真实分辨率不是它，含 720x1280、1080x1920 竖屏）。
    # 分辨率直接决定码率分档，所以优先用 ffprobe 读真实值；ffprobe 不可用/失败时退回 master。
    width = 0
    height = 0
    fps = 0.0
    probed = probe_media(final_url, referer, min(timeout, 12.0))
    if probed.get("width") and probed.get("height"):
        width = int(probed["width"])
        height = int(probed["height"])
        fps = float(probed.get("fps") or 0)
        resolution = f"{width}x{height}"
    elif resolution and "x" in resolution.lower():
        try:
            raw_width, raw_height = resolution.lower().split("x", 1)
            width, height = int(raw_width), int(raw_height)
        except ValueError:
            width = height = 0
    # 优先用分片实测：很多源的 BANDWIDTH 是 128 / 800000 这种占位值，
    # 实测同一线路的声明值和分片估算能差 2 倍以上。BYTERANGE 列表没法这样估，跳过。
    bitrate = 0
    bitrate_source = ""
    if not any(tag.startswith("#EXT-X-BYTERANGE") for tag in tags):
        bitrate = estimate_bitrate(media["entries"], final_url, timeout)
        if bitrate:
            bitrate_source = "segments"
    if not bitrate and bandwidth:
        bitrate = round(bandwidth / 1000)
        bitrate_source = "master"

    # 广告分片：占比很小但确实存在的第二个域名
    segments = media["segments"] or 1
    minority_hosts = {
        host: count
        for host, count in hosts.items()
        if count / segments <= 0.2 and host
    }
    ad_keyword_segments = 0
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and AD_KEYWORD.search(urllib.parse.urlparse(line).path or ""):
            ad_keyword_segments += 1

    cue = sum(1 for tag in tags if tag.startswith("#EXT-X-CUE-OUT"))
    daterange = sum(1 for tag in tags if tag.startswith("#EXT-X-DATERANGE"))
    scte = sum(1 for tag in tags if "SCTE35" in tag.upper())
    discontinuity = sum(1 for tag in tags if tag.startswith("#EXT-X-DISCONTINUITY"))

    ad_score = 0
    reasons: list[str] = []
    if cue or daterange or scte:
        ad_score += 3
        reasons.append(f"广告标记 CUE/DATERANGE/SCTE35={cue}/{daterange}/{scte}")
    if minority_hosts:
        ad_score += 2
        reasons.append("分片来自多个域名: " + ", ".join(list(minority_hosts)[:3]))
    if ad_keyword_segments and (minority_hosts or cue or daterange):
        ad_score += 1
        reasons.append(f"分片路径含广告关键词 {ad_keyword_segments} 个")

    return {
        "kind": "hls",
        "status": resp.status_code,
        "url": url,
        "final_url": final_url,
        "resolution": resolution,
        "width": width,
        "height": height,
        "fps": fps,
        "bandwidth": bandwidth,
        "bitrate_kbps": bitrate,
        "bitrate_source": bitrate_source,
        "variants": len(variants),
        "segments": media["segments"],
        "duration": round(total, 1),
        "median_segment": round(median, 2),
        "discontinuity": discontinuity,
        "discontinuity_ratio": round(discontinuity / segments, 3),
        "segment_hosts": len(hosts),
        "minority_hosts": list(minority_hosts)[:5],
        "cue_out": cue,
        "daterange": daterange,
        "scte35": scte,
        "ad_keyword_segments": ad_keyword_segments,
        "ad_score": ad_score,
        "ad_reasons": reasons,
    }


def analyze_stream(
    url: str,
    site_hosts: list[str] | None = None,
    referer: str | None = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """分析一个播放地址，返回 kind / relation / ad_score / grade。"""
    site_hosts = [h for h in (site_hosts or []) if h]
    result: dict[str, Any] = {
        "kind": "unknown",
        "relation": "unknown",
        "ad_score": 0,
        "ad_reasons": [],
        "grade": "D",
        "host": "",
        "bitrate_kbps": 0,
        "width": 0,
        "height": 0,
        "fps": 0.0,
    }
    if not url:
        result["error"] = "没有播放地址"
        return result

    parsed = urllib.parse.urlparse(url if "://" in url else "http://" + url)
    host = parsed.netloc
    result["host"] = host

    if not host or host.split(":")[0] in ("127.0.0.1", "localhost", "0.0.0.0"):
        result.update(kind="local", error="本地代理地址，无法在外部验证")
        return result

    final_url = ""
    try:
        resp = request(url, referer, timeout, stream=True)
        content_type = (resp.headers.get("Content-Type") or "").lower()
        final_url = resp.url
        body = b""
        if "mpegurl" in content_type or url.lower().split("?")[0].endswith(".m3u8"):
            body = resp.content[:65536]
        elif "text/html" in content_type:
            body = resp.content[:262144]
        elif "video/" in content_type or "octet-stream" in content_type:
            size = resp.headers.get("Content-Length")
            result.update(
                kind="mp4" if "mp4" in content_type else "video",
                size=int(size) if size and size.isdigit() else None,
                final_url=final_url[:300],
            )
            resp.close()
            # mp4 没有分片可估，只能让 ffprobe 读一下 moov 里的码率。
            result.update(probe_media(final_url or url, referer, min(timeout, 8.0)))
            result["relation"] = site_relation(url, site_hosts, final_url)
            result["grade"] = grade_of(result)
            return result
        elif "audio/" in content_type:
            size = resp.headers.get("Content-Length")
            result.update(
                kind="audio",
                size=int(size) if size and size.isdigit() else None,
                final_url=final_url[:300],
            )
            resp.close()
            result["relation"] = site_relation(url, site_hosts, final_url)
            result["grade"] = grade_of(result)
            return result
        resp.close()
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"[:200]
        result["relation"] = site_relation(url, site_hosts, final_url)
        return result

    text = body.decode("utf-8", "replace")

    if "#EXTM3U" in text:
        detail = analyze_hls(final_url, referer, timeout)
        result.update(detail)
        result["relation"] = site_relation(url, site_hosts, final_url)
    elif "<html" in text.lower() or "<!doctype" in text.lower():
        found = find_m3u8(text, final_url)
        result.update(kind="page", page_url=final_url, m3u8_found=len(found))
        if found:
            detail = analyze_hls(found[0], final_url, timeout)
            if detail.get("kind") == "hls":
                result.update(detail)
                result["relation"] = site_relation(url, site_hosts, final_url)
            else:
                result["relation"] = site_relation(url, site_hosts, final_url)
    else:
        result["relation"] = site_relation(url, site_hosts, final_url)

    result["grade"] = grade_of(result)
    return result


M3U8_RE = re.compile(r"""https?:\\?/\\?/[^\s"'<>\\]+?\.m3u8[^\s"'<>\\]*""", re.I)


def find_m3u8(text: str, base: str) -> list[str]:
    text = text.replace("\\/", "/")
    out: list[str] = []
    for hit in M3U8_RE.findall(text):
        url = urllib.parse.urljoin(base, hit)
        if url not in out:
            out.append(url)
    return out


def grade_of(result: dict[str, Any]) -> str:
    kind = result.get("kind")
    if kind in ("unknown", "local"):
        return "D"
    relation = result.get("relation")
    ad_score = int(result.get("ad_score") or 0)
    if relation == "platform":
        return "C"
    if ad_score >= 2:
        return "C"
    if kind == "page":
        # 页面型播放地址：要么需要解析，要么是网页播放器，广告不可控
        return "C"
    if relation == "self":
        return "A"
    return "B"


def describe(result: dict[str, Any]) -> str:
    grade = result.get("grade", "D")
    label = {"A": "自营直连", "B": "第三方直连", "C": "搬运/解析/有广告标记", "D": "无法验证"}[grade]
    parts = [f"{grade} {label}", result.get("kind", "?")]
    if result.get("resolution"):
        parts.append(result["resolution"])
    if result.get("bitrate_kbps"):
        parts.append(f"{result['bitrate_kbps']} kbps")
    if result.get("relation") and result["relation"] != "unknown":
        parts.append({"self": "同主域", "third": "第三方", "platform": "平台CDN"}[result["relation"]])
    if result.get("ad_score"):
        parts.append(f"广告分 {result['ad_score']}")
    if result.get("error"):
        parts.append(result["error"][:40])
    return " | ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分析播放地址的来源与广告风险")
    parser.add_argument("url", nargs="+", help="播放地址，可以多个")
    parser.add_argument("--site-host", action="append", default=[], help="站点域名，用于判断自营")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = parser.parse_args(argv)

    for url in args.url:
        result = analyze_stream(url, args.site_host)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=1))
        else:
            print(f"{url[:90]}\n  -> {describe(result)}")
            for reason in result.get("ad_reasons") or []:
                print(f"     - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
