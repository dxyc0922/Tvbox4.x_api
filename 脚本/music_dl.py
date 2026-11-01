# -*- coding: utf-8 -*-
"""
music-dl · 壳端 py 源（TVBox / 海阔视界 通用）
=================================================================
对接本机（或局域网里某台设备）跑着的 music-dl 服务，默认端口 :37777，前缀 /music。

【服务地址已内置】文件下面 SERVER_URL 就是，进源即用，不用手填。
  同机（壳和服务在一台设备）：保持 127.0.0.1 就行
  分机（壳在手机、服务在电脑/盒子）：把 SERVER_URL 改成 http://192.168.x.x:37777

【这个源能干什么】
  搜索        —— 关键词搜歌，多平台聚合（壳的搜索框直接用）
  每日推荐歌单 —— 各平台推荐歌单，点进去整张听
  排行榜      —— 各平台榜单（热歌/飙升/新歌…），点进去整张听
  我的歌单    —— 已登录平台的个人歌单
  本地歌单    —— 服务里自建/导入的歌单
  本地音乐    —— 服务下载目录里的文件
  各平台歌单  —— 网易云/QQ/酷狗/酷我/咪咕/千千/汽水/Apple/JOOX，按分类翻歌单
  服务自检    —— 一条链排查「服务连不上 / 列表空白」

【上一曲 / 下一曲】
  从歌单或榜单里点任意一首 → 整张按顺序铺成播放列表，壳里能直接切上/下一曲。
  从搜索列表里点某一首 → 详情页把「这首歌所在的那一页」按当前这首开头环绕铺开，
  点哪首先播哪首，往后一直能切。

依赖：纯标准库，无第三方包。
"""

import base64
import html as _html
import json
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
import urllib.request

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    _BaseSpider = object


# ==================================================================
# 配置区
# ==================================================================

# 内置服务地址：只写 协议://IP:端口，不要带 /music
SERVER_URL = "http://127.0.0.1:37777"

# 服务前缀（music-dl 默认就是 /music，别改）
BASE_PATH = "/music"

# 封面走本地服务代理：个别平台封面有防盗链、壳里加载不出来时改成 True
USE_COVER_PROXY = False

# 内置音乐播放页：点歌时调起「大封面 + 滚动歌词」的播放界面
#   True  = 点播放 → 先弹本源自带的播放页
#   False = 直接把音频流交给壳（配套的 APK 里已经内置了统一的播放页，
#           点歌会自动弹那个页，所以这里关掉，只留一套界面，免得两边打架）
MUSIC_UI = False

# 播放页本地服务起始端口（被占用会自动往后找，最多试 12 个）
UI_PORT = 37779

# 每页条数
PAGE_SIZE = 30

# 播放前先探一下能不能拿到流：
#   点下去没反应、想让它直接告诉你「这首歌这个源没免费音源」就改成 True。
#   默认 False（每播一首都多一次请求，遇到平台限流反而更容易被挡）。
PROBE_PLAY = False

# 大歌单最多续抓几页 / 最多给多少首（TVBox 播放列表太大会卡）
MAX_PAGES = 3
MAX_EPISODES = 400

# 片源中文名（没列到的直接显示原始标识）
SOURCE_NAME = {
    "netease": "网易云",
    "qq": "QQ音乐",
    "kugou": "酷狗",
    "kuwo": "酷我",
    "migu": "咪咕",
    "fivesing": "5sing",
    "jamendo": "Jamendo",
    "joox": "JOOX",
    "qianqian": "千千",
    "soda": "汽水",
    "bilibili": "B站",
    "apple": "Apple",
    "local": "本地",
}

# 「我的歌单」支持的源
USER_PL_SOURCES = ["netease", "qq", "kugou", "kuwo", "soda", "migu"]

# 一级分类里按源列歌单的顺序
PL_CATEGORY_SOURCES = ["netease", "qq", "kugou", "kuwo", "migu", "qianqian", "joox", "soda", "apple"]

# 自动探测候选（内置地址不通时往下试，分机部署请直接改 SERVER_URL）
FALLBACK_ORIGINS = [
    "http://127.0.0.1:37777",
    "http://localhost:37777",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8090",
]

UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

PROBE_TIMEOUT = 3
REQ_TIMEOUT = 25

DIAG_TID = "diag"
VID_PREFIX = "mdl:"


# ==================================================================
# 基础工具
# ==================================================================

_TAG_RE = re.compile(r"<[^>]+>")


def _text(raw):
    if not raw:
        return ""
    return _html.unescape(_TAG_RE.sub("", raw)).replace("\xa0", " ").strip()


def _squash(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _http_get(url, timeout=None, referer=None):
    """成功返回响应正文(str)，失败返回 ""。"""
    if not url:
        return ""
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    try:
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=timeout or REQ_TIMEOUT)
        raw = resp.read()
        return raw.decode("utf-8", "ignore")
    except Exception:
        return ""


def _http_json(url, timeout=None):
    txt = _http_get(url, timeout=timeout)
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


def _b64e(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return VID_PREFIX + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text):
    if not isinstance(text, str) or not text.startswith(VID_PREFIX):
        return None
    body = text[len(VID_PREFIX):]
    body += "=" * (-len(body) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(body.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


def _clean_label(s):
    return (s or "").replace("$", " ").replace("#", " ").replace("\n", " ").strip() or "音乐"


def _js_unescape(s):
    """页面里 navigateTo('...') 的参数是 JS 字符串字面量，\\/ 和 \\u0026 要还原。"""
    if not s:
        return ""
    s = s.replace("\\/", "/")
    try:
        got = json.loads('"' + s.replace('"', '\\"') + '"')
        if isinstance(got, str):
            return got
    except Exception:
        pass
    out = s.replace("\\u0026", "&").replace("\\u003d", "=").replace("\\u0027", "'")
    out = out.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\\\", "\\")
    return out


# 只留这些参数，剩下的（封面/描述/外链/曲目数）不进 vod_id，免得 id 过长
_KEEP_PARAMS = ("id", "source", "toplist_id", "toplist_name", "update_frequency", "category_id",
                "category_name", "collection_id", "name", "q", "type", "page", "page_size")


def _slim_url(url):
    try:
        parts = urllib.parse.urlsplit(url)
        pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        kept = [(k, v) for k, v in pairs if k in _KEEP_PARAMS]
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(kept), ""))
    except Exception:
        return url


def _norm_url(raw):
    """页面里抠出来的链接：先还原转义，再规整查询串。"""
    if not raw:
        return ""
    return _slim_url(_js_unescape(_html.unescape(raw)))


def _with_page(url, page_no):
    try:
        parts = urllib.parse.urlsplit(url)
        pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
        if page_no and page_no > 1:
            pairs.append(("page", str(page_no)))
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(pairs), ""))
    except Exception:
        return url


def _page_error(page):
    """页面里那行「获取歌单失败: xxx」。"""
    if not page:
        return ""
    m = re.search(r'class="error-msg"[^>]*>(.*?)</div>', page, re.S)
    if m:
        txt = _squash(_text(m.group(1)))
        if txt:
            return txt
    return ""


def _panel_errors(page, marker):
    """某几个源的分栏报错，例如网易云被风控。"""
    out = []
    for panel_id, chunk in _panels(page, marker):
        head = chunk[:1200]
        m = re.search(r'class="category-source-empty error"[^>]*>(.*?)</div>', head, re.S)
        if m:
            src = panel_id.split("-")[-1] if panel_id else ""
            out.append((src, _squash(_text(m.group(1)))))
    return out


def _panel_empty(page, marker):
    """分栏存在但是空的（没登录 / 没内容）。"""
    out = []
    for panel_id, chunk in _panels(page, marker):
        if 'class="category-source-empty"' in chunk[:1200]:
            src = panel_id.split("-")[-1] if panel_id else ""
            out.append(src)
    return out


# ==================================================================
# HTML 解析
# ==================================================================

_CACHE = {}
CACHE_TTL = 300


_ATTR_CACHE = {}


def _attr(chunk, name):
    m = re.search(r'\b' + name + r'="([^"]*)"', chunk)
    if m:
        return _html.unescape(m.group(1))
    m = re.search(r"\b" + name + r"='([^']*)'", chunk)
    return _html.unescape(m.group(1)) if m else ""


def _panels(page, marker):
    """按面板切页，返回 [(panel_id, chunk), ...]"""
    out = []
    for chunk in re.split(r'<div class="' + marker, page)[1:]:
        m = re.search(r'id="([^"]+)"', chunk[:400])
        out.append((m.group(1) if m else "", chunk))
    return out


def _parse_songs(page):
    """解析 song-card 列表。"""
    songs = []
    if not page:
        return songs
    for chunk in re.split(r'<li class="song-card"', page)[1:]:
        chunk = chunk.split("</li>")[0]
        sid = _attr(chunk, "data-id")
        src = _attr(chunk, "data-source")
        if not sid:
            continue
        extra = {}
        m = re.search(r"data-extra='([^']*)'", chunk)
        if m:
            try:
                got = json.loads(_html.unescape(m.group(1)))
                if isinstance(got, dict):
                    extra = got
            except Exception:
                extra = {}
        cover = _attr(chunk, "data-cover")
        if not cover:
            m = re.search(r'cover-wrapper.*?<img src="([^"]+)"', chunk, re.S)
            cover = _html.unescape(m.group(1)) if m else ""
        songs.append({
            "id": sid,
            "source": src,
            "name": _attr(chunk, "data-name") or "音乐",
            "artist": _attr(chunk, "data-artist"),
            "album": _attr(chunk, "data-album"),
            "cover": cover,
            "duration": _attr(chunk, "data-duration"),
            "extra": extra,
        })
    return songs


def _parse_playlists(page, panel_source=""):
    """解析 playlist-card 列表。"""
    items = []
    if not page:
        return items
    for chunk in re.split(r'<div class="playlist-card"', page)[1:]:
        url = ""
        m = re.search(r"navigateTo\('([^']+)'\)", chunk)
        if m:
            url = _norm_url(m.group(1))
        name = ""
        m = re.search(r'<div class="playlist-title"[^>]*>(.*?)</div>', chunk, re.S)
        if m:
            name = _text(m.group(1))
        if not name and not url:
            continue
        cover = ""
        m = re.search(r'class="playlist-cover"[^>]*>\s*<img src="([^"]+)"', chunk, re.S)
        if m:
            cover = _html.unescape(m.group(1))
        creator = ""
        m = re.search(r'<div class="playlist-author">(.*?)</div>', chunk, re.S)
        if m:
            creator = _text(m.group(1))
        count = ""
        m = re.search(r'class="playlist-count">(.*?)</div>', chunk, re.S)
        if m:
            count = _text(m.group(1))
        src = panel_source or _attr(chunk, "data-source")
        if not src and url:
            try:
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                src = (q.get("source") or [""])[0]
            except Exception:
                src = ""
        if not src:
            m = re.search(r'class="tag tag-src"[^>]*>([^<]+)<', chunk)
            if m:
                src = _squash(m.group(1))
        items.append({
            "url": url,
            "name": name or "歌单",
            "cover": cover,
            "creator": creator,
            "count": count,
            "source": src,
        })
    return items


def _parse_toplists(page, panel_source=""):
    """解析 toplist-card 列表。"""
    items = []
    if not page:
        return items
    for chunk in re.split(r'<a class="toplist-card"', page)[1:]:
        url = ""
        # 整块里第一个 href 就是卡片自己的（href 值可能上千字符，不能用截断窗口找）
        m = re.search(r'href="([^"]*)"', chunk)
        if m:
            url = _norm_url(m.group(1))
        elif "navigateTo('" in chunk:
            m = re.search(r"navigateTo\('([^']+)'\)", chunk)
            if m:
                url = _norm_url(m.group(1))
        name = ""
        m = re.search(r'<div class="toplist-title">(.*?)</div>', chunk, re.S)
        if m:
            name = _text(m.group(1))
        sub = ""
        m = re.search(r'<div class="toplist-sub">(.*?)</div>', chunk, re.S)
        if m:
            sub = _squash(_text(m.group(1)))
        cover = ""
        m = re.search(r'class="toplist-cover"[^>]*>\s*<img src="([^"]+)"', chunk, re.S)
        if m:
            cover = _html.unescape(m.group(1))
        if not url:
            continue
        items.append({
            "url": url,
            "name": name or "榜单",
            "cover": cover,
            "sub": sub,
            "source": panel_source,
        })
    return items


