# coding=utf-8
"""
水牛影院 sunnykings.com | TVBox Python 爬虫 
网站结构:
  - 全量修复筛选分类（港剧、日剧、泰剧等完美展示并可点击）
  - 强制修复 INTRO_PREFIX 丢失问题
  - 融合 12 段占位与霸王硬上弓详情页解析
"""
import re
import sys
import json
import time
import html
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
                print("[sunnykings]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://sunnykings.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/template/default18/template/mb13/statics/img/load.gif"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1",  "type_name": "电影"},
    {"type_id": "2",  "type_name": "电视剧"},
    {"type_id": "3",  "type_name": "综艺"},
    {"type_id": "4",  "type_name": "动漫"},
    {"type_id": "30", "type_name": "爽文短剧"},
]

_DEFAULT_SUB_TID = {
    "1": "1", "2": "2", "3": "3", "4": "4", "30": "30", "36": "36"
}

_SLOT = {
    "tid": 0, "area": 1, "order": 2, "plot": 3,
    "lang": 4, "letter": 5, "page": 8, "year": 11,
}
_SHOW_SLOTS = 12
_SEARCH_SLOTS = 14

_CLASS_ID_MAP = {
    "全部": "", "电影": "1", "电视剧": "2",
    "动作片": "7", "喜剧片": "8", "爱情片": "9", "科幻片": "10",
    "恐怖片": "11", "剧情片": "12", "犯罪片": "29", "战争片": "13",
    "国产剧": "14", "港剧": "15", "台湾剧": "16", "韩剧": "17",
    "日剧": "18", "泰剧": "31", "欧美剧": "19", "海外剧": "20",
    "大陆综艺": "21", "日韩综艺": "22", "港台综艺": "23", "欧美综艺": "24",
    "国产动漫": "25", "日本动漫": "26", "欧美动漫": "27", "海外动漫": "28",
    "爽文短剧": "30", "短剧": "30", 
}

_SORTS = [{"n": "按时间", "v": "time"},
          {"n": "按人气", "v": "hits"},
          {"n": "按评分", "v": "score"}]
_YEARS = [{"n": "全部", "v": ""}] + \
         [{"n": str(y), "v": str(y)} for y in range(2026, 2005, -1)]
