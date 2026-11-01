# coding=utf-8
"""
VS影院 vssdy.com | TVBox Python 爬虫 
- 亮点：修复元信息抓取（类型/地区/年份/完整演员/导演）
- 亮点：默认开启极速秒开（Python 复现 dypck.js 直链解密，告别 WebView 嗅探延迟）
- 保留：筛选（分类/地区/年份/类型）四维支持
"""
import re
import sys
import json
import time
import urllib.parse

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as _rq
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass

    class _BaseSpider:
        def __init__(self):
            self._session = None

        @property
        def _sess(self):
            if self._session is None:
                self._session = _rq.Session()
                self._session.verify = False
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[vssdy]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.vssdy.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/dydysf/yj_pic/img/load.jpg"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "电影",   "type_name": "电影"},
    {"type_id": "电视剧", "type_name": "电视剧"},
    {"type_id": "综艺",   "type_name": "综艺"},
    {"type_id": "动漫",   "type_name": "动漫"},
    {"type_id": "短剧",   "type_name": "短剧"},
]

# ===================== 筛选 =====================
_ALL = {"n": "全部", "v": ""}

_AREAS = [_ALL,
    {"n": "中国大陆", "v": "中国大陆"}, {"n": "中国香港", "v": "中国香港"},
    {"n": "中国台湾", "v": "中国台湾"}, {"n": "美国",     "v": "美国"},
    {"n": "日本",     "v": "日本"},     {"n": "韩国",     "v": "韩国"},
    {"n": "英国",     "v": "英国"},     {"n": "法国",     "v": "法国"},
    {"n": "德国",     "v": "德国"},     {"n": "印度",     "v": "印度"},
    {"n": "泰国",     "v": "泰国"},     {"n": "其他",     "v": "其他"},
]

_YEARS = [_ALL] + [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]

_MOVIE_GENRES = [_ALL, {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "科幻", "v": "科幻"}, {"n": "恐怖", "v": "恐怖"}, {"n": "灾难", "v": "灾难"}, {"n": "战争", "v": "战争"}, {"n": "剧情", "v": "剧情"}, {"n": "悬疑", "v": "悬疑"}, {"n": "犯罪", "v": "犯罪"}, {"n": "动画", "v": "动画"}, {"n": "奇幻", "v": "奇幻"}, {"n": "冒险", "v": "冒险"}, {"n": "纪录片", "v": "纪录片"}]

_TV_GENRES = [_ALL, {"n": "剧情", "v": "剧情"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "悬疑", "v": "悬疑"}, {"n": "犯罪", "v": "犯罪"}, {"n": "古装", "v": "古装"}, {"n": "动作", "v": "动作"}, {"n": "家庭", "v": "家庭"}, {"n": "国产", "v": "国产"}, {"n": "内地剧", "v": "内地剧"}, {"n": "历史革命", "v": "历史革命"}, {"n": "领袖人物", "v": "领袖人物"}]

_VARIETY_GENRES = [_ALL, {"n": "真人秀", "v": "真人秀"}, {"n": "脱口秀", "v": "脱口秀"}, {"n": "选秀", "v": "选秀"}, {"n": "访谈", "v": "访谈"}, {"n": "音乐", "v": "音乐"}, {"n": "生活", "v": "生活"}]

_ANIME_GENRES = [_ALL, {"n": "动画", "v": "动画"}, {"n": "日韩动漫", "v": "日韩动漫"}, {"n": "国产动漫", "v": "国产动漫"}, {"n": "欧美动漫", "v": "欧美动漫"}, {"n": "港台动漫", "v": "港台动漫"}]

_DUANJU_GENRES = [_ALL, {"n": "短剧", "v": "短剧"}, {"n": "爱情", "v": "爱情"}, {"n": "剧情", "v": "剧情"}, {"n": "爽文", "v": "爽文"}, {"n": "古装", "v": "古装"}, {"n": "穿越", "v": "穿越"}]

