#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""TVBox / 影視倉 Native PySpider 模組 - 央視頻版 (JCE 25312 修復版)

文件路徑：./py/ysptpb.py
"""

from datetime import datetime, timedelta, timezone
import gzip
import json
import random
import ssl
import struct
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------
# 禁用 Android Python 的 SSL 驗證 (解決 CERTIFICATE_VERIFY_FAILED)
# ---------------------------------------------------------------
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

try:
    _SSL_CTX = ssl._create_unverified_context()
except Exception:
    _SSL_CTX = None

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def __init__(self):
            pass


# ===============================================================
# JCE 協議（cmd 25312，時移/直播取流）
# ===============================================================

class W:
    def __init__(self): self.b = bytearray()
    def head(self, typ, tag):
        if tag < 15: self.b.append(((tag & 0xf) << 4) | (typ & 0xf))
        else: self.b.append(0xf0 | (typ & 0xf)); self.b.append(tag)
    def byte(self, v, tag):
        v = int(v)
        if v == 0: self.head(12, tag)
        else: self.head(0, tag); self.b += struct.pack('>b', v)
    def short(self, v, tag):
        v = int(v)
        if -128 <= v <= 127: self.byte(v, tag)
        else: self.head(1, tag); self.b += struct.pack('>h', v)
    def int(self, v, tag):
        v = int(v)
        if -32768 <= v <= 32767: self.short(v, tag)
        else: self.head(2, tag); self.b += struct.pack('>i', v)
    def long(self, v, tag):
        v = int(v)
        if -2147483648 <= v <= 2147483647: self.int(v, tag)
        else: self.head(3, tag); self.b += struct.pack('>q', v)
    def float(self, v, tag):
        self.head(4, tag); self.b += struct.pack('>f', float(v))
    def double(self, v, tag):
        self.head(5, tag); self.b += struct.pack('>d', float(v))
    def string(self, s, tag):
        if s is None: return
        data = str(s).encode('utf-8')
        if len(data) > 255:
            self.head(7, tag); self.b += struct.pack('>i', len(data)); self.b += data
        else:
            self.head(6, tag); self.b.append(len(data)); self.b += data
    def bytes(self, data, tag):
        data = bytes(data)
        self.head(13, tag); self.head(0, 0); self.int(len(data), 0); self.b += data
    def struct(self, fn, tag):
        self.head(10, tag); fn(self); self.head(11, 0)
    def list(self, items, tag, wf=None):
        self.head(9, tag); self.int(len(items), 0)
    def out(self):
        return bytes(self.b)


class R:
    def __init__(self, data): self.d = memoryview(data); self.p = 0
    def rem(self): return len(self.d) - self.p
    def get(self, n):
        if self.p + n > len(self.d): raise EOFError
        b = self.d[self.p:self.p + n].tobytes(); self.p += n; return b
    def u8(self): return self.get(1)[0]
    def head(self):
        b = self.u8(); typ = b & 0xf; tag = (b & 0xf0) >> 4
        if tag == 15: tag = self.u8()
        return typ, tag
    def value(self, typ):
        if typ == 0: return struct.unpack('>b', self.get(1))[0]
        if typ == 1: return struct.unpack('>h', self.get(2))[0]
        if typ == 2: return struct.unpack('>i', self.get(4))[0]
        if typ == 3: return struct.unpack('>q', self.get(8))[0]
        if typ == 4: return struct.unpack('>f', self.get(4))[0]
        if typ == 5: return struct.unpack('>d', self.get(8))[0]
        if typ == 6: n = self.u8(); return self.get(n).decode('utf-8', 'replace')
        if typ == 7:
            n = struct.unpack('>i', self.get(4))[0]
            return self.get(n).decode('utf-8', 'replace')
        if typ == 8: n = self._int(); return {self._fv(): self._fv() for _ in range(n)}
        if typ == 9: n = self._int(); return [self._fv() for _ in range(n)]
        if typ == 10: return self.struct()
        if typ == 11: return None
        if typ == 12: return 0
        if typ == 13: t, _ = self.head(); n = self._int(); return self.get(n)
        raise ValueError('type %d' % typ)
    def _fv(self): t, _ = self.head(); return self.value(t)
    def _int(self): t, _ = self.head(); return int(self.value(t))
    def struct(self):
        m = {}
        while self.rem() > 0:
            t, tag = self.head()
            if t == 11: break
            m[tag] = self.value(t)
        return m


VER_NAME, VER_CODE = '3.2.7.26212', '302070'
APP_ID, QMF_APP_ID, QMF_PLATFORM, BIZ_ID = '1200013', 10012, 1, 0
CHAN_ID = '10070'
GUID = ''.join(random.choice('0123456789abcdef') for _ in range(32))


def _qua(w):
    w.string(VER_NAME, 0); w.string(VER_CODE, 1)
    w.int(1080, 2); w.int(2400, 3); w.int(3, 4); w.string('12', 5)
    w.int(1, 6); w.int(1, 7); w.int(420, 8); w.string(CHAN_ID, 9)
    for i in range(10, 15): w.string('', i)
    w.struct(lambda ww: (ww.int(0, 0), ww.byte(0, 1), ww.string('', 2)), 15)
    w.string('', 16); w.string('', 17); w.string('', 18)
    w.struct(lambda ww: (ww.int(0, 0), ww.float(0, 1), ww.float(0, 2), ww.double(0, 3)), 19)
    w.string(GUID[:16], 20); w.string('Pixel 6', 21)
    w.int(1, 22)
    for i in range(23, 27): w.int(0, i)
    w.string('', 27); w.string('', 28); w.string(GUID, 29)


def _head(w, cmd, reqid):
    w.int(reqid, 0); w.int(cmd, 1)
    w.struct(lambda ww: _qua(ww), 2)
    w.string(APP_ID, 3); w.string(GUID, 4)
    w.list([], 5); w.struct(lambda ww: None, 6)
    w.list([], 7)
    w.int(0, 8); w.int(0, 9); w.int(0, 10)


def _wrap(cmd, body, reqid):
    w = W()
    w.struct(lambda ww: _head(ww, cmd, reqid), 0)
    w.bytes(body, 1)
    reqcmd = w.out()
    inner = bytearray([38]) + struct.pack('>i', len(reqcmd) + 17) + bytes([1]) + b'\x00' * 10 + reqcmd + bytes([40])
    comp = gzip.compress(bytes(inner))
    out = bytearray([19]) + struct.pack('>i', 0) + struct.pack('>H', 2) + struct.pack('>H', 65281)
    out += struct.pack('>H', cmd) + struct.pack('>H', 0) + struct.pack('>q', reqid)
    out += struct.pack('>i', 531) + struct.pack('>i', QMF_APP_ID) + struct.pack('>q', BIZ_ID)
    g = GUID.encode()[:32]
    out += g + b'\x00' * (32 - len(g))
    out += struct.pack('>b', QMF_PLATFORM) + struct.pack('>i', int(VER_CODE)) + b'\x00' * 6
    out += bytes([0]) + struct.pack('>H', 0) + struct.pack('>H', 0)
    out += struct.pack('>i', len(inner)) + comp + bytes([3])
    struct.pack_into('>i', out, 1, len(out))
    return bytes(out)


def _unwrap(data):
    if data[:1] != b'\x13' or len(data) < 90:
        return None
    flags = struct.unpack('>i', data[21:25])[0]
    payload = data[89:-1]
    if flags & 2:
        payload = gzip.decompress(payload)
    if payload[:1] != b'&' or payload[-1:] != b'(':
        return None
    rc = R(payload[16:-1]).struct()
    return rc.get(1) or b''


def _http_post(url, headers, body, timeout=10):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method='POST')
    kwargs = {}
    if _SSL_CTX is not None:
        kwargs['context'] = _SSL_CTX
    try:
        with urllib.request.urlopen(req, timeout=timeout, **kwargs) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b''
    except Exception:
        return 599, b''


def jce_stream_url(pid, sid, start, end, stream='fhd'):
    """向 jacc.ysp.cctv.cn 請求 m3u8 直播/時移地址。"""
    w = W()
    w.string(pid, 0); w.string(sid, 1)
    w.long(start, 2); w.long(end, 3)
    w.string(stream, 4)
    body = w.out()

    CMD = 25312
    reqid = int(time.time() * 1000) & 0x7fffffff
    packet = _wrap(CMD, body, reqid)

    st, raw = _http_post(
        'https://jacc.ysp.cctv.cn',
        {'Content-Type': 'application/octet-stream'},
        packet, 10
    )
    if st < 200 or st >= 300:
        raise RuntimeError('JCE HTTP %d' % st)

    resp_body = _unwrap(raw)
    if not resp_body:
        raise RuntimeError('JCE bad response')

    m = R(resp_body).struct()
    err = m.get(0, 0)
    if err != 0:
        raise RuntimeError('JCE errCode=%s' % err)
    url = m.get(2, '')
    if not url:
        raise RuntimeError('JCE empty url')
    return url


# ===============================================================
# 頻道表 (slug -> name / title / sid / pid)
# 名稱、pid、sid 均取自可用的央視頻 JCE 接口
# ===============================================================

_CCTV_TABLE = [
    # slug,       name,       title,                   sid,          pid
    ("cctv1",     "CCTV1",    "CCTV-1 綜合",           "2024078201", "600001859"),
    ("cctv2",     "CCTV2",    "CCTV-2 財經",           "2024075401", "600001800"),
    ("cctv3",     "CCTV3",    "CCTV-3 綜藝",           "2024068501", "600001801"),
    ("cctv4",     "CCTV4",    "CCTV-4 中文國際",       "2029797101", "600001814"),
    ("cctv5",     "CCTV5",    "CCTV-5 體育",           "2024078401", "600001818"),
    ("cctv5plus", "CCTV5+",   "CCTV-5+ 體育賽事",      "2024078001", "600001817"),
    ("cctv6",     "CCTV6",    "CCTV-6 電影",           "2013693901", "600108442"),
    ("cctv7",     "CCTV7",    "CCTV-7 國防軍事",       "2024072001", "600004092"),
    ("cctv8",     "CCTV8",    "CCTV-8 電視劇",         "2029793001", "600001803"),
    ("cctv9",     "CCTV9",    "CCTV-9 紀錄",           "2024078601", "600004078"),
    ("cctv10",    "CCTV10",   "CCTV-10 科教",          "2024078701", "600001805"),
    ("cctv11",    "CCTV11",   "CCTV-11 戲曲",          "2027248701", "600001806"),
    ("cctv12",    "CCTV12",   "CCTV-12 社會與法",      "2027248801", "600001807"),
    ("cctv13",    "CCTV13",   "CCTV-13 新聞",          "2029797201", "600001811"),
    ("cctv14",    "CCTV14",   "CCTV-14 少兒",          "2027248901", "600001809"),
    ("cctv15",    "CCTV15",   "CCTV-15 音樂",          "2027249001", "600001815"),
    ("cctv16",    "CCTV16",   "CCTV-16 奧林匹克",      "2027249101", "600098637"),
    ("cctv17",    "CCTV17",   "CCTV-17 農業農村",      "2027249401", "600001810"),
    ("cctv4k",    "CCTV4K",   "CCTV-4K 超高清",        "2029810301", "600002264"),
    ("cctv8k",    "CCTV8K",   "CCTV-8K 超高清",        "2026774101", "600156816"),
]

CHANNELS = {}
for slug, name, title, sid, pid in _CCTV_TABLE:
    CHANNELS[slug] = {
        "name": name,
        "title": title,
        "pic": "https://live.cctv.com/favicon.ico",
        "sid": sid,
        "pid": pid,
        "defn": "fhd",
    }


def _shift_timestamps(date_str):
    """把 YYYYMMDD 轉為當天 UTC+8 的 [start, end) unix 秒。"""
    y = int(date_str[:4]); m = int(date_str[4:6]); d = int(date_str[6:8])
    tz = timezone(timedelta(hours=8))
    start = datetime(y, m, d, 0, 0, 0, tzinfo=tz)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


class Spider(Spider):

    def getName(self):
        return "央視頻tp"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False

    # -----------------------------------------------------------
    # 首頁 / 分類
    # -----------------------------------------------------------
    def homeContent(self, filter):
        return {
            "class": [{"type_id": "1", "type_name": "央視"}],
            "list": [
                {
                    "vod_id": cid,
                    "vod_name": ch["name"],
                    "vod_pic": ch["pic"],
                    "vod_remarks": "直播",
                }
                for cid, ch in CHANNELS.items()
            ],
        }

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        vod_list = []
        if str(tid) == "1":
            vod_list = [
                {
                    "vod_id": cid,
                    "vod_name": ch["name"],
                    "vod_pic": ch["pic"],
                    "vod_remarks": "直播",
                }
                for cid, ch in CHANNELS.items()
            ]
        return {
            "page": 1,
            "pagecount": 1,
            "limit": len(vod_list),
            "total": len(vod_list),
            "list": vod_list,
        }

    # -----------------------------------------------------------
    # 詳情：直播 + 近 7 天回看
    # -----------------------------------------------------------
    def detailContent(self, array):
        if not array:
            return {"list": []}
        tid = array[0]
        if tid not in CHANNELS:
            return {"list": []}

        ch = CHANNELS[tid]
        play_urls = []
        play_urls.append(f"🔴 實時直播${tid}")

        now = datetime.now()
        for i in range(7):
            day_date = now - timedelta(days=i)
            date_str = day_date.strftime("%Y%m%d")
            display_date = day_date.strftime("%m月%d日")
            play_urls.append(
                f"📅 {display_date} 全天回看${tid}__shift__{date_str}"
            )

        vod_detail = {
            "vod_id": tid,
            "vod_name": ch["title"],
            "type_name": "央視",
            "vod_pic": ch["pic"],
            "vod_remarks": "直播",
            "vod_content": f"央視頻原生點播 - {ch['title']}",
            "vod_play_from": "央視頻",
            "vod_play_url": "#".join(play_urls),
        }
        return {"list": [vod_detail]}

    def searchContent(self, key, quick, pg=1):
        vod_list = [
            {
                "vod_id": cid,
                "vod_name": ch["name"],
                "vod_pic": ch["pic"],
                "vod_remarks": "直播",
            }
            for cid, ch in CHANNELS.items()
            if key.lower() in ch["name"].lower()
            or key.lower() in ch["title"].lower()
        ]
        return {"list": vod_list}

    # -----------------------------------------------------------
    # 播放：走 JCE 25312 拿 m3u8 直鏈
    # -----------------------------------------------------------
    def playerContent(self, flag, id, vipFlags):
        cid = id.split("__shift__")[0]
        shift_date = id.split("__shift__")[1] if "__shift__" in id else ""

        ch = CHANNELS.get(cid)
        if not ch:
            return {"parse": 0, "url": "", "header": {}}

        # 直播默認拉最近 5 分鐘的時移窗口；回看用整天的時間戳
        try:
            if shift_date:
                start, end = _shift_timestamps(shift_date)
            else:
                now = int(time.time())
                start, end = now - 300, now

            real_url = jce_stream_url(
                ch["pid"], ch["sid"], start, end, ch.get("defn", "fhd")
            )
        except Exception:
            real_url = ""

        return {
            "parse": 0,
            "url": real_url,
            "header": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                    " AppleWebKit/537.36 (KHTML, like Gecko)"
                    " Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://tv.cctv.com/",
            },
        }

    def localProxy(self, param):
        pass


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