def _parse_category_chips(page):
    """解析歌单分类页：返回 {source: [(category_id, category_name, url), ...]}"""
    result = {}
    for panel_id, chunk in _panels(page, "category-source-panel"):
        src = panel_id.split("category-panel-")[-1] if "category-panel-" in panel_id else ""
        if not src:
            continue
        chips = []
        for cm in re.finditer(r'<a class="category-chip[^"]*"\s+href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S):
            url = _norm_url(cm.group(1))
            label = _text(cm.group(2))
            cid = ""
            try:
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                cid = (q.get("category_id") or [""])[0]
            except Exception:
                cid = ""
            chips.append((cid, label or "全部", url))
        if chips:
            result[src] = chips
    return result


def _pageinfo(page):
    """从 HTML 里抠 (page, total_pages, total_count)。"""
    pg, total_pages, total_count = 1, 0, 0
    m = re.search(r"当前第\s*(\d+)\s*/\s*(\d+)\s*页", page or "")
    if m:
        pg = int(m.group(1))
        total_pages = int(m.group(2))
    m = re.search(r'class="count">(\d+)</span>', page or "")
    if m:
        total_count = int(m.group(1))
    elif m:
        pass
    if not total_count:
        m = re.search(r"共\s*(\d+)\s*首", page or "")
        if m:
            total_count = int(m.group(1))
        else:
            m = re.search(r"共\s*(\d+)\s*个", page or "")
            if m:
                total_count = int(m.group(1))
    return pg, total_pages, total_count


# ==================================================================
# Spider
# ==================================================================

class Spider(_BaseSpider):

    def __init__(self):
        self.origin = ""
        self.prefix = BASE_PATH
        self.base = ""
        self._cat_cache = None
        self._cat_cache_at = 0
        self._diag = []

    # ---------------- 生命周期 ----------------

    def init(self, extend=""):
        self.base = ""
        self.origin = ""
        cfg = self._parse_extend(extend)
        ext_url = (cfg.get("url") or cfg.get("server") or cfg.get("host") or "").strip() if cfg else ""
        first = ext_url or cfg.get("_raw", "") if cfg else ""
        if not first:
            first = SERVER_URL
        self._resolve(first)
        return self

    def setExtendInfo(self, extend):
        try:
            cfg = self._parse_extend(extend)
            ext_url = (cfg.get("url") or cfg.get("server") or "") if cfg else ""
            if ext_url:
                self._resolve(ext_url)
        except Exception:
            pass

    def _parse_extend(self, extend):
        if isinstance(extend, dict):
            return extend
        if not isinstance(extend, str):
            return {}
        s = extend.strip()
        if not s:
            return {}
        if s.startswith("{"):
            try:
                got = json.loads(s)
                if isinstance(got, dict):
                    return got
            except Exception:
                return {}
        return {"_raw": s}

    def _resolve(self, first):
        origins = []
        for o in [first, SERVER_URL] + FALLBACK_ORIGINS:
            o = (o or "").strip().rstrip("/")
            if not o:
                continue
            if not o.startswith("http"):
                o = "http://" + o
            if o not in origins:
                origins.append(o)
        prefixes = [BASE_PATH, ""] if BASE_PATH else [""]
        for origin in origins:
            for prefix in prefixes:
                try:
                    txt = _http_get(origin + prefix + "/healthz", timeout=PROBE_TIMEOUT)
                except Exception:
                    txt = ""
                if txt and "go-music-dl" in txt:
                    self.origin = origin
                    self.prefix = prefix
                    self.base = origin + prefix
                    return True
        # 一个都没通：把内置地址先记下，后面每次用的时候会自己再试
        self.origin = origins[0] if origins else SERVER_URL
        self.prefix = BASE_PATH
        self.base = self.origin + self.prefix
        return False

    def getName(self):
        return "music-dl 音乐"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ---------------- 内部请求 ----------------

    def _url(self, path, params=None):
        base = self.base or (SERVER_URL + BASE_PATH)
        url = base + path
        if params:
            clean = {}
            for k, v in params.items():
                if v is None:
                    continue
                s = v if isinstance(v, str) else str(v)
                if s == "":
                    continue
                clean[k] = s
            if clean:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
        return url

    def _page(self, path, params=None, timeout=None):
        """取一个 HTML 页面；连不上/要登录时记一笔并返回 ""。"""
        url = self._url(path, params)
        body = _http_get(url, timeout=timeout)
        if not body:
            if not self.base:
                self._resolve(SERVER_URL)
            self._note("拉取失败：" + path)
            return "", url
        if 'id="login-card"' in body or 'id="auth-form"' in body:
            self._note("服务需要登录：请先在 music-dl 里关掉登录或完成登录")
            return "", url
        return body, url

    def _note(self, msg):
        if msg not in self._diag:
            self._diag.append(msg)

    def _cover(self, url, source=""):
        if not url:
            return ""
        if USE_COVER_PROXY and url.startswith("http") and "/cover_proxy" not in url:
            return self._url("/cover_proxy", {"url": url, "source": source})
        return url

    def _srcname(self, source):
        return SOURCE_NAME.get(source, source or "")

    def _friendly_err(self, source, msg):
        """把服务端抛的接口报错翻成人话，并说清下一步怎么办。"""
        raw = (msg or "").strip()
        low = raw.lower()
        name = self._srcname(source) or "这个源"
        if "require cookie" in low or "require userid cookie" in low or "need login" in low or "未登录" in raw:
            return (name + "：服务端还没登录这个平台。\n"
                    "想让这个平台的歌单/我的歌单出来，先在服务设置里登录它；\n"
                    "不想登录就用别的平台的歌单，搜索不受影响。")
        if "-462" in raw or "api error code" in low:
            return (name + "：接口这次没让服务端取数据（服务端原话：" + raw + "）。\n"
                    "常见原因是这一台机器的网络被这个平台挡了，或者该平台要登录；\n"
                    "换个平台的歌单、或隔一会儿再点，其他源照常能用。")
        if "index.js uri not found" in low:
            return (name + "：服务端缺这个平台的解析文件，取不到歌单。\n"
                    "换别的平台的歌单，或让服务端补上这个平台的解析文件。")
        if "403" in raw or "forbidden" in low:
            return (name + "：平台回了 403，当前这条网络被挡了。\n"
                    "换个网络（比如手机流量）或别的平台再试。")
        if "timeout" in low or "timed out" in low or "no such host" in low or "connection" in low:
            return (name + "：网络没通（" + raw + "）。\n"
                    "先确认这台设备能打开那个平台，再点一次试试。")
        return name + "：" + raw

    # ---------------- 分类 / 筛选项 ----------------

    def _playlist_categories(self):
        """抓一次歌单分类页，拆成 {source: [(cid, name, url), ...]}，缓存 10 分钟。"""
        now = time.time()
        if self._cat_cache is not None and now - self._cat_cache_at < 600:
            return self._cat_cache
        page, _ = self._page("/playlist_categories", timeout=30)
        cats = _parse_category_chips(page) if page else {}
        if cats:
            self._cat_cache = cats
            self._cat_cache_at = now
            return cats
        return self._cat_cache or {}

    def _source_filter(self):
        values = [{"n": "全部源", "v": ""}]
        for s in PL_CATEGORY_SOURCES:
            values.append({"n": self._srcname(s), "v": s})
        for s in USER_PL_SOURCES:
            if s not in PL_CATEGORY_SOURCES:
                values.append({"n": self._srcname(s), "v": s})
        return [{"key": "source", "name": "音乐源", "value": values}]

    def _tabs_of(self, page, marker):
        """把 tab 页拆成 [(source, chunk), ...]"""
        out = []
        for panel_id, chunk in _panels(page, marker):
            src = panel_id.split("-")[-1] if panel_id else ""
            out.append((src, chunk))
        return out

    # ---------------- 首页 ----------------

    def homeContent(self, filter=False):
        classes = [
            {"type_id": "hot", "type_name": "🔥 每日推荐歌单"},
            {"type_id": "rank", "type_name": "🏆 排行榜"},
            {"type_id": "mine", "type_name": "❤️ 我的歌单"},
            {"type_id": "col", "type_name": "🗂 本地歌单"},
            {"type_id": "local", "type_name": "📱 本地音乐"},
        ]
        filters = {
            "hot": self._source_filter(),
            "rank": self._source_filter(),
            "mine": self._source_filter(),
        }

        cats = self._playlist_categories()
        for src in PL_CATEGORY_SOURCES:
            chips = cats.get(src) or []
            classes.append({"type_id": "pl:" + src, "type_name": self._srcname(src) + "歌单"})
            if chips:
                opts = [{"n": "全部", "v": ""}]
                for cid, name, _u in chips:
                    opts.append({"n": name, "v": cid})
                # 只留一个筛选条，太长就截断，别把壳拉爆
                filters["pl:" + src] = [{"key": "cat", "name": "分类", "value": opts[:60]}]

        classes.append({"type_id": DIAG_TID, "type_name": "🩺 服务自检"})
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        page, _ = self._page("/recommend", timeout=30)
        vods = []
        if page:
            for src, chunk in self._tabs_of(page, "category-source-panel"):
                for it in _parse_playlists(chunk, src)[:10]:
                    vods.append(self._playlist_vod(it, src))
                if len(vods) >= PAGE_SIZE:
                    break
        if not vods:
            vods = [self._diag_vod()]
        return {"list": vods[:PAGE_SIZE]}

    # ---------------- 分类内容 ----------------

    def categoryContent(self, tid, pg="1", filter=False, extend=None):
        tid = str(tid)
        try:
            page_no = int(pg)
        except Exception:
            page_no = 1
        if page_no < 1:
            page_no = 1
        ext = extend if isinstance(extend, dict) else {}
        source = (ext.get("source") or "").strip()

        if tid == "hot":
            return self._category_playlists("/recommend", source, page_no, single_page=True)
        if tid == "rank":
            return self._category_toplists(source, page_no)
        if tid == "mine":
            return self._category_playlists("/user_playlists", source, page_no, single_page=True)
        if tid == "col":
            return self._category_playlists("/my_collections", "", page_no, single_page=True)
        if tid == "local":
            return self._category_local(page_no)
        if tid == DIAG_TID:
            return {"list": [self._diag_vod()], "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        if tid.startswith("pl:"):
            return self._category_source_playlists(tid[3:], (ext.get("cat") or "").strip(), page_no)

        return {"list": [], "page": page_no, "pagecount": 1, "limit": PAGE_SIZE, "total": 0}

    def _note_vod(self, title, text, sub="点开看说明"):
        """列表级说明卡：点进去能看到为什么空。"""
        return {
            "vod_id": _b64e({"t": "none", "n": title, "msg": text}),
            "vod_name": title,
            "vod_pic": "",
            "vod_remarks": sub,
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": text,
            "vod_play_from": "music-dl",
            "vod_play_url": "说明$" + _b64e({"t": "none"}),
        }

    def _empty(self, page_no):
        return {"list": [], "page": page_no, "pagecount": page_no, "limit": PAGE_SIZE, "total": page_no - 1}

    def _empty_note(self, page_no, page, path):
        """空列表时给一张能点开的说明卡，不让用户面对白屏。"""
        errs = _panel_errors(page, "category-source-panel")
        if errs:
            parts = []
            for src, msg in errs[:4]:
                parts.append(self._friendly_err(src, msg))
            text = ("这几个源这次没返回内容：\n\n" + "\n\n".join(parts) +
                    "\n\n「我的歌单」这类要登录的平台歌曲，要在服务端登录过才有；"
                    "没登录的话可以用歌单卡片右下角的「导入本地」把歌单存成本地清单。")
            return {"list": [self._note_vod("这个栏目暂无可显示内容", text)],
                    "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        if path.endswith("user_playlists"):
            return {"list": [self._note_vod(
                "我的歌单是空的",
                "服务端没登录任何平台账号时这里就是空的。\n"
                "想看某个平台自己的歌单，先在服务端把那个平台登录好；\n"
                "想收藏歌单，可以在任意歌单卡片上点「导入本地」。")],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        if path.endswith("my_collections"):
            return {"list": [self._note_vod(
                "本地导入的歌单还是空的",
                "还没导入过歌单。\n在歌单卡片上点右下角「导入本地」，就会出现在这里（只存歌单信息，不下载歌曲）。")],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        return self._empty(page_no)

    def _category_playlists(self, path, source, page_no, single_page=True):
        params = {}
        if source:
            params["sources"] = source
        page, url = self._page(path, params, timeout=40)
        if not page:
            return {"list": [self._diag_vod()], "page": 1, "pagecount": 1, "limit": 1, "total": 1}

        items = []
        _p, _tp, total = _pageinfo(page)
        if url.rstrip("/").endswith(("recommend", "user_playlists", "my_collections")):
            for src, chunk in self._tabs_of(page, "category-source-panel"):
                if src == "" or src == "empty":
                    src = source
                items.extend(_parse_playlists(chunk, src))
        else:
            items = _parse_playlists(page, source)
        if not items:
            items = _parse_playlists(page, source)

        if single_page:
            total = total or len(items)
            start = (page_no - 1) * PAGE_SIZE
            chunk = items[start:start + PAGE_SIZE]
            if not items:
                return self._empty_note(page_no, page, path)
            return {
                "list": [self._playlist_vod(it, it.get("source") or source) for it in chunk],
                "page": page_no,
                "pagecount": max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE),
                "limit": PAGE_SIZE,
                "total": len(items),
            }
        return self._empty(page_no)

    def _category_source_playlists(self, source, category_id, page_no):
        page, url = self._page("/category_playlists", {
            "source": source,
            "category_id": category_id,
            "page": page_no,
            "page_size": PAGE_SIZE,
        }, timeout=40)
        if not page:
            return {"list": [self._diag_vod()], "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        items = _parse_playlists(page, source)
        _p, total_pages, total = _pageinfo(page)
        if not items:
            err = _page_error(page)
            if err:
                return {"list": [self._note_vod(
                    self._srcname(source) + "歌单这次没出来",
                    self._friendly_err(source, err) + "\n\n换个分类、或隔一会儿再点一次试试；其他平台的歌单不受影响。")],
                    "page": 1, "pagecount": 1, "limit": 1, "total": 1}
            return {"list": [self._note_vod(
                self._srcname(source) + "没有这个分类的歌单",
                "服务端没为这个分类返回歌单。\n"
                "回上一层换一个分类（或选「全部」）再试；\n"
                "「每日推荐歌单」和「排行榜」里也有大量可直接播放的歌单。")],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        return {
            "list": [self._playlist_vod(it, source) for it in items],
            "page": page_no,
            "pagecount": total_pages or page_no,
            "limit": PAGE_SIZE,
            "total": total or (page_no * PAGE_SIZE),
        }

    def _category_toplists(self, source, page_no):
        params = {}
        if source:
            params["sources"] = source
        page, _u = self._page("/toplists", params, timeout=40)
        if not page:
            return {"list": [self._diag_vod()], "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        items = []
        for src, chunk in self._tabs_of(page, "category-source-panel"):
            if not src or src == "empty":
                src = source
            items.extend(_parse_toplists(chunk, src))
        err = _page_error(page)
        if not items:
            return self._empty_note(page_no, page, "/toplists")
        start = (page_no - 1) * PAGE_SIZE
        chunk = items[start:start + PAGE_SIZE]
        out = [self._toplist_vod(it) for it in chunk]
        # 有的源这次没出来，在最后一页挂张说明卡，不挡正片
        if err and start + PAGE_SIZE >= len(items):
            out.append(self._note_vod("部分来源这次没出来", err + "\n其他来源的榜单照常可用。", sub="说明"))
        return {
            "list": out,
            "page": page_no,
            "pagecount": max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE),
            "limit": PAGE_SIZE,
            "total": len(items),
        }

    def _category_local(self, page_no):
        data = _http_json(self._url("/local_music", {"limit": 0}), timeout=40)
        tracks = []
        if isinstance(data, dict):
            tracks = data.get("tracks") or []
        elif isinstance(data, list):
            tracks = data
        if not data:
            # 老版本 / 没索引时退回页面
            page, _u = self._page("/local_music_page", timeout=40)
            songs = _parse_songs(page) if page else []
            return self._songs_result(songs, "/local_music_page", page_no)
        songs = []
        for t in tracks:
            if not isinstance(t, dict):
                continue
            songs.append({
                "id": t.get("id") or "",
                "source": "local",
                "name": t.get("name") or "音乐",
                "artist": t.get("artist") or "",
                "album": t.get("album") or "",
                "cover": t.get("cover") or "",
                "duration": str(t.get("duration") or ""),
                "extra": t.get("extra") if isinstance(t.get("extra"), dict) else {},
            })
        songs = [s for s in songs if s["id"]]
        if not songs:
            return {"list": [self._note_vod(
                "本地音乐是空的",
                "服务里还没有本地曲库。\n"
                "本地音乐指的是服务自己扫描到的本地文件（比如放在下载目录里的歌），\n"
                "歌单里的歌不在这里——那些直接在歌单/榜单/搜索里点开就能听。")],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1}
        return self._songs_result(songs, "/local_music", page_no, title_hint="本地音乐")

    def _songs_result(self, songs, ctx_path, page_no, title_hint=""):
        total = len(songs)
        start = (page_no - 1) * PAGE_SIZE
        chunk = songs[start:start + PAGE_SIZE]
        if not chunk:
            return self._empty(page_no)
        return {
            "list": [self._song_vod(s, ctx_path, i) for i, s in enumerate(chunk)],
            "page": page_no,
            "pagecount": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            "limit": PAGE_SIZE,
            "total": total,
        }

    # ---------------- 条目构造 ----------------

    def _playlist_vod(self, item, source):
        payload = {"t": "pl", "u": item.get("url") or "", "n": item.get("name") or "歌单",
                   "p": item.get("cover") or "", "s": source or item.get("source") or ""}
        return {
            "vod_id": _b64e(payload),
            "vod_name": item.get("name") or "歌单",
            "vod_pic": self._cover(item.get("cover") or "", payload["s"]),
            "vod_remarks": self._srcname(payload["s"]) + ((" · " + item.get("count")) if item.get("count") else ""),
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": ("歌单：" + (item.get("name") or "") +
                            "\n来源：" + self._srcname(payload["s"]) +
                            (("\n创建者：" + item["creator"]) if item.get("creator") else "") +
                            (("\n曲目：" + item["count"]) if item.get("count") else "") +
                            "\n点开即整张铺成播放列表，可以直接切上/下一曲。"),
        }

    def _toplist_vod(self, item):
        payload = {"t": "pl", "u": item.get("url") or "", "n": item.get("name") or "榜单",
                   "p": item.get("cover") or "", "s": item.get("source") or ""}
        return {
            "vod_id": _b64e(payload),
            "vod_name": item.get("name") or "榜单",
            "vod_pic": self._cover(item.get("cover") or "", payload["s"]),
            "vod_remarks": self._srcname(payload["s"]) + ((" · " + item["sub"]) if item.get("sub") else ""),
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": ("榜单：" + (item.get("name") or "") +
                            "\n来源：" + self._srcname(payload["s"]) +
                            (("\n" + item["sub"]) if item.get("sub") else "") +
                            "\n点开即整张铺成播放列表，可以直接切上/下一曲。"),
        }

    def _song_vod(self, song, ctx_path, idx=0):
        extra = song.get("extra") if isinstance(song.get("extra"), dict) else {}
        payload = {
            "t": "sg",
            "s": song.get("source") or "",
            "i": song.get("id") or "",
            "n": song.get("name") or "音乐",
            "a": song.get("artist") or "",
            "al": song.get("album") or "",
            "cv": song.get("cover") or "",
            "du": song.get("duration") or "",
            "ex": extra,
            "c": {"u": ctx_path, "x": idx},
        }
        remark = song.get("artist") or ""
        dur = str(song.get("duration") or "")
        if dur and dur.isdigit() and int(dur) > 0:
            try:
                sec = int(dur)
                dur_txt = "%d:%02d" % (sec // 60, sec % 60)
            except Exception:
                dur_txt = dur
            remark = (remark + " · " + dur_txt) if remark else dur_txt
        return {
            "vod_id": _b64e(payload),
            "vod_name": song.get("name") or "音乐",
            "vod_pic": self._cover(song.get("cover") or "", song.get("source") or ""),
            "vod_remarks": remark,
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": ("歌手：" + (song.get("artist") or "未知") +
                            "\n专辑：" + (song.get("album") or "") +
                            (("\n时长：" + dur_txt) if dur and dur.isdigit() else "") +
                            "\n来源：" + self._srcname(song.get("source"))),
        }

    # ---------------- 详情 ----------------

    def detailContent(self, array):
        vids = array if isinstance(array, (list, tuple)) else [array]
        vids = [v for v in vids if isinstance(v, str)][:10]
        if not vids:
            vids = [array]
        out = []
        for vid in vids:
            payload = _b64d(vid) if isinstance(vid, str) else None
            if not payload:
                continue
            kind = payload.get("t")
            if kind in ("pl", "tl"):
                got = self._detail_playlist(payload)
            elif kind == "sg":
                got = self._detail_song(payload)
            elif kind == "diag":
                text = "\n".join(self._diag_lines())
                title = payload.get("n") or "🩺 服务自检"
                got = {"list": [{
                    "vod_id": _b64e({"t": "diag", "n": title}),
                    "vod_name": title,
                    "vod_pic": "",
                    "vod_remarks": "明细",
                    "vod_tag": "",
                    "vod_douban_id": 0,
                    "vod_content": text,
                    "vod_play_from": "music-dl",
                    "vod_play_url": "说明$" + _b64e({"t": "none"}),
                }]}
            elif kind == "none":
                name = payload.get("n") or "说明"
                msg = payload.get("msg") or "这次没拉到内容，回头再点一次试试。"
                got = {"list": [{
                    "vod_id": _b64e({"t": "none", "n": name, "msg": msg}),
                    "vod_name": name,
                    "vod_pic": "",
                    "vod_remarks": "说明",
                    "vod_tag": "",
                    "vod_douban_id": 0,
                    "vod_content": msg,
                    "vod_play_from": "music-dl",
                    "vod_play_url": "说明$" + _b64e({"t": "none"}),
                }]}
            else:
                got = {"list": []}
            out.extend(got.get("list") or [])
            if len(out) >= 10:
                break
        return {"list": out}

    def _fetch_songs(self, url):
        """抓歌单/榜单页，大列表自动续抓第 2、3 页。返回 (songs, err)。"""
        if not url:
            return [], ""
        full = url if url.startswith("http") else (self.origin or SERVER_URL) + url
        cached = _CACHE.get(full)
        if cached and time.time() - cached[0] < CACHE_TTL:
            return cached[1], cached[2]
        page = _http_get(full, timeout=45)
        if not page:
            return [], "页面拉取失败（服务没响应）"
        songs = [s for s in _parse_songs(page) if s.get("id")]
        err = _page_error(page)
        if not songs:
            return [], err
        total_pages = _pageinfo(page)[1] or 1
        seen = set((s.get("source"), str(s.get("id"))) for s in songs)
        page_no = 1
        while page_no < min(total_pages, MAX_PAGES) and len(songs) < MAX_EPISODES:
            page_no += 1
            more = _http_get(_with_page(full, page_no), timeout=45)
            if not more:
                break
            added = 0
            for s in _parse_songs(more):
                key = (s.get("source"), str(s.get("id")))
                if not s.get("id") or key in seen:
                    continue
                seen.add(key)
                songs.append(s)
                added += 1
                if len(songs) >= MAX_EPISODES:
                    break
            if added == 0:
                break
        songs = songs[:MAX_EPISODES]
        try:
            if len(_CACHE) > 24:
                _CACHE.clear()
            _CACHE[full] = (time.time(), songs, err)
        except Exception:
            pass
        return songs, err

    def _songs_to_episodes(self, songs, ctx_url, limit=MAX_EPISODES):
        episodes = []
        for s in songs[:limit]:
            label = _clean_label(s.get("name") or "音乐")
            if s.get("artist"):
                label += " - " + _clean_label(s["artist"])
            sub = _b64e({
                "t": "sg",
                "s": s.get("source") or "",
                "i": s.get("id") or "",
                "n": s.get("name") or "音乐",
                "a": s.get("artist") or "",
                "al": s.get("album") or "",
                "cv": s.get("cover") or "",
                "du": s.get("duration") or "",
                "ex": s.get("extra") if isinstance(s.get("extra"), dict) else {},
                "c": {"u": ctx_url, "x": 0},
            })
            episodes.append(label + "$" + sub)
        return episodes

    def _detail_playlist(self, payload):
        url = payload.get("u") or ""
        if not url:
            return {"list": []}
        # 外部导入的歌单，跳转的是站外地址，本地解析不了
        if url.startswith("http") and self.origin and not url.startswith(self.origin):
            return {"list": [self._info_vod(
                payload, "这个歌单是外部导入的，只能在原站打开，本机服务取不到曲目。")]}

        songs, err = self._fetch_songs(url)
        if not songs:
            if err:
                why = self._friendly_err(payload.get("s"), err)
            else:
                why = "这个歌单里没拉到歌（可能是空歌单，或者这个源在当前网络下取不到）。"
            return {"list": [self._info_vod(payload, why)]}

        episodes = self._songs_to_episodes(songs, url)
        name = payload.get("n") or "歌单"
        first = songs[0]
        note = "来源：" + self._srcname(payload.get("s"))
        if err:
            note += "\n注意：" + err
        note += "\n共 %d 首，点任意一集播放，播放器里的「下一集」就是下一曲。" % len(episodes)
        vod = {
            "vod_id": _b64e(payload),
            "vod_name": name,
            "vod_pic": self._cover(payload.get("p") or first.get("cover") or "", payload.get("s") or ""),
            "vod_remarks": "%d 首" % len(episodes),
            "vod_year": "",
            "vod_area": "",
            "vod_actor": first.get("artist") or "",
            "vod_director": "",
            "vod_content": note,
            "vod_play_from": "music-dl",
            "vod_play_url": "#".join(episodes),
        }
        return {"list": [vod]}

    def _detail_song(self, payload):
        ctx = payload.get("c") if isinstance(payload.get("c"), dict) else {}
        ctx_url = ctx.get("u") or ""
        songs = []
        if ctx_url:
            songs, _err = self._fetch_songs(ctx_url)

        cur_id = str(payload.get("i") or "")
        cur_src = str(payload.get("s") or "")
        start = -1
        for i, s in enumerate(songs):
            if str(s.get("id")) == cur_id and str(s.get("source")) == cur_src:
                start = i
                break
        if start < 0:
            songs = []
        elif start > 0:
            songs = songs[start:] + songs[:start]

        if not songs:
            songs = [{
                "id": cur_id,
                "source": cur_src,
                "name": payload.get("n") or "音乐",
                "artist": payload.get("a") or "",
                "album": payload.get("al") or "",
                "cover": payload.get("cv") or "",
                "duration": payload.get("du") or "",
                "extra": payload.get("ex") if isinstance(payload.get("ex"), dict) else {},
            }]

        episodes = []
        for s in songs:
            label = _clean_label(s.get("name") or "音乐")
            if s.get("artist"):
                label += " - " + _clean_label(s["artist"])
            sub = _b64e({
                "t": "sg",
                "s": s.get("source") or cur_src,
                "i": s.get("id") or "",
                "n": s.get("name") or "音乐",
                "a": s.get("artist") or "",
                "al": s.get("album") or "",
                "cv": s.get("cover") or "",
                "du": s.get("duration") or "",
                "ex": s.get("extra") if isinstance(s.get("extra"), dict) else {},
                "c": {"u": ctx_url, "x": 0},
            })
            episodes.append(label + "$" + sub)

        head = songs[0]
        vod = {
            "vod_id": _b64e(payload),
            "vod_name": head.get("name") or payload.get("n") or "音乐",
            "vod_pic": self._cover(head.get("cover") or payload.get("cv") or "", cur_src),
            "vod_remarks": "%d 首" % len(episodes),
            "vod_year": "",
            "vod_area": "",
            "vod_actor": head.get("artist") or "",
            "vod_director": "",
            "vod_content": ("歌手：" + (head.get("artist") or "未知") +
                            "\n专辑：" + (head.get("album") or "") +
                            "\n来源：" + self._srcname(cur_src) +
                            "\n点哪首先播哪首，往后一直能切。"),
            "vod_play_from": "music-dl",
            "vod_play_url": "#".join(episodes[:400]),
        }
        return {"list": [vod]}

    def _info_vod(self, payload, message=""):
        return {
            "vod_id": _b64e(payload),
            "vod_name": payload.get("n") or "说明",
            "vod_pic": self._cover(payload.get("p") or "", payload.get("s") or ""),
            "vod_remarks": "点开看说明",
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": (message or "这次没拉到内容，回头再点一次试试。"),
            "vod_play_from": "music-dl",
            "vod_play_url": "说明$" + _b64e({"t": "none"}),
        }

    # ---------------- 播放 ----------------

    def playerContent(self, flag, id, vipFlags=None):
        if isinstance(id, str) and (id.startswith("http://") or id.startswith("https://")):
            return {"parse": 0, "playUrl": "", "url": id, "header": {"User-Agent": UA}}

        payload = _b64d(id) if isinstance(id, str) else None
        if not payload or payload.get("t") != "sg":
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

        extra = payload.get("ex") if isinstance(payload.get("ex"), dict) else {}
        params = {
            "id": payload.get("i") or "",
            "source": payload.get("s") or "",
            "name": payload.get("n") or "Unknown",
            "artist": payload.get("a") or "Unknown",
            "album": payload.get("al") or "",
            "cover": payload.get("cv") or "",
            "stream": "1",
        }
        if extra:
            params["extra"] = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
        url = self._url("/download", params)

        # ---- 内置音乐播放页：先把 UI 调起来 ----
        if MUSIC_UI:
            try:
                ok, ui_port, _ui_err = _ui_srv(self)
                if ok:
                    ctx = payload.get("c") if isinstance(payload.get("c"), dict) else {}
                    boot = {
                        "api": "",
                        "srcname": SOURCE_NAME,
                        "song": {
                            "uid": "%s:%s" % (payload.get("s") or "", payload.get("i") or ""),
                            "id": payload.get("i") or "",
                            "source": payload.get("s") or "",
                            "name": payload.get("n") or "音乐",
                            "artist": payload.get("a") or "",
                            "album": payload.get("al") or "",
                            "cover": self._cover(payload.get("cv") or "", payload.get("s") or ""),
                            "duration": payload.get("du") or "",
                            "extra": extra,
                        },
                        "list": [],
                        "ctx": {"u": ctx.get("u") or "", "x": ctx.get("x") or 0},
                    }
                    ui_url = "http://127.0.0.1:%d/p?s=%s" % (ui_port, _ui_b64e(boot))
                    return {"parse": 1, "playUrl": "", "url": ui_url, "header": {}}
            except Exception:
                pass

        out = {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": {
                "User-Agent": UA,
                "Referer": (self.base or SERVER_URL) + "/",
            },
        }
        if PROBE_PLAY:
            try:
                import urllib.error as _ue
                req = urllib.request.Request(url, headers={"Range": "bytes=0-1", "User-Agent": UA})
                with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT + 4) as resp:
                    resp.read(2)
            except _ue.HTTPError as e:
                if e.code == 404:
                    out["url"] = ""
                    out["msg"] = (self._srcname(payload.get("s")) + " 这边没有可播的免费音源（服务端取不到流）。\n"
                                  "换列表里另一个源的同名歌曲试试，或先在服务端登录这个平台。")
                else:
                    out["url"] = ""
                    out["msg"] = self._friendly_err(payload.get("s"), "HTTP %s" % e.code)
            except Exception as e:
                out["url"] = ""
                out["msg"] = self._friendly_err(payload.get("s"), str(e))
        return out

    def localProxy(self, param):
        """壳走本地代理时的兜底：把目标流地址原样回一个 302。"""
        try:
            target = ""
            if isinstance(param, dict):
                target = param.get("url") or param.get("u") or ""
            elif isinstance(param, str):
                target = param
            if not target:
                return [404, "text/plain", "no url"]
            return [302, "text/plain", "", {"Location": target}]
        except Exception as e:
            return [500, "text/plain", str(e)]

    # ---------------- 搜索 ----------------

    def searchContent(self, key, quick=False, pg="1"):
        keyword = (key or "").strip()
        if not keyword:
            return {"list": []}
        try:
            page_no = int(pg)
        except Exception:
            page_no = 1
        if page_no < 1:
            page_no = 1

        params = {"q": keyword, "type": "song", "page": page_no, "page_size": PAGE_SIZE}
        page, _u = self._page("/search", params, timeout=40)
        if not page:
            return {"list": [self._diag_vod("搜索没拉到结果，先看这里为什么")]}
        songs = _parse_songs(page)
        proto = urllib.parse.urlsplit(self.base or SERVER_URL)
        ctx_path = urllib.parse.urlunsplit(("", "", proto.path + "/search", urllib.parse.urlencode(params), ""))
        if not songs:
            return {"list": []}
        return {"list": [self._song_vod(s, ctx_path, i) for i, s in enumerate(songs)]}

    # ---------------- 自检 ----------------

    def _diag_vod(self, title="🩺 服务自检"):
        return {
            "vod_id": _b64e({"t": "diag"}),
            "vod_name": title,
            "vod_pic": "",
            "vod_remarks": "点开看明细",
            "vod_tag": "",
            "vod_douban_id": 0,
            "vod_content": "\n".join(self._diag_lines()),
            "vod_play_from": "music-dl",
            "vod_play_url": "说明$" + _b64e({"t": "none"}),
        }

    def _diag_lines(self):
        lines = []
        healthy = False
        if not self.base:
            self._resolve(SERVER_URL)
        try:
            txt = _http_get((self.base or "") + "/healthz", timeout=PROBE_TIMEOUT)
            healthy = bool(txt and "go-music-dl" in txt)
        except Exception:
            healthy = False
        lines.append("服务地址：" + (self.base or "未设置"))
        lines.append("健康检查：" + ("OK ✓" if healthy else "连不上 ✗"))
        if healthy:
            lines.append("首页：" + ("OK ✓" if _http_get(self.base + "/", timeout=REQ_TIMEOUT) else "拉不到 ✗"))
            cats = self._playlist_categories()
            total_cat = sum(len(v) for v in cats.values())
            lines.append("歌单分类：%d 个源 / %d 个分类" % (len(cats), total_cat))
            data = _http_json(self._url("/local_music", {"limit": 1}), timeout=20)
            if isinstance(data, dict):
                lines.append("本地音乐：%s 首" % data.get("total", 0))
            else:
                lines.append("本地音乐：拉不到（跳过）")
        else:
            lines.append("")
            lines.append("连不上的话，按顺序看这几条：")
            lines.append("1. music-dl 是不是正在运行（App / 桌面版开着）")
            lines.append("2. 端口是不是 37777，地址栏是不是 /music")
            lines.append("3. 壳和服务必须在同一台设备上")
            lines.append("   127.0.0.1 只指「本机」，服务装在电脑/盒子上就得改地址")
            lines.append("4. 分机部署：把本文件顶部的 SERVER_URL")
            lines.append("   改成 http://服务那台的局域网IP:37777")
            lines.append("5. 服务开了登录的话，先在设置里关掉或先登录一次")
        if self._diag:
            lines.append("")
            lines.append("最近几次没通的请求：")
            for m in self._diag[-6:]:
                lines.append("· " + m)
        return lines


# ==================================================================
# 本机自测（壳里不跑这段）
# ==================================================================

if __name__ == "__main__":
    sp = Spider()
    sp.init("")
    print("base =", sp.base)
    home = sp.homeContent(True)
    print("分类：", " / ".join([c["type_name"] for c in home["class"]]))
    print("筛选项：", list((home.get("filters") or {}).keys()))
    hot = sp.categoryContent("hot", "1", False, {})
    print("每日推荐：", len(hot.get("list") or []), "个")
    if hot.get("list"):
        print("  首个：", hot["list"][0]["vod_name"])
        d = sp.detailContent([hot["list"][0]["vod_id"]])
        if d.get("list"):
            eps = d["list"][0]["vod_play_url"].split("#")
            print("  详情：", d["list"][0]["vod_name"], len(eps), "首")
            print("  第一集：", eps[0][:60])
            pc = sp.playerContent("", eps[0].split("$")[-1])
            print("  取流：", pc["url"][:120])
    s = sp.searchContent("周杰伦", False, "1")
    print("搜索：", len(s.get("list") or []), "条")
    if s.get("list"):
        print("  首个：", s["list"][0]["vod_name"], "-", s["list"][0]["vod_remarks"])
        d = sp.detailContent([s["list"][0]["vod_id"]])
        if d.get("list"):
            eps = d["list"][0]["vod_play_url"].split("#")
            print("  详情铺开：", len(eps), "首；点哪首先播哪首 ->", eps[0].split("$")[0][:40])
    print("自检：")
    for ln in sp._diag_lines():
        print("  " + ln)



# ==================================================================
# 内置音乐播放页（点歌即调起）
# ==================================================================
# 点播放时不再直接把音频丢给壳的原生播放器，而是先在设备上起一个本地小服务，
# 把「音乐播放页」吐出来交给壳打开：大封面 + 滚动歌词 + 进度拖动 + 上下曲。
# 起不来（极少数环境）会自动退回原来的直连播放，不会把功能弄挂。

PLAYER_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#3d1b45">
<title>正在播放</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden}
body{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue","Noto Sans CJK SC",sans-serif;
  color:#fff;background:#3d1b45;
  user-select:none;-webkit-user-select:none;
}
#bgimg{
  position:fixed;inset:0;z-index:0;
  background-size:cover;background-position:center;
  filter:blur(58px) saturate(1.7) brightness(.85);
  transform:scale(1.35);
  opacity:.85;
  transition:background-image .5s;
}
#bg{
  position:fixed;inset:0;z-index:1;
  background:
    radial-gradient(120% 80% at 85% 0%, rgba(255,120,160,.42) 0%, rgba(255,120,160,0) 55%),
    radial-gradient(100% 70% at 0% 100%, rgba(120,60,220,.40) 0%, rgba(120,60,220,0) 60%),
    linear-gradient(163deg,rgba(64,33,79,.58) 0%,rgba(85,32,79,.54) 42%,rgba(110,31,76,.50) 72%,rgba(125,32,71,.48) 100%);
}
#bg::after{
  content:"";position:absolute;inset:-30%;
  background:repeating-linear-gradient(122deg,rgba(255,255,255,.045) 0 2px,rgba(255,255,255,0) 2px 46px);
  transform:rotate(2deg);
}
#blob{
  position:fixed;z-index:1;right:-70px;top:-90px;width:270px;height:270px;pointer-events:none;
  background:radial-gradient(circle at 42% 58%,rgba(255,140,190,.55),rgba(190,90,220,.28) 45%,rgba(255,255,255,0) 72%);
  filter:blur(6px);border-radius:56% 44% 62% 38%/48% 60% 40% 52%;
}

