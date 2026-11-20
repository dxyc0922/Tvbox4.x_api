# coding=utf-8
"""
两个BT影视 bttwo.life | TVBox Python 爬虫 
关键:
  - 服务端渲染；列表走 /filter?classify=N&areas=&types=&years=&tags=&sort_by=&order=&page=
  - 详情播放合一 /play/{code}，每集独立 URL
  - 选集通过 <a href="/play/xxx" data-episode="N"> 属性提取（Alpine.js 组件写法）
  - 真实 m3u8 藏于 JS 取流接口，静态 HTML 拿不到；playerContent 做多路尝试，
    拿不到则返回播放页由上层嗅探/解析
  - 播放/嗅探/代理 header 不带 Referer（CDN 拒绝携带 Referer 的分片请求）
"""
import re
import json
import html as _html
import urllib.parse

try:
    import requests as _requests
except Exception:
    _requests = None


# ===================== 全局常量 =====================
HOST = "https://www.bttwo.life"
UA = ("Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "动漫"},
]

_AREAS = [
    {"n": "全部地区", "v": ""},
    {"n": "中国", "v": "7"}, {"n": "美国", "v": "5"},
    {"n": "韩国", "v": "12"}, {"n": "日本", "v": "11"},
    {"n": "法国", "v": "6"},
]
_TYPES = [
    {"n": "全部类型", "v": ""},
    {"n": "剧情", "v": "1"}, {"n": "喜剧", "v": "5"},
    {"n": "动作", "v": "10"}, {"n": "科幻", "v": "14"},
    {"n": "悬疑", "v": "2"}, {"n": "恐怖", "v": "3"},
]
_YEARS = [
    {"n": "全部年份", "v": ""},
    {"n": "2026", "v": "1"}, {"n": "2025", "v": "3"}, {"n": "2024", "v": "4"},
]
_TAGS = [
    {"n": "全部标签", "v": ""},
    {"n": "4K", "v": "1"}, {"n": "HD", "v": "37"},
    {"n": "院线", "v": "36"}, {"n": "TC", "v": "38"},
]
_SORTS = [
    {"n": "最新上映", "v": "update_time"},
    {"n": "最受欢迎", "v": "hits"},
    {"n": "评分最高", "v": "score"},
]

FILTERS = {}
for _c in CLASSES:
    FILTERS[_c["type_id"]] = [
        {"key": "areas",   "name": "地区", "value": _AREAS},
        {"key": "types",   "name": "类型", "value": _TYPES},
        {"key": "years",   "name": "年份", "value": _YEARS},
        {"key": "tags",    "name": "标签", "value": _TAGS},
        {"key": "sort_by", "name": "排序", "value": _SORTS},
    ]


# ===================== 正则集中 =====================
_RE_CARD = re.compile(
    r'<a[^>]+href="(/play/[A-Za-z0-9]+)"[^>]*>([\s\S]{20,2000}?)</a>')
_RE_IMG_DATA_SRC = re.compile(r'<img[^>]+?data-src="([^"]+)"')
_RE_IMG_DATA_ORIG = re.compile(r'<img[^>]+?data-original="([^"]+)"')
_RE_IMG_SRC = re.compile(
    r'<img[^>]+?src="((?!/static/images/placeholder)[^"]+)"')
_RE_H3_TITLE = re.compile(r"<h3[^>]*>([^<]{2,60})</h3>")
_RE_TITLE_ATTR = re.compile(r'title="([^"]{2,60})"')
_RE_REMARK = re.compile(r"(更新至\d+集|全\d+集)")
_RE_YEAR_TAG = re.compile(r"<[^>]*>(20\d{2}|19\d{2})<")