FILTERS = {
    "电影": [{"key": "area", "name": "地区", "value": _AREAS}, {"key": "year", "name": "年份", "value": _YEARS}, {"key": "class", "name": "类型", "value": _MOVIE_GENRES}],
    "电视剧": [{"key": "area", "name": "地区", "value": _AREAS}, {"key": "year", "name": "年份", "value": _YEARS}, {"key": "class", "name": "类型", "value": _TV_GENRES}],
    "综艺": [{"key": "area", "name": "地区", "value": _AREAS}, {"key": "year", "name": "年份", "value": _YEARS}, {"key": "class", "name": "类型", "value": _VARIETY_GENRES}],
    "动漫": [{"key": "area", "name": "地区", "value": _AREAS}, {"key": "year", "name": "年份", "value": _YEARS}, {"key": "class", "name": "类型", "value": _ANIME_GENRES}],
    "短剧": [{"key": "area", "name": "地区", "value": _AREAS}, {"key": "year", "name": "年份", "value": _YEARS}, {"key": "class", "name": "类型", "value": _DUANJU_GENRES}],
}

# ===================== 列表正则 =====================
_RE_CARD = re.compile(
    r'<a\s+class="[^"]*stui-vodlist__thumb lazyload[^"]*"\s+'
    r'href="(/resource/\d+\.html)"\s+'
    r'title="([^"]*)"\s+'
    r'data-original="([^"]*)"[^>]*>'
    r'[\s\S]{0,300}?'
    r'<span class="pic-text text-right">([^<]*)</span>',
    re.S | re.I)

_RE_TEXT_CARD = re.compile(
    r'<a class="top-line-dot text-overflow" href="(/resource/\d+\.html)" title="([^"]*)">\s*'
    r'<span class="text-muted pull-right">([^<]*)</span>([^<]*)</a>',
    re.S | re.I)

_RE_PAGE = re.compile(r'page=(\d+)', re.I)

# ===================== 详情正则 =====================
_RE_H1 = re.compile(r'<h1 class="title">([^<]+)</h1>', re.I)
_RE_DETAIL_PIC = re.compile(r'<div class="stui-content__thumb">[\s\S]*?<img[^>]*data-original="([^"]+)"', re.I)
_RE_DETAIL_REMARK = re.compile(r'<div class="stui-content__thumb">[\s\S]*?<span class="pic-text text-right">([^<]*)</span>', re.I)
_RE_INTRO_FULL = re.compile(r'<div[^>]*id="desc"[^>]*>[\s\S]*?<div class="col-pd">([\s\S]*?)</div>', re.I)

# 修复：全面兼容复杂排版的主演和导演
_RE_ACTOR = re.compile(r'<span class="text-muted">主演：</span>\s*([\s\S]*?)</p>', re.I)
_RE_DIRECTOR = re.compile(r'<span class="text-muted">导演：</span>\s*([\s\S]*?)</p>', re.I)
_RE_TAGS = re.compile(r'<span class="text-muted">类型：</span>\s*([\s\S]*?)<span class="split-line">', re.I)
_RE_AREA_YEAR = re.compile(r'<span class="text-muted hidden-xs">地区：</span>\s*<a[^>]*>([^<]+)</a>[\s\S]*?<span class="text-muted hidden-xs">年份：</span>\s*<a[^>]*>([^<]+)</a>', re.I)

# ===================== 线路/剧集正则 =====================
_RE_LINE_TABS = re.compile(r'<a href="javascript:;" data-target="\.ff-playurl-tab-(\d+)" data-toggle="tab">\s*<span[^>]*></span>([^<]+)</a>', re.S | re.I)
_RE_EPISODE_UL = re.compile(r'<ul class="stui-content__playlist[^"]*ff-playurl-tab-(\d+)[^"]*">([\s\S]*?)</ul>', re.S | re.I)
_RE_EPISODE_A = re.compile(r'<a title="([^"]*)" href="(/play/[^"]+)" target="_self">([^<]*)</a>', re.S | re.I)