.app{
  position:relative;z-index:2;height:100%;
  display:flex;flex-direction:column;
  padding:calc(env(safe-area-inset-top,0px) + 8px) 24px calc(env(safe-area-inset-bottom,0px) + 10px);
}

/* ---------- 顶栏 ---------- */
.topbar{display:flex;align-items:center;gap:10px;height:44px;flex:0 0 auto}
.ic{
  width:38px;height:38px;border:0;background:transparent;color:#fff;
  display:flex;align-items:center;justify-content:center;border-radius:50%;
}
.ic:active{background:rgba(255,255,255,.14)}
.ic svg{width:22px;height:22px;fill:none;stroke:#fff;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.topbar .src{
  flex:1;text-align:center;font-size:12px;letter-spacing:.4px;
  color:rgba(255,255,255,.68);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}

/* ---------- 封面 ---------- */
.stage{
  flex:0 0 auto;display:flex;flex-direction:column;align-items:center;
  padding-top:6px;
}
.cover{
  position:relative;width:min(54vw,200px);aspect-ratio:1;border-radius:50%;
  box-shadow:0 18px 46px rgba(0,0,0,.42), 0 0 0 1px rgba(255,255,255,.16) inset;
  overflow:hidden;background:rgba(255,255,255,.10);
}
.cover img{width:100%;height:100%;object-fit:cover;display:block}
.cover .none{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(140deg,rgba(255,255,255,.22),rgba(255,255,255,.06));
}
.cover .none svg{width:42%;height:42%;fill:rgba(255,255,255,.62)}
.cover.spin img{animation:spin 22s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}