_RE_DOC_TITLE = re.compile(r"<title[^>]*>([^<]+)</title>")
_RE_H1_TAG = re.compile(r"<h1[^>]*>([\s\S]*?)</h1>", re.I)
_RE_OG_IMAGE = re.compile(r'property="og:image"\s+content="([^"]+)"', re.I)
_RE_DATA_POSTER = re.compile(r'data-poster="([^"]+)"', re.I)
_RE_POSTER_IMG = re.compile(
    r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*(?:poster|thumb|cover)[^"]*"', re.I)
_RE_OG_DESC = re.compile(r'property="og:description"\s+content="([^"]+)"', re.I)
_RE_META_DESC = re.compile(r'name="description"\s+content="([^"]+)"', re.I)

_RE_EPISODE_A = re.compile(
    r'<a[^>]*?href="(/play/[A-Za-z0-9]+)"[^>]*?data-episode="(\d+)"')
_RE_PLAY_CODE = re.compile(r"/play/([A-Za-z0-9]+)")

_RE_M3U8_RAW = re.compile(r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)')
_RE_M3U8_JSON = re.compile(r'"(https?://[^"]+\.m3u8[^"]*)"')
_RE_DATAID = re.compile(r'dataid="(\d+)"')

_RE_PAGECOUNT = re.compile(r"共\s*(\d+)\s*页")
_RE_PAGE_NUM = re.compile(r"[?&]page=(\d+)")


class Spider:

    def __init__(self):
        self.site = HOST
        self.name = "两个BT影视"
        self.header = {
            "User-Agent": UA,
            "Referer": self.site + "/",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.s = self.session = self.sess = _requests.Session() if _requests else None
        self._extend = {}

    def getName(self):
        return self.name

    def init(self, extend=""):
        self._extend = {}
        if isinstance(extend, dict):
            self._extend = extend
        elif isinstance(extend, str) and extend.strip():
            try:
                e = json.loads(extend)
                if isinstance(e, dict):
                    self._extend = e
            except Exception:
                pass
        self.log("init: site=%s" % self.site)

    def getDependence(self):
        return []

    def action(self, action):
        return {}

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def log(self, *a, **kw):
        try:
            print("[bttwo]", *a)
        except Exception:
            pass

    def _get(self, url, referer=None, timeout=12):
        h = dict(self.header)
        if referer:
            h["Referer"] = referer
        if self.s is not None:
            try:
                r = self.s.get(url, headers=h, timeout=timeout, allow_redirects=True)
                if r.status_code < 400:
                    r.encoding = "utf-8"
                    return r.text or ""
            except Exception as e:
                self.log("session.get fail %s: %s" % (url, e))
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "ignore")
        except Exception as e:
            self.log("urlopen fail %s: %s" % (url, e))
            return ""

    def _u(self, u):
        if not u:
            return u
        u = u.strip().replace("&amp;", "&")
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http"):
            return u
        if u.startswith("/"):
            m = re.match(r"(https?://[^/]+)", self.site)
            return (m.group(1) if m else self.site) + u
        return self.site.rstrip("/") + "/" + u.lstrip("/")

    def _un(self, s):
        return _html.unescape(s) if s else ""

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

    def homeContent(self, filter=False):
        vod_list = []
        try:
            html = self._get(self.site + "/filter?classify=1")
            vod_list = self._items(html)[:24]
        except Exception as e:
            self.log("homeContent list fail: %s" % e)
        return {"class": CLASSES, "filters": FILTERS, "list": vod_list}

    def homeVideoContent(self):
        try:
            html = self._get(self.site + "/filter?classify=1")
            return {"list": self._items(html)[:24]}
        except Exception as e:
            self.log("homeVideoContent fail: %s" % e)
            return {"list": []}

    def _items(self, html, base=None):
        out = []
        seen = set()
        if not html:
            return out

        for m in _RE_CARD.finditer(html):
            href, block = m.group(1), m.group(2)
            if href in seen:
                continue
            seen.add(href)

            pic = ""
            im = _RE_IMG_DATA_SRC.search(block) or _RE_IMG_DATA_ORIG.search(block)
            if im:
                pic = self._u(im.group(1))
            else:
                im = _RE_IMG_SRC.search(block)
                pic = self._u(im.group(1)) if im else ""
            if pic and "placeholder" in pic.lower():
                pic = ""

            name = ""
            hm = _RE_H3_TITLE.search(block)
            if hm:
                name = self._un(hm.group(1)).strip()
            else:
                tm = _RE_TITLE_ATTR.search(block)
                if tm:
                    name = tm.group(1)
                else:
                    txt = re.sub(r"<[^>]+>", "|", block)
                    parts = [p.strip() for p in txt.split("|") if p.strip()]
                    for p in parts:
                        p = self._un(p)
                        if p.lower() in ("4k", "hd", "tc", "vip", "院线"):
                            continue
                        if 2 <= len(p) <= 40 and not re.match(
                                r"^[\d.\s分集全更新至]+$", p):
                            name = p
                            break

            block_noimg = re.sub(r"<img[^>]*>", "", block)
            remark = ""
            rm = _RE_REMARK.search(block_noimg)
            if rm:
                remark = rm.group(1)
            else:
                ym = _RE_YEAR_TAG.search(block_noimg)
                remark = ym.group(1) if ym else ""

            out.append({
                "vod_id":      href,
                "vod_name":    name,
                "vod_pic":     pic,
                "vod_remarks": remark,
            })
        return out

    def _cat_url(self, tid, pg, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        if pg < 1:
            pg = 1
        q = {"classify": str(tid), "page": str(pg), "order": "desc"}
        ext = extend or {}
        for k in ("areas", "types", "years", "tags"):
            v = str(ext.get(k, "") or "").strip()
            if v:
                q[k] = v
        sb = str(ext.get("sort_by", "") or "").strip()
        q["sort_by"] = sb if sb else "update_time"
        return self.site + "/filter?" + urllib.parse.urlencode(q)

    def categoryContent(self, tid, pg=1, filter=False, extend=None):
        try:
            pg = int(pg)
        except Exception:
            pg = 1
        ext = {}
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(filter, dict):
            ext = filter

        url = self._cat_url(tid, pg, ext)
        self.log("category: %s" % url)
        html = self._get(url)
        if not html:
            return {"list": [], "page": pg, "pagecount": 1,
                    "limit": 24, "total": 0}

        vod_list = self._items(html)

        pagecount = pg
        m = _RE_PAGECOUNT.search(html)
        if m:
            pagecount = int(m.group(1))
        else:
            pages = _RE_PAGE_NUM.findall(html)
            if pages:
                pagecount = max(pagecount, max(int(p) for p in pages))
        if re.search(r"[?&]page=%d\b" % (pg + 1), html):
            pagecount = max(pagecount, pg + 1)

        self.log("  最终: %d 条, 总页数: %d" % (len(vod_list), pagecount))
        return {
            "list":      vod_list,
            "page":      pg,
            "pagecount": pagecount,
            "limit":     24,
            "total":     pagecount * 24,
        }

    def searchContent(self, key, quick=False, pg="1"):
        url = self.site + "/search?q=" + urllib.parse.quote(str(key))
        self.log("search: %s" % url)
        html = self._get(url)
        if not html:
            return {"list": []}
        return {"list": self._items(html)}

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        vid = str(vid or "").strip()
        url = self._u(vid)
        self.log("detail: %s" % url)

        html = self._get(url)
        if not html:
            return {"list": []}

        title = ""
        tm = _RE_DOC_TITLE.search(html)
        if tm:
            title = self._un(tm.group(1)).strip()
            title = re.sub(r"\s*-\s*第\d+集.*$", "", title)
            title = re.sub(r"\s*-\s*两个BT影视\s*$", "", title)
        if not title:
            h1 = _RE_H1_TAG.search(html)
            if h1:
                title = self._clean(h1.group(1))
        title = title or vid

        pic = ""
        for pat in (_RE_OG_IMAGE, _RE_DATA_POSTER, _RE_POSTER_IMG):
            im = pat.search(html)
            if im:
                p = self._u(im.group(1))
                if p and "placeholder" not in p.lower() and "loading" not in p.lower():
                    pic = p
                    break

        desc = ""
        dm = _RE_OG_DESC.search(html) or _RE_META_DESC.search(html)
        if dm:
            desc = self._clean(dm.group(1))
        desc = INTRO_PREFIX + "\n" + desc if desc else INTRO_PREFIX

        eps = []
        seen = set()
        cur_code_m = _RE_PLAY_CODE.search(url)
        cur_code = cur_code_m.group(1) if cur_code_m else ""
        for m in _RE_EPISODE_A.finditer(html):
            href, num = m.group(1), int(m.group(2))
            code = href.split("/")[-1]
            if code in seen or code == cur_code:
                continue
            seen.add(code)
            eps.append((num, "第%d集$%s" % (num, self._u(href))))

        cm = re.search(r"第(\d+)集", self._un(tm.group(1)) if tm else "")
        cur_num = int(cm.group(1)) if cm else 1
        eps.append((cur_num, "第%d集$%s" % (cur_num, url)))
        eps.sort(key=lambda x: x[0])

        play_url = "#".join(e for _, e in eps)
        self.log("  选集: %d 条" % len(eps))

        return {"list": [{
            "vod_id":        vid,
            "vod_name":      title,
            "vod_pic":       pic,
            "vod_content":   desc,
            "vod_play_from": "两个BT",
            "vod_play_url":  play_url,
        }]}

    def _extract_m3u8(self, html, page_url):
        if not html:
            return ""

        m = _RE_M3U8_RAW.search(html)
        if m:
            return m.group(1)

        for var in ("videoUrl", "playUrl", "source", "src", "url", "m3u8", "now"):
            m = re.search(
                r'var\s+%s\s*=\s*["\']([^"\']+\.m3u8[^"\']*)["\']' % re.escape(var),
                html)
            if m:
                return self._u(m.group(1))

        m = _RE_M3U8_JSON.search(html)
        if m:
            return m.group(1).replace("\\/", "/")

        dataid = _RE_DATAID.search(html)
        code = _RE_PLAY_CODE.search(page_url or "")
        for tpl in ("/api/play/{code}", "/api/video/{dataid}",
                    "/api/episode/{dataid}", "/api/url/{code}"):
            api = self.site + tpl.format(
                code=code.group(1) if code else "",
                dataid=dataid.group(1) if dataid else "")
            try:
                txt = self._get(api, referer=page_url)
                if not txt:
                    continue
                m2 = _RE_M3U8_RAW.search(txt)
                if m2:
                    return m2.group(1)
                try:
                    s = json.dumps(json.loads(txt))
                    m2 = _RE_M3U8_RAW.search(s)
                    if m2:
                        return m2.group(1)
                except Exception:
                    pass
            except Exception:
                pass
        return ""

    def _play_header(self):
        """
        播放/嗅探/代理统一使用的 header。
        bttwo 的 CDN 会拒绝携带 Referer 的分片请求，因此这里只保留 UA，不带 Referer/Origin。
        """
        return {
            "User-Agent": UA,
            "Accept": "*/*",
        }

    def playerContent(self, flag, ids, vipFlags=None):
        url = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        url = str(url or "").strip()
        if not url:
            return {"parse": 0, "url": "", "header": self._play_header()}
        if not url.startswith("http"):
            url = self._u(url)
        self.log("player: %s" % url)

        u = url.lower()
        if u.endswith((".m3u8", ".mp4", ".flv", ".mkv", ".ts", ".avi")) or "m3u8" in u:
            return {"parse": 0, "url": url, "header": self._play_header()}

        html = self._get(url, referer=self.site + "/")
        found = self._extract_m3u8(html, url)
        if found:
            if found.startswith("//"):
                found = "https:" + found
            elif not found.startswith("http"):
                found = self._u(found)
            self.log("  => 直链 m3u8: %s" % found[:160])
            return {"parse": 0, "url": found, "header": self._play_header()}

        self.log("  => 未找到直链，交由上层嗅探（header 已去 Referer）")
        return {"parse": 1, "url": url, "header": self._play_header()}

    def localProxy(self, param):
        u = param.get("url", "") if isinstance(param, dict) else ""
        if not u:
            return [403, "text/plain", b"", None]
        u = self._u(u)
        h = self._play_header()
        if self.s is not None:
            try:
                r = self.s.get(u, headers=h, timeout=15)
                return [200, r.headers.get("Content-Type", "application/octet-stream"),
                        r.content, None]
            except Exception:
                pass
        try:
            import urllib.request
            req = urllib.request.Request(u, headers=h)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return [200, resp.headers.get("Content-Type", "application/octet-stream"),
                        resp.read(), None]
        except Exception:
            return [403, "text/plain", b"", None]


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
