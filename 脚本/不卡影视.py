# coding=utf-8
"""
不卡影视 bukayingshi.com | TVBox Python 爬虫（修正版）
网站结构：
  - 分类 /buka/{1-5}.html，翻页 /buka/{type}-{page}.html
  - 筛选 /vodshow/{type}-{area}-{sort}-{class}-{lang}---{page}---{year}.html
  - 搜索 /vodsearch/{kw}----------{page}---.html
  - 详情 /ying/{id}.html，剧集按 data-source 分块 -> /shi/{id}-{sid}-{nid}.html
  - 播放 player_aaaa.url 是 share 页；请求 share 页提取 var main 的 m3u8，
    拼上 share 页 origin，直出
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
                adapter = _rq.adapters.HTTPAdapter(
                    pool_connections=10, pool_maxsize=10, max_retries=0)
                self._session.mount('https://', adapter)
                self._session.mount('http://', adapter)
            return self._session

        def fetch(self, url, headers=None, **kw):
            timeout = kw.pop('timeout', 15)
            r = self._sess.get(url, headers=headers, timeout=timeout, **kw)
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[bukayingshi]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.bukayingshi.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/static/images/logo.jpg"
INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "5", "type_name": "短剧"},
]

_AREAS = [
    ("全部", ""), ("内地", "内地"), ("韩国", "韩国"), ("香港", "香港"),
    ("台湾", "台湾"), ("日本", "日本"), ("美国", "美国"), ("泰国", "泰国"),
    ("英国", "英国"), ("新加坡", "新加坡"), ("其他", "其他"),
]
_LANGS = [
    ("全部", ""), ("国语", "国语"), ("英语", "英语"), ("粤语", "粤语"),
    ("闽南语", "闽南语"), ("韩语", "韩语"), ("日语", "日语"), ("其它", "其它"),
]
_YEARS = [("全部", "")] + [(str(y), str(y)) for y in range(2026, 2003, -1)]
_SORTS = [("最新", "time"), ("热门", "hits"), ("评分", "score")]

_CLASS_MAP = {
    "1": ["全部", "喜剧", "爱情", "动作", "科幻", "恐怖", "剧情", "战争",
          "警匪", "犯罪", "动画", "奇幻", "武侠", "冒险", "枪战", "悬疑",
          "惊悚", "经典", "青春", "文艺", "微电影", "纪录片", "预告片"],
    "2": ["全部", "古装", "战争", "青春偶像", "喜剧", "家庭", "犯罪", "动作",
          "奇幻", "剧情", "历史", "经典", "乡村", "情景", "商战", "网剧", "其他"],
    "3": ["全部", "真人秀", "脱口秀", "国产综艺", "喜剧", "晚会", "综艺",
          "音乐", "纪录", "游戏", "生活", "港台综艺", "日韩综艺", "剧情",
          "文化", "相声", "情感", "悬疑", "欧美综艺", "美食", "竞技"],
    "4": ["全部", "动画", "冒险", "喜剧", "奇幻", "剧情", "科幻", "动作",
          "儿童", "悬疑", "都市", "家庭", "国漫", "日常", "爱情", "玄幻",
          "日漫", "音乐", "治愈", "短片", "古风", "犯罪", "武侠", "运动", "校园"],
    "5": ["全部", "AI漫剧", "短剧", "剧情", "爱情", "爽文", "古装", "短片",
          "悬疑", "喜剧", "奇幻", "都市", "玄幻", "犯罪", "家庭", "穿越",
          "惊悚", "武侠", "科幻", "动作", "冒险", "恐怖", "青春", "历史"],
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    FILTERS[tid] = [
        {"key": "class", "name": "类型",
         "value": [{"n": x, "v": "" if x == "全部" else x}
                   for x in _CLASS_MAP.get(tid, ["全部"])]},
        {"key": "area", "name": "地区",
         "value": [{"n": n, "v": v} for n, v in _AREAS]},
        {"key": "lang", "name": "语言",
         "value": [{"n": n, "v": v} for n, v in _LANGS]},
        {"key": "year", "name": "年份",
         "value": [{"n": n, "v": v} for n, v in _YEARS]},
        {"key": "sort", "name": "排序",
         "value": [{"n": n, "v": v} for n, v in _SORTS]},
    ]


# ============ 正则（按真实源码修正） ============

# 卡片：a 标签 href=/ying/xx.html，class 里含 video-item，img 有 src + alt
_RE_VIDEO_ITEM = re.compile(
    r'<a\s+href="(/ying/\d+\.html)"[^>]*class="[^"]*video-item[^"]*"[^>]*>'
    r'[\s\S]*?<img[^>]*?src="([^"]*)"[^>]*?alt="([^"]*)"',
    re.S | re.I)

# 搜索卡片：href 和 class 顺序不定，分两个分支
_RE_SEARCH_ITEM = re.compile(
    r'<a[^>]*class="[^"]*search_result_list_item[^"]*"[^>]*href="(/ying/\d+\.html)"[^>]*>'
    r'([\s\S]*?)</a>',
    re.S | re.I)
_RE_SEARCH_ITEM2 = re.compile(
    r'<a[^>]*href="(/ying/\d+\.html)"[^>]*class="[^"]*search_result_list_item[^"]*"[^>]*>'
    r'([\s\S]*?)</a>',
    re.S | re.I)
_RE_SEARCH_IMG = re.compile(r'<img[^>]*?src="([^"]*)"', re.I)
_RE_SEARCH_TITLE = re.compile(
    r'search_result_list_item_content_title"[^>]*>([^<]*)<', re.I)
_RE_SEARCH_TAG = re.compile(
    r'search_result_list_item_content_tag"[^>]*>([^<]*)<', re.I)

# 详情
_RE_H1 = re.compile(
    r'<h1[^>]*class="[^"]*font-bold text-2xl[^"]*"[^>]*>([^<]*)</h1>', re.I)
_RE_DETAIL_PIC = re.compile(r'<img\s+alt="[^"]*"\s+src="([^"]+)"', re.I)
_RE_A_TAG = re.compile(r'<a[^>]*>([^<]*)</a>', re.I)

# 元信息：逐个 video_appraise_row 块（用下一个 row 或分界符作为终点）
_RE_ROW_ONE = re.compile(
    r'<div class="video_appraise_row"[^>]*>'
    r'([\s\S]*?)'
    r'(?=<div class="video_appraise_row"|<div class="el-divider|</div>\s*</div>\s*<div class="mx-10)',
    re.S | re.I)
_RE_ROW_TITLE = re.compile(
    r'video_appraise_title font-bold"[^>]*>([^<]*)</span>', re.I)

# 简介
_RE_SHORT_DESC = re.compile(
    r'<span class="video-description-short">([\s\S]*?)</span>', re.I)

# 线路名：detail_line_ite 块，data-source -> 名字
_RE_LINE_BLOCK = re.compile(
    r'<div[^>]*class="[^"]*detail_line_ite[^"]*"[^>]*data-source="(\d+)"[^>]*>'
    r'[\s\S]*?<div[^>]*class="[^"]*bg-\[#(?:a3d5dc|e3e8e8)\][^"]*"[^>]*>([^<]*)</div>',
    re.S | re.I)

# 剧集块：每个线路一个 video_play_channel_list
_RE_CHANNEL_BLOCK = re.compile(
    r'<div[^>]*class="[^"]*video_play_channel_list[^"]*"[^>]*data-source="(\d+)"[^>]*>'
    r'([\s\S]*?)</div>\s*(?=<div[^>]*class="[^"]*video_play_channel_list|</div>\s*<div class="recommend_video)',
    re.S | re.I)

# 剧集：某块内的 episode-item
_RE_EPISODE_IN_BLOCK = re.compile(
    r'<a[^>]*href="(/shi/\d+-\d+-\d+\.html)"[^>]*class="[^"]*episode-item[^"]*"'
    r'([^>]*)>',
    re.S | re.I)
_RE_EP_NAME_ATTR = re.compile(r'data-episode-name="([^"]*)"', re.I)

# 兜底：直接全局扫 episode-item（当分块失败时）
_RE_EPISODE = re.compile(
    r'<a[^>]*href="(/shi/\d+-\d+-\d+\.html)"[^>]*class="[^"]*episode-item[^"]*"([^>]*)>',
    re.S | re.I)

# player_aaaa：以 </script> 为边界
_RE_PLAYER_AAAA = re.compile(
    r'var\s+player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', re.S | re.I)

# share 页 var main
_RE_SHARE_MAIN = re.compile(
    r'var\s+main\s*=\s*["\']([^"\']+?\.m3u8[^"\']*)["\']', re.I)
_RE_M3U8_ANY = re.compile(
    r'["\']([^"\']+?\.m3u8[^"\']*)["\']', re.I)

_RE_TAIL_PAGE = re.compile(
    r'href="/buka/\d+-(\d+)\.html"[^>]*>\s*<button[^>]*>\s*<span[^>]*>尾页', re.I)
_RE_PAGE_INFO = re.compile(r'<span>(\d+)/(\d+)</span>')


class Spider(Spider):

    def getName(self):
        return "不卡影视"

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
        self._play_cache = {}

    def _fetch(self, url, timeout=20, headers=None):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            if hasattr(rsp, "text"):
                return rsp.text or ""
            if hasattr(rsp, "content"):
                return rsp.content.decode("utf-8", "ignore")
            return str(rsp)
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self.site_url + url
        return urllib.parse.urljoin(self.site_url + "/", url)

    def _clean(self, s):
        if not s:
            return ""
        s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ")
              .replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n{2,}", "\n", s)
        return s.strip()

    def _parse_video_items(self, html):
        out = []
        seen = set()
        for m in _RE_VIDEO_ITEM.finditer(html):
            href, pic, alt = m.group(1), m.group(2), m.group(3)
            if href in seen:
                continue
            seen.add(href)
            out.append({
                "vod_id": href,
                "vod_name": self._clean(alt)[:120],
                "vod_pic": self._fix_url(pic) or DEFAULT_PIC,
                "vod_remarks": "",
            })
        return out

    def _parse_search_items(self, html):
        out = []
        seen = set()
        results = list(_RE_SEARCH_ITEM.finditer(html)) + \
                  list(_RE_SEARCH_ITEM2.finditer(html))
        for m in results:
            href = m.group(1)
            block = m.group(2)
            if href in seen:
                continue
            seen.add(href)
            mi = _RE_SEARCH_IMG.search(block)
            pic = self._fix_url(mi.group(1)) if mi else DEFAULT_PIC
            mt = _RE_SEARCH_TITLE.search(block)
            name = self._clean(mt.group(1)) if mt else ""
            mtg = _RE_SEARCH_TAG.search(block)
            remarks = self._clean(mtg.group(1)) if mtg else ""
            out.append({
                "vod_id": href,
                "vod_name": name,
                "vod_pic": pic or DEFAULT_PIC,
                "vod_remarks": remarks,
            })
        return out

    def _page_count(self, html):
        m = _RE_TAIL_PAGE.search(html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        m = _RE_PAGE_INFO.search(html)
        if m:
            try:
                return int(m.group(2))
            except Exception:
                pass
        return 1

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html = self._fetch(self.site_url + "/")
        return {"list": self._parse_video_items(html)}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        def _v(k):
            v = extend.get(k)
            if v in ("", None, "全部"):
                return ""
            return v

        area = _v("area")
        lang = _v("lang")
        cls = _v("class")
        year = _v("year")
        sort = _v("sort") or ""

        has_filter = bool(area or lang or cls or year or sort)

        if has_filter:
            # 真实 12 段顺序：
            # type - area - sort - class - lang - 空 - 空 - 空 - page - 空 - 空 - year
            seg = [
                tid,
                urllib.parse.quote(area) if area else "",
                sort or "",
                urllib.parse.quote(cls) if cls else "",
                urllib.parse.quote(lang) if lang else "",
                "",
                "",
                "",
                str(page) if page > 1 else "",
                "",
                "",
                year or "",
            ]
            path = "-".join(seg)
            url = "%s/vodshow/%s.html" % (self.site_url, path)
        else:
            # 无筛选走 buka 列表
            if page > 1:
                url = "%s/buka/%s-%d.html" % (self.site_url, tid, page)
            else:
                url = "%s/buka/%s.html" % (self.site_url, tid)

        self.log("category: %s" % url)
        html = self._fetch(url)
        videos = self._parse_video_items(html)
        pagecount = self._page_count(html)

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": pagecount * 24,
        }

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        kw = urllib.parse.quote(key)
        url = "%s/vodsearch/%s----------%d---.html" % (self.site_url, kw, page)
        self.log("search: %s" % url)
        html = self._fetch(url)
        videos = self._parse_search_items(html)
        if not videos:
            videos = self._parse_video_items(html)
        return {
            "list": videos,
            "page": page,
            "pagecount": self._page_count(html),
            "limit": 24,
            "total": 999,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)
        self.log("detail: %s" % url)

        html = self._fetch(url)
        if not html:
            return {"list": []}

        # 名称
        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m2 = re.search(r"<title>《(.*?)》", html)
            if m2:
                name = self._clean(m2.group(1))
        name = name or vod_id

        # 封面
        pic = DEFAULT_PIC
        m = _RE_DETAIL_PIC.search(html)
        if m:
            pic = self._fix_url(m.group(1))

        # 元信息：逐个 row 解析
        director = actor = area = lang = year = remarks = ""
        for mm in _RE_ROW_ONE.finditer(html):
            block = mm.group(1)
            mt = _RE_ROW_TITLE.search(block)
            if not mt:
                continue
            key = self._clean(mt.group(1))
            links = _RE_A_TAG.findall(block)
            if links:
                val = ", ".join(self._clean(x) for x in links if self._clean(x))
            else:
                rest = block[mt.end():]
                val = self._clean(rest)
            k = key.replace(":", "").replace("：", "").strip()
            if k == "导演":
                director = val
            elif k in ("演员", "主演"):
                actor = val
            elif k == "地区":
                area = val
            elif k == "语言":
                lang = val
            elif k == "年份":
                year = val
            elif k == "备注":
                remarks = val

        # 语言合并到地区，保证 TVBox 显示
        if lang and area:
            area = "%s · %s" % (area, lang)
        elif lang and not area:
            area = lang

        # 简介（加前缀）
        content = ""
        m = _RE_SHORT_DESC.search(html)
        if m:
            content = self._clean(m.group(1))
        if not content:
            m = re.search(r'name="description"\s+content="([^"]*)"', html)
            if m:
                content = self._clean(m.group(1))
        content = (INTRO_PREFIX + "\n" + content) if content else INTRO_PREFIX

        # 线路名：source -> name
        line_names = {}
        for m in _RE_LINE_BLOCK.finditer(html):
            src = m.group(1)
            nm = self._clean(m.group(2))
            if nm:
                line_names[src] = nm

        # 剧集：按线路分块
        channels = []  # [(source, name, [(ep_name, href), ...])]
        for m in _RE_CHANNEL_BLOCK.finditer(html):
            src = m.group(1)
            block = m.group(2)
            eps = []
            for mm in _RE_EPISODE_IN_BLOCK.finditer(block):
                href = mm.group(1)
                attrs = mm.group(2) or ""
                ep_name = ""
                mn = _RE_EP_NAME_ATTR.search(attrs)
                if mn:
                    ep_name = self._clean(mn.group(1))
                if not ep_name:
                    ep_name = "第%02d集" % (len(eps) + 1)
                eps.append((ep_name, self._fix_url(href)))
            if eps:
                channels.append((src, line_names.get(src, "线路%s" % src), eps))

        # 兜底：如果分块失败，用旧的全局正则
        if not channels:
            eps = []
            for m in _RE_EPISODE.finditer(html):
                href = m.group(1)
                attrs = m.group(2) or ""
                ep_name = ""
                mn = _RE_EP_NAME_ATTR.search(attrs)
                if mn:
                    ep_name = self._clean(mn.group(1))
                if not ep_name:
                    ep_name = "第%02d集" % (len(eps) + 1)
                eps.append((ep_name, self._fix_url(href)))
            if eps:
                channels.append(("1", "buka", eps))

        self.log("channels: %s" % [(s, n, len(e)) for s, n, e in channels])

        if not channels:
            return {"list": []}

        # 排序
        channels.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 999)

        play_from = "$$$".join(nm for _, nm, _ in channels)
        play_url = "$$$".join(
            "#".join("%s$%s" % (n, h) for n, h in eps)
            for _, _, eps in channels
        )

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_area": area,
            "vod_lang": lang,
            "vod_year": year,
            "vod_remarks": remarks,
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }]}

    # ---------- share 页 -> 真 m3u8 ----------
    def _resolve_share_url(self, share_url):
        try:
            rsp = self.fetch(share_url, headers={
                "User-Agent": UA,
                "Referer": self.site_url + "/",
            }, timeout=15)
        except Exception as e:
            self.log("share fetch fail: %s" % e)
            return ""

        text = ""
        if hasattr(rsp, "text"):
            text = rsp.text or ""
        elif hasattr(rsp, "content"):
            text = rsp.content.decode("utf-8", "ignore")

        if not text:
            return ""
        if "#EXTM3U" in text:
            return share_url

        m = _RE_SHARE_MAIN.search(text)
        if not m:
            m = _RE_M3U8_ANY.search(text)
        if not m:
            self.log("share 页里没有找到 m3u8")
            return ""

        m3u8 = m.group(1)
        # 去掉 JSON 转义
        m3u8 = m3u8.replace("\\/", "/").replace("&amp;", "&").replace("\\\\", "\\")
        if m3u8.startswith("//"):
            m3u8 = "https:" + m3u8
        elif m3u8.startswith("/"):
            parsed = urllib.parse.urlparse(share_url)
            m3u8 = "%s://%s%s" % (parsed.scheme, parsed.netloc, m3u8)
        elif not m3u8.startswith("http"):
            m3u8 = urllib.parse.urljoin(share_url, m3u8)

        self.log("resolve m3u8: %s" % m3u8[:200])
        return m3u8

    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)
        share_url = ""
        m = _RE_PLAYER_AAAA.search(html)
        self.log("player_aaaa match: %s" % ("YES" if m else "NONE"))
        if m:
            raw = m.group(1)
            try:
                data = json.loads(raw)
                share_url = data.get("url", "") or ""
            except Exception as e:
                self.log("player_aaaa json fail: %s" % e)
                m2 = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
                if m2:
                    share_url = m2.group(1)
        if share_url:
            share_url = share_url.replace("\\/", "/").replace("&amp;", "&")

        if share_url:
            self.log("share: %s" % share_url[:160])
            real_m3u8 = self._resolve_share_url(share_url)
            if real_m3u8:
                res = {
                    "parse": 0,
                    "playUrl": "",
                    "url": real_m3u8,
                    "header": {"User-Agent": UA},
                }
                self._play_cache[play_page] = (now, res)
                return res

        # 兜底
        res = {
            "parse": 1,
            "playUrl": "",
            "url": play_page,
            "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
        }
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param):
        try:
            url = ""
            if isinstance(param, dict):
                url = param.get("url", "")
            else:
                for pair in str(param).split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k == "url":
                            url = v
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = urllib.parse.unquote(url) if "%" in url else url
            url = self._fix_url(url)
            rsp = self.fetch(url, headers={
                "User-Agent": UA, "Referer": self.site_url + "/"}, timeout=15)
            content = rsp.content
            ctype = rsp.headers.get("Content-Type", "image/jpeg")
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return [200, ctype, content, ""]
        except Exception:
            return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        return ".m3u8" in url or ".mp4" in url or url.startswith("http")

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