_RE_PLAY_PATH = re.compile(r'/play/(\d+)-(\d+)-(\d+)\.html', re.I)


class Spider(Spider):

    def getName(self):
        return "VS影院"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.site_url = (self.extend.get("site") or HOST).rstrip("/")
        self.headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.site_url + "/",
        }
        self.default_pic = DEFAULT_PIC
        self.log("init: site=%s" % self.site_url)

    # ---------- 工具 ----------
    def _fetch(self, url, timeout=20):
        try:
            rsp = self.fetch(url, headers=self.headers, timeout=timeout)
            return rsp.text or ""
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"): return "https:" + url
        if url.startswith("http"): return url
        if url.startswith("/"): return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

    def _clean(self, s):
        if not s: return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    # ---------- 列表 ----------
    def _extract_videos(self, html):
        videos, seen = [], set()
        if not html: return videos

        for href, title, pic, remark in _RE_CARD.findall(html):
            if href in seen: continue
            seen.add(href)
            videos.append({
                "vod_id": href, "vod_name": self._clean(title)[:100],
                "vod_pic": pic or self.default_pic, "vod_remarks": self._clean(remark),
            })

        for href, title, remark, name in _RE_TEXT_CARD.findall(html):
            if href in seen: continue
            seen.add(href)
            videos.append({
                "vod_id": href, "vod_name": self._clean(title or name)[:100],
                "vod_pic": self.default_pic, "vod_remarks": self._clean(remark),
            })
        return videos

    def _page_count(self, html):
        if not html: return 1
        pages = _RE_PAGE.findall(html)
        if pages:
            try: return max(int(p) for p in pages) + 1
            except Exception: pass
        return 9999

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        return {"list": self._extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        area, year, genre = "", "", ""
        if isinstance(extend, dict):
            area  = extend.get("area", "")  or ""
            year  = extend.get("year", "")  or ""
            genre = extend.get("class", "") or ""
            if area  == "全部": area  = ""
            if year  == "全部": year  = ""
            if genre == "全部": genre = ""

        path = "/catalog/%s-%s-%s-%s-----%d-24.html" % (tid, area, year, genre, page - 1)
        url = self.site_url + path + "?order=&page=%d&size=24" % (page - 1)
        
        html = self._fetch(url)
        videos = self._extract_videos(html)
        pagecount = self._page_count(html)
        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": pagecount * 24,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        url = "%s/search?searchword=%s&page=%d" % (self.site_url, urllib.parse.quote(key), page)
        html = self._fetch(url)
        return {
            "list": self._extract_videos(html), "page": page,
            "pagecount": self._page_count(html), "limit": 24, "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------- 详情 ----------
    def detailContent(self, ids):
        if not ids: return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        html = self._fetch(url)
        if not html: return {"list": []}

        name = ""
        m = _RE_H1.search(html)
        if m: name = self._clean(m.group(1))
        if not name:
            m = re.search(r"<title>《([^》]+)》", html)
            if m: name = self._clean(m.group(1))
        if not name: name = vod_id

        pic = self.default_pic
        m = _RE_DETAIL_PIC.search(html)
        if m: pic = m.group(1)

        content = ""
        m = _RE_INTRO_FULL.search(html)
        if m: content = self._clean(m.group(1))
        content = (INTRO_PREFIX + "\n" + content) if content else INTRO_PREFIX

        # ====== 修复元信息抓取 ======
        actor = ""
        m = _RE_ACTOR.search(html)
        if m: 
            # 清理掉所有的链接标签，只留纯文本，去掉末尾的 ...
            actor = self._clean(m.group(1)).replace("...", "").strip()

        director = ""
        m = _RE_DIRECTOR.search(html)
        if m: 
            director = self._clean(m.group(1)).replace("...", "").strip()

        # 抓取类型标签
        type_tags = ""
        m = _RE_TAGS.search(html)
        if m: 
            type_tags = self._clean(m.group(1)).replace(" ", " / ")
            
        # 抓取地区和年份
        area_year = ""
        m = _RE_AREA_YEAR.search(html)
        if m:
            area_year = "%s / %s" % (self._clean(m.group(1)), self._clean(m.group(2)))

        # ==========================

        remark = ""
        m = _RE_DETAIL_REMARK.search(html)
        if m: remark = self._clean(m.group(1))

        lines = {}
        for m in _RE_LINE_TABS.finditer(html):
            n = int(m.group(1))
            lines[n] = [self._clean(m.group(2)), []]

        for m in _RE_EPISODE_UL.finditer(html):
            n = int(m.group(1))
            if n not in lines: continue
            for a in _RE_EPISODE_A.finditer(m.group(2)):
                ep_name = self._clean(a.group(1))
                ep_url = a.group(2)
                lines[n][1].append((ep_name, ep_url))

        play_from, play_url = [], []
        for n in sorted(lines.keys()):
            line_name, eps = lines[n]
            if not eps: continue
            play_from.append(line_name)
            play_url.append("#".join("%s$%s" % (ep, u) for ep, u in eps))

        if not play_from: return {"list": []}
        
        # 把类型、地区、年份合并到 vod_remarks 或者 vod_content 顶部，让 TVBox 识别
        full_remarks = remark
        if type_tags: full_remarks += " | " + type_tags
        if area_year: full_remarks += " | " + area_year

        return {"list": [{
            "vod_id": vod_id, "vod_name": name, "vod_pic": pic,
            "vod_content": content, "vod_actor": actor, "vod_director": director,
            "vod_remarks": full_remarks,
            "vod_play_from": "$$$".join(play_from), "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        
        # 默认开启直链解析（秒开）
        direct = self._try_direct_m3u8(play_page)
        if direct:
            self.log("  => 极速直链: %s" % direct[:160])
            return {
                "parse": 0, "playUrl": "", "url": direct,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }

        # 解析失败则兜底嗅探
        self.log("  => 直链失败，转为 parse:1 嗅探")
        return {
            "parse": 1, "playUrl": "", "url": play_page,
            "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
        }

    def _try_direct_m3u8(self, play_page):
        m = _RE_PLAY_PATH.search(play_page)
        if not m: return ""
        vid, line_idx, ep_idx = m.group(1), int(m.group(2)), int(m.group(3))

        ts = int(time.time())
        key = ((ts * (ts % 0x10) % 0x5fb) + (ts * (ts % 0x20)) + 0x3020d + ts * (ts % 0x40))
        url = "%s/gpyj/%s&pid=%d&url=%d-%d&t=%d&key=%d" % (
            self.site_url, vid, line_idx, line_idx, ep_idx, ts, key)

        try:
            rsp = self.fetch(url, headers={
                "User-Agent": UA, "Referer": play_page, "X-Requested-With": "XMLHttpRequest",
            }, timeout=8)  # 缩短超时，加快响应
            raw = (rsp.text or "").strip()
        except Exception as e:
            return ""

        if not raw or len(raw) % 2 != 0: return ""

        try:
            half = len(raw) // 2
            out = []
            for i in range(0, len(raw), 2):
                b = int(raw[i:i + 2], 16)
                b = (b ^ 0x100000) - 0x367 - (half - 1) * (i // 2)
                b = b % 256
                out.insert(0, chr(b))
            final_url = "".join(out)
        except Exception:
            return ""

        if not final_url.startswith("http"): return ""
        if ".m3u8" not in final_url.lower() and ".mp4" not in final_url.lower(): return ""

        return final_url

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url

    def manualVideoCheck(self): return False
    def destroy(self): pass
    def close(self): self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