.meta{width:100%;text-align:center;margin-top:14px;flex:0 0 auto}
.meta .t{
  font-size:20px;font-weight:600;line-height:1.3;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}
.meta .a{
  margin-top:6px;font-size:13px;color:rgba(255,255,255,.62);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
}

/* ---------- 歌词 ---------- */
.lyric{
  flex:1 1 auto;min-height:60px;margin-top:10px;
  overflow:hidden;position:relative;
  -webkit-mask-image:linear-gradient(180deg,transparent 0,#000 16%,#000 84%,transparent 100%);
  mask-image:linear-gradient(180deg,transparent 0,#000 16%,#000 84%,transparent 100%);
}
.lyric .inner{
  position:absolute;left:0;right:0;top:50%;
  transition:transform .42s cubic-bezier(.22,.61,.36,1);
}
.lyric .ln{
  padding:7px 6px;text-align:center;font-size:15px;line-height:1.45;
  color:rgba(255,255,255,.70);transition:color .25s,transform .25s;
  text-shadow:0 1px 8px rgba(0,0,0,.35);
}
.lyric .ln.cur{color:#ffe14d;font-weight:700;font-size:16.5px;transform:scale(1.03);text-shadow:0 0 14px rgba(255,225,77,.55),0 1px 8px rgba(0,0,0,.4)}
.lyric .empty{text-align:center;color:rgba(255,255,255,.45);font-size:13.5px;line-height:1.9;padding:0 12px}

/* ---------- 进度 ---------- */
.prog{flex:0 0 auto;display:flex;align-items:center;gap:10px;margin-top:10px;padding:6px 0}
.prog .tm{font-size:11px;color:rgba(255,255,255,.62);min-width:34px;font-variant-numeric:tabular-nums}
.prog .tm.r{text-align:right}
.bar{
  position:relative;flex:1;height:22px;display:flex;align-items:center;
}
.bar .track{
  position:relative;width:100%;height:3px;border-radius:2px;background:rgba(255,255,255,.24);
}
.bar .buf{position:absolute;left:0;top:0;height:100%;border-radius:2px;background:rgba(255,255,255,.30)}
.bar .fill{position:absolute;left:0;top:0;height:100%;border-radius:2px;background:#ffe14d}
.bar .dot{
  position:absolute;width:11px;height:11px;border-radius:50%;background:#fff;
  box-shadow:0 1px 6px rgba(0,0,0,.45);transform:translate(-50%,-50%);top:50%;left:0;
}

/* ---------- 主控制 ---------- */
.ctrl{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;padding:8px 4px 2px}
.ctrl .ic svg{width:25px;height:25px;stroke:rgba(255,255,255,.94)}
.ctrl .ic.small svg{width:22px;height:22px;stroke:rgba(255,255,255,.80)}
.ctrl .ic.act svg{stroke:#ffe14d}
#play{
  width:64px;height:64px;border-radius:50%;border:0;
  background:rgba(255,255,255,.96);color:#5a2050;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 10px 26px rgba(0,0,0,.36);
}
#play:active{transform:scale(.95)}
#play svg{width:28px;height:28px;fill:#5a2050;stroke:none}

/* ---------- 底栏 ---------- */
.foot{flex:0 0 auto;display:flex;align-items:center;justify-content:space-around;padding:10px 0 2px}
.foot button{
  border:0;background:transparent;color:rgba(255,255,255,.78);
  font-size:12.5px;padding:8px 12px;border-radius:16px;
  display:flex;flex-direction:column;align-items:center;gap:3px;font-family:inherit;
}
.foot button:active{background:rgba(255,255,255,.12)}
.foot svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.9;stroke-linecap:round;stroke-linejoin:round}

/* ---------- 面板 ---------- */
.sheet{
  position:fixed;left:0;right:0;bottom:0;z-index:20;
  background:linear-gradient(180deg,#48224f,#3a1a42);
  border-radius:20px 20px 0 0;padding:8px 0 calc(env(safe-area-inset-bottom,0px) + 12px);
  box-shadow:0 -12px 40px rgba(0,0,0,.5);
  transform:translateY(102%);transition:transform .28s cubic-bezier(.22,.61,.36,1);
  max-height:72%;overflow:auto;
}
.sheet.on{transform:translateY(0)}
.sheet .hd{
  display:flex;align-items:center;justify-content:space-between;
  padding:10px 18px 6px;font-size:14px;font-weight:600;color:rgba(255,255,255,.92);
}
.sheet .hd span{font-size:12px;color:rgba(255,255,255,.55);font-weight:400}
.sheet .it{
  display:flex;align-items:center;gap:10px;padding:11px 18px;font-size:14px;
  color:rgba(255,255,255,.86);
}
.sheet .it:active{background:rgba(255,255,255,.10)}
.sheet .it .sub{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sheet .it .tag{
  font-size:10.5px;padding:1.5px 6px;border-radius:6px;
  background:rgba(255,255,255,.14);color:rgba(255,255,255,.7);flex:0 0 auto;
}
.sheet .it.on{color:#ffe14d}
.mask{position:fixed;inset:0;z-index:19;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .28s}
.mask.on{opacity:1;pointer-events:auto}

#toast{
  position:fixed;left:50%;bottom:22%;transform:translate(-50%,10px);z-index:40;
  background:rgba(0,0,0,.78);color:#fff;font-size:13px;padding:9px 16px;border-radius:18px;
  opacity:0;pointer-events:none;transition:opacity .22s,transform .22s;max-width:80%;text-align:center;
}
#toast.on{opacity:1;transform:translate(-50%,0)}
#loading{
  position:fixed;inset:0;z-index:30;background:rgba(40,15,46,.72);
  display:none;align-items:center;justify-content:center;flex-direction:column;gap:14px;
}
#loading.on{display:flex}
#loading .ring{
  width:38px;height:38px;border-radius:50%;
  border:3px solid rgba(255,255,255,.22);border-top-color:#ffe14d;
  animation:spin .9s linear infinite;
}
#loading .tx{font-size:13px;color:rgba(255,255,255,.8)}
</style>
</head>
<body>
<div id="bgimg"></div>
<div id="bg"></div>
<div id="blob"></div>

<div class="app">
  <div class="topbar">
    <button class="ic" id="btnBack" aria-label="返回">
      <svg viewBox="0 0 24 24"><path d="M15 5l-7 7 7 7"/></svg>
    </button>
    <div class="src" id="srcName">music-dl</div>
    <button class="ic" id="btnTopMore" aria-label="更多">
      <svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.6" fill="#fff" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="#fff" stroke="none"/><circle cx="19" cy="12" r="1.6" fill="#fff" stroke="none"/></svg>
    </button>
  </div>

  <div class="stage">
    <div class="cover" id="coverBox">
      <img id="cover" alt="">
      <div class="none" id="coverNone">
        <svg viewBox="0 0 24 24"><path d="M12 3v10.6A3.4 3.4 0 1014 17V6h4V3z"/></svg>
      </div>
    </div>
    <div class="meta">
      <div class="t" id="mTitle">—</div>
      <div class="a" id="mArtist">—</div>
    </div>
  </div>

  <div class="lyric" id="lyricBox"><div class="inner" id="lyricInner"><div class="empty">正在读取歌词…</div></div></div>

  <div class="prog">
    <div class="tm" id="tCur">00:00</div>
    <div class="bar" id="bar">
      <div class="track"><div class="buf" id="pBuf"></div><div class="fill" id="pFill"></div></div>
      <div class="dot" id="pDot"></div>
    </div>
    <div class="tm r" id="tTot">00:00</div>
  </div>

  <div class="ctrl">
    <button class="ic small" id="btnMode" aria-label="循环模式">
      <svg viewBox="0 0 24 24" id="modeIcon"><path d="M17 2l3.5 3.5L17 9"/><path d="M20 5.5H7a4 4 0 00-4 4v1"/><path d="M7 22l-3.5-3.5L7 15"/><path d="M4 18.5h13a4 4 0 004-4v-1"/></svg>
    </button>
    <button class="ic" id="btnPrev" aria-label="上一首">
      <svg viewBox="0 0 24 24"><path d="M19 5v14L8 12z" fill="#fff" stroke="none"/><rect x="4.5" y="5" width="2.4" height="14" rx="1" fill="#fff" stroke="none"/></svg>
    </button>
    <button id="play" aria-label="播放">
      <svg viewBox="0 0 24 24" id="playIcon"><path d="M7 4.5l13 7.5-13 7.5z"/></svg>
    </button>
    <button class="ic" id="btnNext" aria-label="下一首">
      <svg viewBox="0 0 24 24"><path d="M5 5v14l11-7z" fill="#fff" stroke="none"/><rect x="17.1" y="5" width="2.4" height="14" rx="1" fill="#fff" stroke="none"/></svg>
    </button>
    <button class="ic small" id="btnList" aria-label="播放列表">
      <svg viewBox="0 0 24 24"><path d="M4 7h11M4 12h11M4 17h7"/><circle cx="18" cy="16.5" r="2.4"/><path d="M20.4 16.5V9.2l2 .5"/></svg>
    </button>
  </div>

  <div class="foot">
    <button id="btnLyricSrc">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M15.8 15.8L21 21"/></svg>
      搜索歌词
    </button>
    <button id="btnOptions">
      <svg viewBox="0 0 24 24"><path d="M5 8h9M18 8h1M5 16h3M12 16h7"/><circle cx="16" cy="8" r="2.2"/><circle cx="10" cy="16" r="2.2"/></svg>
      播放选项
    </button>
    <button id="btnMore">
      <svg viewBox="0 0 24 24"><circle cx="5" cy="12" r="1.7" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.7" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.7" fill="currentColor" stroke="none"/></svg>
      更多
    </button>
  </div>
</div>

<div class="mask" id="mask"></div>

<div class="sheet" id="sheetLyric">
  <div class="hd">歌词<div><span id="lyricState">—</span></div></div>
  <div class="it" id="lyricReload"><span class="sub">重新搜索歌词</span></div>
  <div class="it" id="lyricReport"><span class="sub">歌词不对？反馈给服务端</span></div>
  <div class="it"><span class="sub">歌词来源</span><span class="tag" id="lyricFrom">music-dl</span></div>
</div>

<div class="sheet" id="sheetOpt">
  <div class="hd">播放选项</div>
  <div class="it" data-opt="quality"><span class="sub">音质</span><span class="tag" id="optQ">标准</span></div>
  <div class="it" data-opt="probe"><span class="sub">播放前先探源</span><span class="tag" id="optP">关</span></div>
  <div class="it" data-opt="autonext"><span class="sub">自动播放下一首</span><span class="tag" id="optA">开</span></div>
  <div class="it" data-opt="lyricoff"><span class="sub">关闭滚动歌词</span><span class="tag" id="optL">关</span></div>
</div>

<div class="sheet" id="sheetList">
  <div class="hd">播放列表<span id="listCount">0 首</span></div>
  <div id="listBody"></div>
</div>

<div class="sheet" id="sheetMore">
  <div class="hd">更多</div>
  <div class="it" id="moreCopy"><span class="sub">复制歌曲信息</span></div>
  <div class="it" id="moreOpen"><span class="sub">用系统播放器打开</span></div>
  <div class="it" id="moreReload"><span class="sub">重新加载播放页</span></div>
  <div class="it" id="moreInfo"><span class="sub">当前音源</span><span class="tag" id="moreSrc">—</span></div>
</div>

<div id="toast"></div>
<div id="loading"><div class="ring"></div><div class="tx" id="loadingTx">正在取流…</div></div>

<script>
(function(){
  "use strict";

  // ---------------- 入参解析 ----------------
  function b64urlDecode(s){
    s = String(s || "").replace(/-/g,"+").replace(/_/g,"/");
    while (s.length % 4) s += "=";
    var bin = atob(s);
    var bytes = new Uint8Array(bin.length);
    for (var i=0;i<bin.length;i++) bytes[i] = bin.charCodeAt(i);
    try { return JSON.parse(new TextDecoder("utf-8").decode(bytes)); }
    catch(e){ return null; }
  }
  function b64urlEncode(obj){
    var bytes = new TextEncoder().encode(JSON.stringify(obj));
    var bin = ""; bytes.forEach(function(b){ bin += String.fromCharCode(b); });
    return btoa(bin).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"");
  }

  var Q = new URLSearchParams(location.search);
  var BOOT = b64urlDecode(Q.get("s")) || {};
  var API = BOOT.api || "/api";
  var LIST = Array.isArray(BOOT.list) && BOOT.list.length ? BOOT.list : [];
  var IDX = 0;
  if (BOOT.song && BOOT.song.uid){
    for (var i=0;i<LIST.length;i++){ if (LIST[i].uid === BOOT.song.uid){ IDX = i; break; } }
  } else { IDX = Number(BOOT.index || 0) || 0; }
  if (IDX < 0 || IDX >= LIST.length) IDX = 0;

  var SRCNAME = BOOT.srcname || {};

  // ---------------- 状态 ----------------
  var audio = new Audio();
  audio.preload = "metadata";
  audio.volume = 1;

  var MODES = ["list","single","random"];
  var MODE_TIP = { list:"列表循环", single:"单曲循环", random:"随机播放" };
  var mode = localStorage.getItem("mdl_mode") || "list";
  if (MODES.indexOf(mode) < 0) mode = "list";

  var opts = {
    autonext: localStorage.getItem("mdl_autonext") !== "0",
    lyricoff: localStorage.getItem("mdl_lyricoff") === "1",
    probe: false,
    quality: "标准"
  };

  var lrc = [], lrcIdx = -1, curDur = 0, seeking = false, loadingCount = 0;
  var streamCache = {};

  // ---------------- 元素 ----------------
  function $(id){ return document.getElementById(id); }
  var elTitle=$("mTitle"), elArtist=$("mArtist"), elCover=$("cover"), elCoverNone=$("coverNone"),
      elCoverBox=$("coverBox"), elSrc=$("srcName"), elLyric=$("lyricInner"), elLyricBox=$("lyricBox"),
      elCur=$("tCur"), elTot=$("tTot"), elFill=$("pFill"), elBuf=$("pBuf"), elDot=$("pDot"),
      elBar=$("bar"), elPlayIcon=$("playIcon"), elLoading=$("loading"), elLoadingTx=$("loadingTx");

  function toast(msg, ms){
    var t = $("toast"); t.textContent = msg; t.classList.add("on");
    clearTimeout(t._h); t._h = setTimeout(function(){ t.classList.remove("on"); }, ms || 1800);
  }
  var busyTimer = null;
  function busy(on, tx){
    loadingCount += on ? 1 : -1;
    if (loadingCount < 0) loadingCount = 0;
    if (on && tx) elLoadingTx.textContent = tx;
    elLoading.classList.toggle("on", loadingCount > 0);
    if (on){
      clearTimeout(busyTimer);
      busyTimer = setTimeout(function(){          // 兜底：9 秒后不再挡着界面
        loadingCount = 0; elLoading.classList.remove("on");
      }, 9000);
    } else {
      clearTimeout(busyTimer);
    }
  }
  function fmt(sec){
    if (!isFinite(sec) || sec < 0) sec = 0;
    sec = Math.floor(sec);
    var m = Math.floor(sec/60), s = sec%60;
    return (m<10?"0":"")+m+":"+(s<10?"0":"")+s;
  }
  function song(){
    return LIST[IDX] || {name:"未知歌曲", artist:"未知", source:"", id:""};
  }
  function srcLabel(s){
    if (!s) return "";
    return SRCNAME[s] || s;
  }

  // ---------------- 渲染 ----------------
  function renderMeta(){
    var s = song();
    elTitle.textContent = s.name || "未知歌曲";
    elArtist.textContent = (s.artist || "未知歌手") + (s.source ? "  ·  " + srcLabel(s.source) : "");
    elSrc.textContent = "music-dl" + (s.source ? "  ·  " + srcLabel(s.source) : "");
    $("moreSrc").textContent = srcLabel(s.source) || "—";
    var cover = s.cover || "";
    if (cover){
      elCover.src = cover;
      elCover.style.display = "block";
      elCoverNone.style.display = "none";
      elCover.onerror = function(){ elCover.style.display="none"; elCoverNone.style.display="flex"; };
    } else {
      elCover.removeAttribute("src");
      elCover.style.display = "none";
      elCoverNone.style.display = "flex";
    }
    var bgEl = document.getElementById("bgimg");
    if (bgEl) bgEl.style.backgroundImage = cover ? 'url("' + cover.replace(/"/g,"%22") + '")' : "none";
    document.title = (s.name || "正在播放");
  }

  function setPlayIcon(playing){
    elPlayIcon.innerHTML = playing
      ? '<path d="M7.5 5h3.2v14H7.5zM13.3 5h3.2v14h-3.2z"/>'
      : '<path d="M7 4.5l13 7.5-13 7.5z"/>';
    elCoverBox.classList.toggle("spin", !!playing);
  }

  function renderLyric(list, idx){
    elLyric.style.transform = "";
    if (!list || !list.length){
      elLyric.innerHTML = '<div class="empty">这首歌暂时没有歌词<br><span style="opacity:.7;font-size:12px">可以点底部「搜索歌词」再试一次</span></div>';
      $("lyricState").textContent = "无歌词";
      return;
    }
    var h = "";
    for (var i=0;i<list.length;i++){
      var tx = list[i].text || "♪";
      h += '<div class="ln" data-i="'+i+'">'+ esc(tx) +'</div>';
    }
    elLyric.innerHTML = h;
    $("lyricState").textContent = list.length + " 行";
    lrcIdx = -1;
    syncLyric(idx == null ? 0 : idx, true);
  }
  function esc(s){
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  }
  function syncLyric(i, force){
    if (opts.lyricoff) return;
    if (i === lrcIdx && !force) return;
    var nodes = elLyric.querySelectorAll(".ln");
    if (!nodes.length) return;
    if (lrcIdx >= 0 && nodes[lrcIdx]) nodes[lrcIdx].classList.remove("cur");
    lrcIdx = i;
    if (i < 0 || !nodes[i]) return;
    nodes[i].classList.add("cur");
    var n = nodes[i];
    var off = n.offsetTop + n.offsetHeight/2;
    elLyric.style.transform = "translateY(" + (-off) + "px)";
  }

  function renderList(){
    var body = $("listBody");
    $("listCount").textContent = LIST.length + " 首";
    var h = "";
    for (var i=0;i<LIST.length;i++){
      var s = LIST[i];
      h += '<div class="it'+(i===IDX?" on":"")+'" data-i="'+i+'">'
         + '<span class="sub">'+ esc(s.name||"未知") +'</span>'
         + (s.source ? '<span class="tag">'+ esc(srcLabel(s.source)) +'</span>' : '')
         + '</div>';
    }
    body.innerHTML = h || '<div class="it"><span class="sub">列表是空的</span></div>';
  }

  // ---------------- 歌词 ----------------
  function parseLrc(text){
    if (!text) return [];
    var out = [], lines = String(text).split(/\r?\n/);
    var tagRe = /\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g;
    for (var i=0;i<lines.length;i++){
      var raw = lines[i], m, times = [], last = 0;
      tagRe.lastIndex = 0;
      while ((m = tagRe.exec(raw))){
        var mm = parseInt(m[1],10), ss = parseInt(m[2],10);
        var frac = m[3] ? parseInt(m[3],10) : 0;
        if (m[3] && m[3].length === 2) frac *= 10;
        else if (m[3] && m[3].length === 1) frac *= 100;
        times.push(mm*60 + ss + frac/1000);
        last = tagRe.lastIndex;
      }
      var body = raw.slice(last).trim();
      if (!times.length && !body) continue;
      if (!body && !times.length) continue;
      for (var k=0;k<times.length;k++) out.push({ t: times[k], text: body });
    }
    out.sort(function(a,b){ return a.t - b.t; });
    return out;
  }

  function loadLyric(){
    if (opts.lyricoff){ elLyric.innerHTML = '<div class="empty">滚动歌词已关闭</div>'; return; }
    var s = song();
    elLyric.innerHTML = '<div class="empty">正在读取歌词…</div>';
    var q = API + "/lyric?source=" + encodeURIComponent(s.source||"")
          + "&id=" + encodeURIComponent(s.id||"")
          + "&name=" + encodeURIComponent(s.name||"")
          + "&artist=" + encodeURIComponent(s.artist||"")
          + "&extra=" + encodeURIComponent(JSON.stringify(s.extra||{}));
    fetch(q, {cache:"no-store"}).then(function(r){ return r.json(); }).then(function(d){
      var list = parseLrc(d && (d.lrc || d.lyric || ""));
      renderLyric(list);
      $("lyricFrom").textContent = (d && d.from) || "music-dl";
    }).catch(function(){
      renderLyric([]);
    });
  }

  // ---------------- 取流 ----------------
  function streamUrl(realUrl){
    return API + "/stream?u=" + b64urlEncode({ u: realUrl });
  }

  function pickUrl(){
    var s = song();
    var q = API + "/url?source=" + encodeURIComponent(s.source||"")
          + "&id=" + encodeURIComponent(s.id||"")
          + "&name=" + encodeURIComponent(s.name||"")
          + "&artist=" + encodeURIComponent(s.artist||"")
          + "&extra=" + encodeURIComponent(JSON.stringify(s.extra||{}));
    return fetch(q, {cache:"no-store"}).then(function(r){ return r.json(); });
  }

  function playIndex(i, autoplay){
    if (!LIST.length) return;
    IDX = (i + LIST.length) % LIST.length;
    var s = song();
    renderMeta();
    renderList();
    loadLyric();
    busy(true, "正在取流…");
    var cached = streamCache[s.uid];
    var jobs = cached ? Promise.resolve({url: cached}) : pickUrl();
    jobs.then(function(d){
      var real = d && (d.url || "");
      if (!real){
        busy(false);
        toast((d && d.msg) || "这首歌这个源拿不到播放地址", 2600);
        return;
      }
      streamCache[s.uid] = real;
      audio.src = streamUrl(real);
      audio.load();
      if (autoplay !== false) audio.play().catch(function(){});
    }).catch(function(){
      busy(false);
      toast("取流失败，检查服务是否在跑", 2600);
    });
  }

  // ---------------- 播放控制 ----------------
  function togglePlay(){
    if (!audio.src){ playIndex(IDX, true); return; }
    if (audio.paused) audio.play().catch(function(){}); else audio.pause();
  }
  function next(auto){
    if (mode === "single" && auto){ audio.currentTime = 0; audio.play().catch(function(){}); return; }
    var n;
    if (mode === "random"){ n = Math.floor(Math.random()*LIST.length); if (LIST.length>1 && n===IDX) n = (n+1)%LIST.length; }
    else n = (IDX + 1) % LIST.length;
    playIndex(n, true);
  }
  function prev(){
    if (mode === "random"){ next(false); return; }
    playIndex((IDX - 1 + LIST.length) % LIST.length, true);
  }

  audio.addEventListener("play",   function(){ setPlayIcon(true); });
  audio.addEventListener("pause",  function(){ setPlayIcon(false); });
  audio.addEventListener("waiting",function(){ busy(true, "缓冲中…"); });
  audio.addEventListener("playing",function(){ busy(false); });
  audio.addEventListener("canplay",function(){ busy(false); });
  audio.addEventListener("loadedmetadata", function(){
    curDur = audio.duration || 0;
    elTot.textContent = fmt(curDur);
  });
  audio.addEventListener("timeupdate", function(){
    if (!seeking && curDur){
      var p = Math.min(100, Math.max(0, audio.currentTime / curDur * 100));
      elFill.style.width = p + "%";
      elDot.style.left = p + "%";
    }
    elCur.textContent = fmt(audio.currentTime);
    if (lrc.length && !opts.lyricoff){
      var t = audio.currentTime + 0.18, i = -1;
      for (var k=0;k<lrc.length;k++){ if (lrc[k].t <= t) i = k; else break; }
      if (i >= 0) syncLyric(i, false);
    }
  });
  audio.addEventListener("ended", function(){
    if (opts.autonext) next(true); else setPlayIcon(false);
  });
  audio.addEventListener("error", function(){
    busy(false);
    if (audio.src) toast("播放出错：这个源这首歌拉不动，换一首试试", 2600);
  });
  audio.addEventListener("progress", function(){
    try {
      if (audio.buffered.length && curDur){
        var end = audio.buffered.end(audio.buffered.length-1);
        elBuf.style.width = Math.min(100, end/curDur*100) + "%";
      }
    } catch(e){}
  });

  // ---------------- 进度拖动 ----------------
  function ratioFromEvent(e){
    var r = elBar.getBoundingClientRect();
    var x = (e.touches && e.touches[0] ? e.touches[0].clientX : e.clientX) - r.left;
    return Math.min(1, Math.max(0, x / r.width));
  }
  function onSeekStart(e){ if (!curDur) return; seeking = true; onSeekMove(e); }
  function onSeekMove(e){
    if (!seeking) return;
    var r = ratioFromEvent(e);
    elFill.style.width = (r*100)+"%";
    elDot.style.left = (r*100)+"%";
    elCur.textContent = fmt(r*curDur);
    if (e.preventDefault) e.preventDefault();
  }
  function onSeekEnd(e){
    if (!seeking) return;
    seeking = false;
    var r = ratioFromEvent(e.changedTouches ? {clientX:e.changedTouches[0].clientX} : e);
    if (curDur) audio.currentTime = r * curDur;
  }
  elBar.addEventListener("touchstart", onSeekStart, {passive:true});
  elBar.addEventListener("touchmove",  onSeekMove,  {passive:false});
  elBar.addEventListener("touchend",   onSeekEnd,   {passive:true});
  elBar.addEventListener("mousedown",  onSeekStart);
  document.addEventListener("mousemove", onSeekMove);
  document.addEventListener("mouseup",   onSeekEnd);

  // ---------------- 事件绑定 ----------------
  document.getElementById("play").addEventListener("click", togglePlay);
  $("btnNext").addEventListener("click", function(){ next(false); });
  $("btnPrev").addEventListener("click", prev);
  $("btnBack").addEventListener("click", function(){
    if (window.AndroidBridge && AndroidBridge.close) AndroidBridge.close();
    else if (history.length > 1) history.back();
    else toast("返回键退出即可");
  });

  $("btnMode").addEventListener("click", function(){
    var i = (MODES.indexOf(mode) + 1) % MODES.length;
    mode = MODES[i];
    localStorage.setItem("mdl_mode", mode);
    $("btnMode").classList.toggle("act", mode !== "list");
    $("modeIcon").innerHTML = mode === "single"
      ? '<path d="M17 2l3.5 3.5L17 9"/><path d="M20 5.5H7a4 4 0 00-4 4v1"/><path d="M7 22l-3.5-3.5L7 15"/><path d="M4 18.5h13a4 4 0 004-4v-1"/><text x="9.5" y="15.5" font-size="8" fill="#fff" stroke="none" font-family="sans-serif">1</text>'
      : mode === "random"
      ? '<path d="M4 6h4l8 12h4"/><path d="M20 18l-3 3M20 18l-3-3" transform="translate(0,-4)"/><path d="M4 18h4M16 6h4"/>'
      : '<path d="M17 2l3.5 3.5L17 9"/><path d="M20 5.5H7a4 4 0 00-4 4v1"/><path d="M7 22l-3.5-3.5L7 15"/><path d="M4 18.5h13a4 4 0 004-4v-1"/>';
    toast(MODE_TIP[mode]);
  });

  function sheetOpen(id){
    ["sheetLyric","sheetOpt","sheetList","sheetMore"].forEach(function(x){
      $(x).classList.toggle("on", x === id);
    });
    $("mask").classList.toggle("on", !!id);
  }
  $("mask").addEventListener("click", function(){ sheetOpen(null); });
  $("btnTopMore").addEventListener("click", function(){ sheetOpen("sheetMore"); });
  $("btnMore").addEventListener("click", function(){ sheetOpen("sheetMore"); });
  $("btnList").addEventListener("click", function(){ renderList(); sheetOpen("sheetList"); });
  $("btnOptions").addEventListener("click", function(){ sheetOpen("sheetOpt"); });
  $("btnLyricSrc").addEventListener("click", function(){ sheetOpen("sheetLyric"); });

  $("lyricReload").addEventListener("click", function(){ sheetOpen(null); loadLyric(); });
  $("lyricReport").addEventListener("click", function(){
    var s = song();
    sheetOpen(null);
    toast("已记录：" + (s.name||"") + " / " + srcLabel(s.source), 2200);
  });

  $("listBody").addEventListener("click", function(e){
    var it = e.target.closest(".it");
    if (!it || it.dataset.i == null) return;
    sheetOpen(null);
    playIndex(parseInt(it.dataset.i,10), true);
  });

  // 播放选项
  function renderOpts(){
    $("optA").textContent = opts.autonext ? "开" : "关";
    $("optL").textContent = opts.lyricoff ? "开" : "关";
    $("optP").textContent = opts.probe ? "开" : "关";
    $("optQ").textContent = opts.quality;
  }
  $("sheetOpt").addEventListener("click", function(e){
    var it = e.target.closest(".it"); if (!it) return;
    var o = it.dataset.opt;
    if (o === "autonext"){ opts.autonext = !opts.autonext; localStorage.setItem("mdl_autonext", opts.autonext?"1":"0"); }
    if (o === "lyricoff"){ opts.lyricoff = !opts.lyricoff; localStorage.setItem("mdl_lyricoff", opts.lyricoff?"1":"0");
      if (opts.lyricoff) renderLyric([]); else loadLyric(); }
    if (o === "probe"){ opts.probe = !opts.probe; toast("播放前探源：" + (opts.probe?"开":"关")); }
    if (o === "quality"){ opts.quality = opts.quality === "标准" ? "高" : "标准"; streamCache = {}; toast("音质：" + opts.quality + "（下次播放生效）"); }
    renderOpts();
  });

  $("moreCopy").addEventListener("click", function(){
    var s = song();
    var txt = (s.name||"") + " - " + (s.artist||"") + "  [" + srcLabel(s.source) + "]";
    try { navigator.clipboard.writeText(txt); } catch(e){}
    toast("已复制");
  });
  $("moreOpen").addEventListener("click", function(){
    var s = song();
    var real = streamCache[s.uid];
    if (!real){ toast("还没取到流"); return; }
    window.location.href = streamUrl(real);
  });
  $("moreReload").addEventListener("click", function(){ location.reload(); });
  $("moreInfo").addEventListener("click", function(){ sheetOpen(null); });

  // 歌词点击跳转
  elLyric.addEventListener("click", function(e){
    var n = e.target.closest(".ln"); if (!n || !lrc.length) return;
    var i = parseInt(n.dataset.i,10);
    if (isNaN(i) || !lrc[i]) return;
    if (curDur) audio.currentTime = Math.min(lrc[i].t, curDur - 0.2);
    syncLyric(i, true);
  });

  // 键盘（桌面/模拟器上调试方便）
  document.addEventListener("keydown", function(e){
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    if (e.key === "ArrowRight") next(false);
    if (e.key === "ArrowLeft") prev();
  });

  // ---------------- 启动 ----------------
  function afterList(){
    renderList();
    if (!LIST.length){
      toast("没拿到歌曲内容", 2600);
      loadLyric();
      return;
    }
    var cur = BOOT.song || {};
    if (cur.uid){
      for (var i=0;i<LIST.length;i++){
        if (LIST[i].uid === cur.uid){ IDX = i; break; }
      }
    }
    renderMeta();
    renderList();
    if (Q.get("p") === "1"){   // 预览模式：只渲染界面，不自动取流
      loadLyric();
      return;
    }
    playIndex(IDX, true);
  }

  function start(){
    renderMeta();
    renderOpts();
    $("btnMode").classList.toggle("act", mode !== "list");
    setPlayIcon(false);
    if (LIST.length){ afterList(); return; }
    if (BOOT.song) LIST = [BOOT.song];
    var CTX = BOOT.ctx || null;
    if (!CTX || !CTX.u){ afterList(); return; }
    fetch(API + "/list?ctx=" + b64urlEncode({u: CTX.u, x: CTX.x || 0}), {cache:"no-store"})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.list && d.list.length) LIST = d.list;
        if (d && d.srcname) SRCNAME = d.srcname;
      })
      .catch(function(){})
      .then(afterList);
  }
  start();
})();
</script>
</body>
</html>
"""

# 歌词抓取缓存（source, id, name, artist）-> (时间, 结果)
_LRC_CACHE = {}

_UI_SERVER = {"lock": None, "httpd": None, "port": 0, "err": "", "tried": False}


def _ui_srv(spider):
    """懒启动本地播放页服务。返回 (ok, port, err)。"""
    if _UI_SERVER["lock"] is None:
        _UI_SERVER["lock"] = threading.Lock()
    with _UI_SERVER["lock"]:
        if _UI_SERVER["httpd"] is not None:
            return True, _UI_SERVER["port"], ""
        if _UI_SERVER["tried"] and _UI_SERVER["err"]:
            return False, 0, _UI_SERVER["err"]
        _UI_SERVER["tried"] = True
        last = ""
        for port in range(UI_PORT, UI_PORT + 12):
            try:
                handler = _ui_handler(spider)
                httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
                try:
                    httpd.daemon_threads = True
                except Exception:
                    pass
                th = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.4})
                th.daemon = True
                th.start()
                _UI_SERVER["httpd"] = httpd
                _UI_SERVER["port"] = port
                _UI_SERVER["err"] = ""
                return True, port, ""
            except Exception as e:
                last = "%s" % e
                continue
        _UI_SERVER["err"] = last or "端口被占用"
        return False, 0, _UI_SERVER["err"]


def _ui_b64e(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _ui_b64d(text):
    try:
        s = (text or "").strip()
        s += "=" * (-len(s) % 4)
        return json.loads(base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


# ---------------- 歌词 ----------------

def _lyric_get(url, referer=None):
    headers = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9"}
    if referer:
        headers["Referer"] = referer
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def _lyric_netease(sid):
    if not sid:
        return ""
    j = _lyric_get("https://music.163.com/api/song/lyric?id=%s&lv=1&kv=1&tv=-1" % urllib.parse.quote(str(sid)),
                   referer="https://music.163.com/")
    if not j:
        return ""
    try:
        d = json.loads(j)
    except Exception:
        return ""
    lrc = ((d.get("lrc") or {}).get("lyric") or "")
    tl = ((d.get("tlyric") or {}).get("lyric") or "")
    if lrc:
        return lrc
    return ""


def _lyric_qq(mid):
    if not mid:
        return ""
    j = _lyric_get("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                   "?songmid=%s&format=json&nobase64=1&g_tk=5381" % urllib.parse.quote(str(mid)),
                   referer="https://y.qq.com/portal/player.html")
    if not j:
        return ""
    try:
        d = json.loads(j)
    except Exception:
        return ""
    return d.get("lyric") or ""


def _qq_mid_by_name(name, artist):
    """按歌名+歌手去 QQ 音乐搜一个 songmid（跨平台兜底用）。"""
    kw = ("%s %s" % (name or "", artist or "")).strip()
    if not kw:
        return ""
    j = _lyric_get("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w=%s&format=json&n=3&p=1"
                   % urllib.parse.quote(kw), referer="https://y.qq.com/")
    if not j:
        return ""
    try:
        d = json.loads(j)
        lst = (((d.get("data") or {}).get("song") or {}).get("list") or [])
        if lst:
            return lst[0].get("songmid") or lst[0].get("mid") or ""
    except Exception:
        pass
    return ""


def _lyric_fetch(source, sid, name, artist):
    key = (source or "", str(sid or ""), name or "", artist or "")
    hit = _LRC_CACHE.get(key)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    out = {"lrc": "", "from": ""}

    if source == "netease" and sid:
        out["lrc"] = _lyric_netease(sid)
        if out["lrc"]:
            out["from"] = "网易云"
    elif source == "qq" and sid:
        out["lrc"] = _lyric_qq(sid)
        if out["lrc"]:
            out["from"] = "QQ音乐"

    if not out["lrc"] and name:
        mid = _qq_mid_by_name(name, artist)
        if mid:
            out["lrc"] = _lyric_qq(mid)
            if out["lrc"]:
                out["from"] = "QQ音乐"

    if not out["lrc"] and str(sid or "").isdigit():
        out["lrc"] = _lyric_netease(sid)
        if out["lrc"]:
            out["from"] = "网易云"

    try:
        if len(_LRC_CACHE) > 200:
            _LRC_CACHE.clear()
        _LRC_CACHE[key] = (time.time(), out)
    except Exception:
        pass
    return out


# ---------------- 播放页 HTTP 服务 ----------------

def _ui_handler(spider):
    class _H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "zakamd/1.0"

        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body, extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass

        def _json(self, obj, code=200):
            self._send(code, "application/json; charset=utf-8",
                       json.dumps(obj, ensure_ascii=False))

        def do_HEAD(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/p", "/"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(PLAYER_HTML.encode("utf-8"))))
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            path = u.path

            if path in ("/p", "/"):
                return self._send(200, "text/html; charset=utf-8", PLAYER_HTML)

            if path == "/favicon.ico":
                return self._send(204, "image/x-icon", b"")

            if path == "/api/ping":
                return self._json({"ok": True, "ver": "1.0"})

            # 播放列表：页面按需拉（免得点歌时先等一次大请求）
            if path == "/api/list":
                boot = _ui_b64d((q.get("ctx") or [""])[0]) or {}
                ctx_url = boot.get("u") or ""
                idx = int(boot.get("x") or 0)
                songs = []
                try:
                    songs, _err = spider._fetch_songs(ctx_url)
                except Exception:
                    songs = []
                items = []
                for s in songs:
                    items.append({
                        "uid": "%s:%s" % (s.get("source") or "", s.get("id") or ""),
                        "id": s.get("id") or "",
                        "source": s.get("source") or "",
                        "name": s.get("name") or "",
                        "artist": s.get("artist") or "",
                        "album": s.get("album") or "",
                        "cover": spider._cover(s.get("cover") or "", s.get("source") or ""),
                        "duration": s.get("duration") or "",
                        "extra": s.get("extra") if isinstance(s.get("extra"), dict) else {},
                    })
                return self._json({"list": items, "srcname": SOURCE_NAME, "index": idx})

            if path == "/api/lyric":
                g = lambda k: (q.get(k) or [""])[0]
                got = _lyric_fetch(g("source"), g("id"), g("name"), g("artist"))
                return self._json(got)

            if path == "/api/url":
                g = lambda k: (q.get(k) or [""])[0]
                sid = g("id")
                source = g("source")
                extra = {}
                try:
                    extra = json.loads(g("extra") or "{}")
                except Exception:
                    extra = {}
                if not sid:
                    return self._json({"url": "", "msg": "这首歌没有 id"})
                params = {
                    "id": sid,
                    "source": source,
                    "name": g("name") or "Unknown",
                    "artist": g("artist") or "Unknown",
                    "album": g("album") or "",
                    "cover": g("cover") or "",
                    "stream": "1",
                }
                if extra:
                    params["extra"] = json.dumps(extra, ensure_ascii=False, separators=(",", ":"))
                target = spider._url("/download", params)
                try:
                    return self._json({"url": target})
                except Exception as e:
                    return self._json({"url": "", "msg": "%s" % e})

            # 音频流代理：同源输出，页面里的播放器才拖得动进度
            if path == "/api/stream":
                boot = _ui_b64d((q.get("u") or [""])[0]) or {}
                target = boot.get("u") or ""
                if not target:
                    return self._send(400, "text/plain", "no url")
                return self._pipe(target)

            return self._send(404, "text/plain", "not found")

        # ---------------- 音频流透传（支持 Range） ----------------
        def _pipe(self, target):
            rng = self.headers.get("Range")
            headers = {"User-Agent": UA, "Accept": "*/*", "Connection": "close"}
            if rng:
                headers["Range"] = rng
            try:
                req = urllib.request.Request(target, headers=headers)
                resp = urllib.request.urlopen(req, timeout=max(10, REQ_TIMEOUT))
            except Exception as e:
                return self._send(502, "text/plain", "拉流失败: %s" % e)
            code = getattr(resp, "status", 200) or 200
            ctype = resp.headers.get("Content-Type") or "audio/mpeg"
            length = resp.headers.get("Content-Length")
            crange = resp.headers.get("Content-Range")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if length:
                self.send_header("Content-Length", length)
            if crange:
                self.send_header("Content-Range", crange)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception:
                pass
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

    return _H



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["music-dl"]

def _tvbox_filter_lines(result, drop):
    if not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_filter_item(item, drop)
    else:
        _tvbox_filter_item(result, drop)
    return result

def _tvbox_filter_item(item, drop):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    keep = [(f, u) for f, u in zip(parts_from, parts_url) if f not in drop]
    if not keep or len(keep) == len(parts_from):
        return
    item['vod_play_from'] = '$$$'.join(f for f, _ in keep)
    item['vod_play_url'] = '$$$'.join(u for _, u in keep)

def _tvbox_sort_lines(result, order):
    if not order or not isinstance(result, dict):
        return result
    items = result.get('list')
    if isinstance(items, list):
        for item in items:
            _tvbox_sort_item(item, order)
    else:
        _tvbox_sort_item(result, order)
    return result

def _tvbox_sort_item(item, order):
    froms = item.get('vod_play_from') or ''
    urls = item.get('vod_play_url') or ''
    if not isinstance(froms, str) or not isinstance(urls, str):
        return
    if '$$$' not in froms:
        return
    parts_from = [f.strip() for f in froms.split('$$$')]
    parts_url = urls.split('$$$')
    if len(parts_from) != len(parts_url):
        return
    known = {f: i for i, f in enumerate(order)}
    pairs = list(zip(parts_from, parts_url))
    # 已知线路按 order（画质速度最优在前），未知线路稳定保持原序后置。
    pairs.sort(key=lambda p: known.get(p[0], len(order)))
    item['vod_play_from'] = '$$$'.join(f for f, _ in pairs)
    item['vod_play_url'] = '$$$'.join(u for _, u in pairs)

def _tvbox_apply(cls):
    fn = getattr(cls, 'detailContent', None)
    if fn is None:
        return
    def wrapper(self, *a, _fn=fn, **k):
        res = _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)
        return _tvbox_sort_lines(res, _TVBOX_LINE_ORDER)
    setattr(cls, 'detailContent', wrapper)

_tvbox_apply(Spider)