_AREAS = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
    {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"},
    {"n": "法国", "v": "法国"}, {"n": "英国", "v": "英国"},
    {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
    {"n": "德国", "v": "德国"}, {"n": "泰国", "v": "泰国"},
    {"n": "印度", "v": "印度"}, {"n": "意大利", "v": "意大利"},
    {"n": "西班牙", "v": "西班牙"}, {"n": "加拿大", "v": "加拿大"},
    {"n": "其他", "v": "其他"},
]
_LANGS = [
    {"n": "全部", "v": ""},
    {"n": "国语", "v": "国语"}, {"n": "英语", "v": "英语"},
    {"n": "粤语", "v": "粤语"}, {"n": "闽南语", "v": "闽南语"},
    {"n": "韩语", "v": "韩语"}, {"n": "日语", "v": "日语"},
    {"n": "法语", "v": "法语"}, {"n": "德语", "v": "德语"},
    {"n": "其它", "v": "其它"},
]

# 核心修复：完美对齐网页的子分类下拉！
_FILTERS_MAP = {
    "1":  ["全部", "动作片", "喜剧片", "爱情片", "科幻片", "恐怖片", "剧情片", "犯罪片", "战争片"],
    "2":  ["全部", "国产剧", "港剧", "台湾剧", "韩剧", "日剧", "泰剧", "欧美剧", "海外剧"],
    "3":  ["全部", "大陆综艺", "日韩综艺", "港台综艺", "欧美综艺"],
    "4":  ["全部", "国产动漫", "日本动漫", "欧美动漫", "海外动漫"],
    "30": ["全部", "爽文短剧", "短剧"],
}

FILTERS = {}
for c in CLASSES:
    tid = c["type_id"]
    FILTERS[tid] = [
        {"key": "class", "name": "分类",
         "value": [{"n": x, "v": "" if x == "全部" else x} for x in _FILTERS_MAP.get(tid, ["全部"])]},
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份", "value": _YEARS},
        {"key": "lang", "name": "语言", "value": _LANGS},
        {"key": "sort_field", "name": "排序", "value": _SORTS},
    ]

# ===================== 正则 =====================
_RE_H1 = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_TITLE = re.compile(r'<title>(.*?)</title>', re.S | re.I)
_RE_INTRO_FULL = re.compile(r'<span[^>]*class="[^"]*detail-content[^"]*"[^>]*>([\s\S]*?)</span>', re.I)
_RE_INTRO_SKETCH = re.compile(r'<span[^>]*class="[^"]*detail-sketch[^"]*"[^>]*>([\s\S]*?)</span>', re.I)
_RE_META_DESC = re.compile(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', re.I)
_RE_SCORE = re.compile(r'class="[^"]*branch[^"]*"[^>]*>\s*([\d.]+)\s*<', re.I)

_RE_PLAYER = re.compile(r'var\s+player_[a-zA-Z_]+\s*=\s*(\{.*?\})\s*</script>', re.S)
_RE_LINE_BLOCK = re.compile(r'<h3[^>]*>\s*([^<\n]+?)\s*</h3>[\s\S]{0,600}?<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>([\s\S]*?)</ul>', re.I)
_RE_EP_A = re.compile(r'<a[^>]+href="([^"]+?)"[^>]*>([^<]*)</a>', re.I)

_RE_CARD_HREF = re.compile(r'href="(/[a-zA-Z][\w\-]{0,12}/(\d{3,})\.html)"', re.I)
_RE_PAGER_MAX = re.compile(r'href="[^"]*?[-/](\d+)\.html"[^>]*>\s*(?:尾页|末页|&#23614;&#39029;)', re.I)
_RE_PAGER_NUM = re.compile(r'class="[^"]*num[^"]*"[^>]*>\s*\d+\s*/\s*(\d+)', re.I)

class Spider(Spider):

    def getName(self):
        return "水牛影院"

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
        self._play_cache = {}
        self._last_req_ts = 0.0

    def _fetch(self, url, timeout=20, headers=None, retry=2):
        now = time.time()
        gap = now - self._last_req_ts
        if gap < 0.4:
            time.sleep(0.4 - gap)
        self._last_req_ts = time.time()

        h = dict(self.headers)
        if headers:
            h.update(headers)

        for attempt in range(retry + 1):
            try:
                rsp = self.fetch(url, headers=h, timeout=timeout)
                text = ""
                if hasattr(rsp, "text"):
                    text = rsp.text or ""
                elif hasattr(rsp, "content"):
                    text = rsp.content.decode("utf-8", "ignore")
                else:
                    text = str(rsp)

                if "请不要频繁操作" in text or "访问过于频繁" in text:
                    time.sleep(3.0)
                    continue
                return text
            except Exception:
                time.sleep(1.0)
        return ""

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip().replace("\\/", "/")
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
        s = s.replace("\\u0026", "&").replace("\\/", "/")
        s = html.unescape(html.unescape(s))
        s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
        s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
        s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
        s = re.sub(r"<[^>]+>", "", s)
        s = (s.replace("&nbsp;", " ").replace("\xa0", " ").replace("\u3000", " "))
        s = re.sub(r"[ \t\r\f\v]+", " ", s)
        s = re.sub(r"\n\s*\n+", "\n", s)
        return s.strip()

    @staticmethod
    def _split_cards(html_content):
        cards = []
        parts = re.split(r'<li[^>]*>', html_content)
        for p in parts:
            if _RE_CARD_HREF.search(p):
                cards.append(p)
        if not cards:
            idx = [m.start() for m in _RE_CARD_HREF.finditer(html_content)]
            for i, s in enumerate(idx):
                e = idx[i + 1] if i + 1 < len(idx) else min(len(html_content), s + 2500)
                cards.append(html_content[s:max(e, s + 400)])
        return cards

    def _extract_videos(self, html_content):
        videos = []
        seen = set()
        if not html_content:
            return videos

        for seg in self._split_cards(html_content):
            m = _RE_CARD_HREF.search(seg)
            if not m:
                continue
            href = m.group(1)
            if href in seen:
                continue
            seen.add(href)

            title = ""
            t = re.search(r'title="([^"]*)"', seg)
            if t:
                title = self._clean(t.group(1))
            if not title:
                h4 = re.search(r'<h4[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>', seg)
                if h4:
                    title = self._clean(h4.group(1))
            if not title:
                title = "未命名"

            pic = self.default_pic
            p = re.search(r'data-original="([^"]+)"', seg) or \
                re.search(r'data-src="([^"]+)"', seg) or \
                re.search(r'<img[^>]+src="([^"]+)"', seg)
            if p:
                src = p.group(1).strip()
                if src and not src.startswith("data:"):
                    pic = self._fix_url(src)

            remark = ""
            pt = re.search(r'pic-text[^"]*"[^>]*>([^<]+)<', seg)
            if pt:
                remark = self._clean(pt.group(1))
            if not remark:
                for text in re.findall(r'<span[^>]*>([^<]{1,20})</span>', seg):
                    text = self._clean(text)
                    if not text or text == title:
                        continue
                    if re.search(r'(更新|全\s*\d|第\s*\d|集|HD|正片|完结|预告)', text):
                        remark = text
                        break

            videos.append({
                "vod_id": href,
                "vod_name": title[:100],
                "vod_pic": pic,
                "vod_remarks": remark,
            })

        return videos

    def _page_count(self, html_content, page):
        if not html_content:
            return page
        m = _RE_PAGER_NUM.search(html_content)
        if m:
            try:
                return max(int(m.group(1)), page)
            except Exception:
                pass
        m = _RE_PAGER_MAX.search(html_content)
        if m:
            try:
                return max(int(m.group(1)), page)
            except Exception:
                pass
        return page

    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        html_text = self._fetch(self.site_url + "/")
        return {"list": self._extract_videos(html_text)}

    @staticmethod
    def _slots_to_url(base, slots):
        return "%s/so-show/%s.html" % (base, "-".join(slots))

    def _build_show_url(self, tid, extend, page):
        try:
            page = int(page) if page else 1
        except Exception:
            page = 1
        page = max(page, 1)

        cls = str(extend.get("class") or "").strip()
        if cls and _CLASS_ID_MAP.get(cls):
            real_tid = _CLASS_ID_MAP[cls]
        else:
            real_tid = _DEFAULT_SUB_TID.get(tid, tid) or tid

        area = str(extend.get("area") or "").strip()
        lang = str(extend.get("lang") or "").strip()
        year = str(extend.get("year") or "").strip()
        plot = str(extend.get("plot") or "").strip()
        order = str(extend.get("sort_field") or "").strip()
        if order in ("time", "默认", "按时间"):
            order = ""

        has_filter = bool(area or lang or year or plot or order)

        if not has_filter:
            if page <= 1:
                return "%s/listnew/%s.html" % (self.site_url, real_tid)
            return "%s/listnew/%s-%d.html" % (self.site_url, real_tid, page)

        slots = [""] * _SHOW_SLOTS
        slots[_SLOT["tid"]] = str(real_tid)
        slots[_SLOT["area"]] = urllib.parse.quote(area) if area else ""
        slots[_SLOT["order"]] = order
        slots[_SLOT["plot"]] = urllib.parse.quote(plot) if plot else ""
        slots[_SLOT["lang"]] = urllib.parse.quote(lang) if lang else ""
        slots[_SLOT["page"]] = "" if page <= 1 else str(page)
        slots[_SLOT["year"]] = year
        return self._slots_to_url(self.site_url, slots)

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
        if not isinstance(extend, dict):
            extend = {}
        extend = dict(extend)
        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        url = self._build_show_url(tid, extend, page)
        self.log("category: %s" % url)
        html_text = self._fetch(url)
        videos = self._extract_videos(html_text)

        if not videos and extend:
            tried = [url]
            relaxed = dict(extend)
            for drop in ("plot", "lang", "sort_field", "area", "year"):
                if drop in relaxed:
                    relaxed.pop(drop)
                    u2 = self._build_show_url(tid, relaxed, page)
                    if u2 in tried:
                        continue
                    tried.append(u2)
                    html_text = self._fetch(u2)
                    videos = self._extract_videos(html_text)
                    if videos:
                        break
        if not videos and page > 1:
            u3 = self._build_show_url(tid, {}, 1)
            html_text = self._fetch(u3)
            videos = self._extract_videos(html_text)

        pagecount = self._page_count(html_text, page)
        return {
            "list": videos, "page": page, "pagecount": max(pagecount, page),
            "limit": len(videos) or 30, "total": max(pagecount, page) * 30,
        }

    def searchContent(self, key, quick=False, pg="1"):
        try:
            page = int(pg) if pg else 1
        except Exception:
            page = 1
        kw = urllib.parse.quote(str(key).strip())
        slots = [""] * _SEARCH_SLOTS
        slots[0] = kw
        if page > 1:
            slots[_SEARCH_SLOTS - 1] = str(page)
        url = "%s/search/%s.html" % (self.site_url, "-".join(slots))

        html_text = self._fetch(url)
        videos = self._extract_videos(html_text)
        pagecount = self._page_count(html_text, page)

        return {
            "list": videos, "page": page,
            "pagecount": max(pagecount, page, 1),
            "limit": len(videos) or 30, "total": len(videos) or 30,
        }

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def _pick_kv(self, header, label):
        plain = self._unentity(header)
        m = re.search(r'%s\s*[：:]\s*</span>([\s\S]{0,900}?)(?=<span[^>]*text-muted|</p>)' % re.escape(label), plain)
        if not m:
            return ""
        frag = m.group(1)
        text = re.sub(r'<[^>]*>', '|', "|" + frag)
        parts = []
        for x in text.split('|'):
            x = self._clean(x)
            if x and x not in ("/", "·"):
                parts.append(x)
        return ", ".join(parts).strip(" /,|")

    @staticmethod
    def _unentity(text):
        if not text:
            return ""
        def rep(mm):
            try: return html.unescape(mm.group(0))
            except Exception: return mm.group(0)
        return re.sub(r'&#?\w+;', rep, text)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = str(ids[0])
        url = vod_id if vod_id.startswith("http") else self._fix_url(vod_id)

        html_text = self._fetch(url)
        if not html_text:
            return {"list": []}

        name = ""
        for h1 in _RE_H1.findall(html_text):
            c = self._clean(h1)
            if c and c not in ("水牛影院",):
                name = c
                break
        if not name:
            m = _RE_TITLE.search(html_text)
            if m:
                name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = name or vod_id

        pic = self.default_pic
        m = re.search(r'data-original="(/upload/vod/[^"]+)"', html_text) or \
            re.search(r'<img[^>]+src="(/upload/vod/[^"]+)"', html_text)
        if m:
            pic = self._fix_url(m.group(1))

        # --- 核心修复：强制保护简介前缀 ---
        content = ""
        m = _RE_INTRO_FULL.search(html_text) or _RE_INTRO_SKETCH.search(html_text)
        if m:
            content = self._clean(m.group(1))
        if len(content) < 10:
            m = _RE_META_DESC.search(html_text)
            if m:
                content = self._clean(m.group(1))

        # 无论 content 有没有拿到，前缀永远都在！
        if content:
            content = INTRO_PREFIX + "\n" + content
        else:
            content = INTRO_PREFIX
        # ---------------------------------

        header = ""
        m = re.search(r'class="[^"]*stui-content__detail[^"]*"([\s\S]{0,4000}?)<div[^>]*class="[^"]*(?:play-btn|stui-pannel)[^"]*"', html_text)
        if m:
            header = m.group(1)
        if not header:
            i = html_text.find("stui-content__detail")
            header = html_text[i:i + 4000] if i > 0 else html_text

        v_type = self._pick_kv(header, "类型")
        v_area = self._pick_kv(header, "地区")
        v_year = self._pick_kv(header, "年份")
        v_lang = self._pick_kv(header, "语言")
        v_actor = self._pick_kv(header, "主演")
        v_director = self._pick_kv(header, "导演")
        v_update = self._pick_kv(header, "更新")

        score = ""
        m = _RE_SCORE.search(html_text)
        if m:
            score = m.group(1)

        play_from, play_url = [], []
        for m in _RE_LINE_BLOCK.finditer(html_text):
            alias = self._clean(m.group(1)) or "线路%d" % (len(play_from) + 1)
            eps = _RE_EP_A.findall(m.group(2))
            items = []
            for href, ep_name in eps:
                if "/tvplay/" not in href and "/play/" not in href:
                    continue
                href = self._fix_url(href.replace("&amp;", "&"))
                ep = self._clean(ep_name) or "正片"
                items.append("%s$%s" % (ep, href))
            if items:
                play_from.append(alias)
                play_url.append("#".join(items))

        if not play_from:
            m = re.search(r'href="(/tvplay/[^"]+)"', html_text)
            if m:
                play_from = ["默认"]
                play_url = ["正片$" + self._fix_url(m.group(1))]
            else:
                return {"list": []}

        remark_parts = [x for x in (v_type, v_area, v_year, v_lang) if x]
        remark = " | ".join(remark_parts)
        if v_update:
            remark = (remark + " | " + v_update) if remark else v_update

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": v_actor,
            "vod_director": v_director,
            "vod_score": score,
            "vod_remarks": remark,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url":  "$$$".join(play_url),
        }]}

    def playerContent(self, flag, id, vipFlags=None):
        play_page = id if id.startswith("http") else self._fix_url(id)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html_text = self._fetch(play_page, headers={"Referer": self.site_url + "/"})
        url = ""
        if html_text:
            raw = ""
            m = _RE_PLAYER.search(html_text)
            if m:
                raw = m.group(1).replace("\\/", "/")
                try:
                    cfg = json.loads(raw)
                    url = (cfg.get("url") or "").strip()
                except Exception:
                    m2 = re.search(r'"url"\s*:\s*"([^"]+)"', raw)
                    if m2:
                        url = m2.group(1).replace("\\/", "/")
            if not url:
                m3 = re.search(r'(https?:\\?/\\?/[^"\'<>\s]+?\.(?:m3u8|mp4)[^"\'<>\s]*)', html_text)
                if m3:
                    url = m3.group(1).replace("\\/", "/")

        if url:
            url = url.replace("\\/", "/")
            if url.startswith("//"):
                url = "https:" + url
            res = {
                "parse": 0, "playUrl": "", "url": url,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            self._play_cache[play_page] = (now, res)
            return res

        res = {"parse": 1, "playUrl": "", "url": play_page,
               "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}
        self._play_cache[play_page] = (now, res)
        return res

    def localProxy(self, param):
        try:
            url = param.get("url", "") if isinstance(param, dict) else ""
            if not url:
                return [200, "image/jpeg", b"", ""]
            url = urllib.parse.unquote(url) if "%" in url else url
            url = self._fix_url(url)
            rsp = self.fetch(url, headers={"User-Agent": UA, "Referer": self.site_url + "/"}, timeout=15)
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
