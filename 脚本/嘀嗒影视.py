# coding=utf-8
"""
嘀嗒影视 didahd.xyz | TVBox Python 爬虫 (V2.2 AES+嗅探双保险)
特点:
  - 适配 MyUI + MacCMS 模板
  - 支持分类筛选（地区/剧情/年份/排序）
  - encrypt=3 优先 AES 解密（seed + MD5），成功则 parse:0 秒播
  - 解密失败自动回退播放页嗅探（parse:1），稳定兼容
  - 简介完美提取：精准提取隐藏的完整剧情
"""
import re
import sys
import json
import time
import hashlib
import base64
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
                print("[didahd]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOST = "https://www.didahd.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
DEFAULT_PIC = HOST + "/template/mytheme/statics/img/load.png"

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# AES 解密用的固定种子
_AES_SEED_SUFFIX = "RY7e48naFXPsLJC"

CLASSES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "纪录片"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "5", "type_name": "综艺"},
]

_SORTS = [
    {"n": "时间", "v": "time"},
    {"n": "人气", "v": "hits"},
    {"n": "评分", "v": "score"},
]

_AREAS = [
    {"n": "全部", "v": ""},
    {"n": "大陆", "v": "大陆"}, {"n": "美国", "v": "美国"},
    {"n": "日本", "v": "日本"}, {"n": "韩国", "v": "韩国"},
    {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"},
    {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"},
    {"n": "法国", "v": "法国"}, {"n": "德国", "v": "德国"},
    {"n": "印度", "v": "印度"}, {"n": "加拿大", "v": "加拿大"},
    {"n": "意大利", "v": "意大利"},
]

_CLASS_OPTIONS = [
    {"n": "全部", "v": ""},
    {"n": "剧情", "v": "剧情"}, {"n": "喜剧", "v": "喜剧"},
    {"n": "动作", "v": "动作"}, {"n": "爱情", "v": "爱情"},
    {"n": "科幻", "v": "科幻"}, {"n": "悬疑", "v": "悬疑"},
    {"n": "惊悚", "v": "惊悚"}, {"n": "犯罪", "v": "犯罪"},
    {"n": "恐怖", "v": "恐怖"}, {"n": "冒险", "v": "冒险"},
    {"n": "奇幻", "v": "奇幻"}, {"n": "古装", "v": "古装"},
    {"n": "战争", "v": "战争"}, {"n": "历史", "v": "历史"},
    {"n": "家庭", "v": "家庭"}, {"n": "武侠", "v": "武侠"},
    {"n": "青春", "v": "青春"}, {"n": "都市", "v": "都市"},
    {"n": "动画", "v": "动画"}, {"n": "纪录片", "v": "纪录片"},
]

FILTERS = {
    "1": [
        {"key": "class", "name": "剧情", "value": _CLASS_OPTIONS},
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]},
        {"key": "sort_field", "name": "排序", "value": _SORTS},
    ],
    "2": [
        {"key": "class", "name": "剧情", "value": _CLASS_OPTIONS},
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]},
        {"key": "sort_field", "name": "排序", "value": _SORTS},
    ],
    "3": [
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]},
    ],
    "4": [
        {"key": "class", "name": "剧情", "value": _CLASS_OPTIONS},
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]},
    ],
    "5": [
        {"key": "class", "name": "剧情", "value": _CLASS_OPTIONS},
        {"key": "area", "name": "地区", "value": _AREAS},
        {"key": "year", "name": "年份",
         "value": [{"n": "全部", "v": ""}] +
                  [{"n": str(y), "v": str(y)} for y in range(2026, 1999, -1)]},
    ],
}

# ===================== 正则 =====================
_RE_CARD = re.compile(
    r'<a\s+class="myui-vodlist__thumb lazyload"\s+href="(/detail/\d+\.html)"\s+'
    r'title="([^"]*)"\s+data-original="([^"]*)"',
    re.S | re.I)

_RE_PIC_FALLBACK = re.compile(r'data-original="([^"]+)"', re.I)

_RE_EPISODE_TAB = re.compile(
    r'<a\s+href="#playlist(\d+)"\s+data-toggle="tab">([^<]+)</a>', re.I)

_RE_EPISODE_LIST = re.compile(
    r'<ul\s+class="myui-content__list\s+sort-list\s+clearfix"[^>]*>([\s\S]*?)</ul>',
    re.S | re.I)

_RE_EPISODE_LINK = re.compile(
    r'<a\s+class="btn\s+btn-default"\s+href="([^"]+)"[^>]*>([^<]+)</a>', re.I)

_RE_PLAYER_AA = re.compile(r'var\s+player_aaaa\s*=\s*(\{.*?\});', re.S)

# 详情页元信息
_RE_H1 = re.compile(r'<h1[^>]*>([\s\S]*?)</h1>', re.I)
_RE_TITLE = re.compile(r'<title>(.*?)</title>', re.S | re.I)

# 简介提取正则
_RE_INTRO_DATA = re.compile(r'<span\s+class="data"\s+style="display:\s*none;">([\s\S]*?)</span>\s*<a', re.I)
_RE_INTRO_SKETCH = re.compile(r'<span\s+class="sketch\s+content">([\s\S]*?)</span>', re.I)
_RE_META_DESC = re.compile(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)["\']', re.I)

_RE_DIRECTOR = re.compile(r'<span\s+class="text-muted">导演：</span>([\s\S]*?)</p>', re.S | re.I)
_RE_ACTOR = re.compile(r'<span\s+class="text-muted">主演：</span>([\s\S]*?)</p>', re.S | re.I)
_RE_SCORE = re.compile(r'pic-tag-right[^>]*>([\d.]+)分<', re.I)
_RE_AREA = re.compile(r'<span\s+class="text-muted\s+hidden-xs">地区：</span>([^<]*)<', re.I)
_RE_YEAR = re.compile(r'<span\s+class="text-muted\s+hidden-xs">年份：</span>([^<]*)<', re.I)

# PoW 挑战
_RE_POW_HASH = re.compile(r"var\s+hash\s*=\s*['\"]([a-f0-9]{40})['\"]")
_RE_POW_TARGET = re.compile(r"var\s+target\s*=\s*['\"]([a-f0-9]{40})['\"]")

# Artplayer 页面提取
_RE_ART_TS = re.compile(r'const\s+timestamp\s*=\s*["\']([^"\']+)', re.I)
_RE_ART_QUALITIES = re.compile(r'const\s+qualities\s*=\s*(\[[\s\S]*?\]);', re.I)


class Spider(Spider):

    def getName(self):
        return "嘀嗒影视"

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

        # 检查 AES 可用性
        try:
            from Crypto.Cipher import AES as _AES
            from Crypto.Util.Padding import unpad as _unpad
            self._AES = _AES
            self._unpad = _unpad
            self.log("init: AES 可用")
        except Exception:
            self._AES = None
            self._unpad = None
            self.log("init: AES 不可用（缺少 pycryptodome），将只走嗅探")

        self.log("init: site=%s" % self.site_url)

    # ---------- 网络请求 ----------
    def _fetch(self, url, timeout=20, headers=None):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            rsp = self.fetch(url, headers=h, timeout=timeout)
            text = ""
            if hasattr(rsp, "text"):
                text = rsp.text or ""
            elif hasattr(rsp, "content"):
                text = rsp.content.decode("utf-8", "ignore")
            else:
                text = str(rsp)

            if ("正在检测" in text) or ("sha1(hash" in text and "attack_key" in text):
                self.log("⚠️ 遇到 PoW 挑战")
                attack_key = self._solve_pow(text)
                if attack_key is not None:
                    sep = "&" if "?" in url else "?"
                    new_url = url + sep + "attack_key=" + str(attack_key)
                    rsp2 = self.fetch(new_url, headers=h, timeout=timeout)
                    text = rsp2.text if hasattr(rsp2, "text") else str(rsp2)
            return text
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url, e))
            return ""

    def _solve_pow(self, html):
        m1 = _RE_POW_HASH.search(html)
        m2 = _RE_POW_TARGET.search(html)
        if not m1 or not m2:
            return None
        hash_prefix = m1.group(1)
        target = m2.group(1)
        max_i = 10 * 1000 * 1000
        start = time.time()
        prefix_b = hash_prefix.encode()
        for i in range(max_i):
            s = hashlib.sha1(prefix_b + str(i).encode()).hexdigest()
            if s == target:
                return i
            if (i + 1) % 1000000 == 0:
                if time.time() - start > 60:
                    return None
        return None

    # ---------- 工具 ----------
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

    # ---------- AES 解密（新增）----------
    def _decode_art_url(self, cipher_text, timestamp):
        """用正确的种子和 key/iv 顺序解密 Artplayer URL"""
        if not self._AES or not cipher_text or not timestamp:
            return ""
        try:
            seed = str(timestamp) + _AES_SEED_SUFFIX
            md5 = hashlib.md5(seed.encode("utf-8")).hexdigest()
            key = md5[16:32].encode("utf-8")
            iv = md5[0:16].encode("utf-8")

            raw = cipher_text.replace("\\/", "/")
            dec = self._AES.new(key, self._AES.MODE_CBC, iv).decrypt(
                base64.b64decode(raw))
            result = self._unpad(dec, 16).decode("utf-8", "ignore")
            return result.replace("\\/", "/")
        except Exception as e:
            self.log("AES 解密失败: %s" % e)
            return ""

    def _try_artplayer_decrypt(self, raw_url, referer):
        """请求 Artplayer 页面并尝试 AES 解密真实 m3u8"""
        if not self._AES or not raw_url:
            return ""
        if not re.match(r'^[0-9a-fA-F]+$', raw_url):
            return ""

        try:
            art = self.site_url + "/static/player/artplayer/?url=" + \
                  urllib.parse.quote(raw_url, safe='')
            txt = self._fetch(art, headers={"Referer": referer})
            if not txt:
                return ""

            ts = _RE_ART_TS.search(txt)
            if not ts:
                self.log("  未找到 timestamp")
                return ""
            timestamp = ts.group(1)

            qm = _RE_ART_QUALITIES.search(txt)
            if not qm:
                self.log("  未找到 qualities")
                return ""

            try:
                arr = json.loads(qm.group(1))
            except Exception:
                return ""

            for it in arr:
                u = self._decode_art_url(it.get("url", ""), timestamp)
                if u and u.startswith("http"):
                    self.log("  ✅ AES 解密成功")
                    return self._fix_url(u)
            return ""
        except Exception as e:
            self.log("  Artplayer 解密异常: %s" % e)
            return ""

    # ---------- 列表提取 ----------
    def _extract_videos(self, html):
        videos = []
        seen = set()
        if not html:
            return videos

        matches = _RE_CARD.findall(html)
        self.log("  卡片: %d 条" % len(matches))
        for href, title, pic in matches:
            if href in seen:
                continue
            seen.add(href)
            videos.append({
                "vod_id": href,
                "vod_name": self._clean(title)[:100],
                "vod_pic": self._fix_url(pic) or self.default_pic,
                "vod_remarks": "",
            })

        if not videos:
            hrefs = re.findall(r'href="(/detail/\d+\.html)"', html)
            imgs = re.findall(r'data-original="([^"]+)"', html)
            for i, href in enumerate(hrefs):
                if href in seen:
                    continue
                seen.add(href)
                pic = imgs[i] if i < len(imgs) else ""
                videos.append({
                    "vod_id": href,
                    "vod_name": href.split("/")[-1].replace(".html", ""),
                    "vod_pic": self._fix_url(pic) or self.default_pic,
                    "vod_remarks": "",
                })
        return videos

    def _page_count(self, html):
        if not html:
            return 1
        pages = re.findall(r'page=(\d+)', html)
        if pages:
            try:
                return max(int(p) for p in pages) + 1
            except Exception:
                pass
        return 999

    # ---------- TVBox 接口 ----------
    def homeContent(self, filter=False):
        return {"class": CLASSES, "filters": FILTERS}

    def homeVideoContent(self):
        return self.categoryContent("1", "1", False, {})

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not extend:
            extend = {}

        for k in list(extend.keys()):
            if extend[k] in ("", None, "全部"):
                del extend[k]

        area = extend.get("area", "")
        cls = extend.get("class", "")
        year = extend.get("year", "")
        sort = extend.get("sort_field", "time")

        if sort == "time":
            sort_seg = ""
        else:
            sort_seg = sort

        url = "%s/show/%s-%s--%s-----%s---%s.html" % (
            self.site_url, tid, area, cls, sort_seg, year)

        self.log("category: %s" % url)
        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))

        videos = self._extract_videos(html)
        pagecount = self._page_count(html)
        self.log("  结果: %d 条, 页数: %d" % (len(videos), pagecount))

        return {
            "list": videos, "page": page, "pagecount": pagecount,
            "limit": 24, "total": pagecount * 24,
        }

    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        keyword = urllib.parse.quote(key)
        url = "%s/search/-------------.html?wd=%s&submit=" % (self.site_url, keyword)
        self.log("search: %s" % url)
        html = self._fetch(url)
        self.log("  HTML 长度: %d" % len(html))
        videos = self._extract_videos(html)
        return {
            "list": videos, "page": page,
            "pagecount": self._page_count(html),
            "limit": 24, "total": 999,
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
        self.log("  HTML 长度: %d" % len(html))
        if not html:
            return {"list": []}

        name = ""
        m = _RE_H1.search(html)
        if m:
            name = self._clean(m.group(1))
        if not name:
            m = _RE_TITLE.search(html)
            if m:
                name = self._clean(m.group(1).split("_")[0].split("-")[0])
        name = re.sub(r"\s*\(\d{4}\)\s*$", "", name).strip() or vod_id

        pic = self.default_pic
        m = _RE_PIC_FALLBACK.search(html)
        if m:
            pic = self._fix_url(m.group(1))

        content = ""
        m_data = _RE_INTRO_DATA.search(html)
        if m_data:
            content = self._clean(m_data.group(1))
        if not content:
            m_sketch = _RE_INTRO_SKETCH.search(html)
            if m_sketch:
                content = self._clean(m_sketch.group(1))
        if not content:
            m_meta = _RE_META_DESC.search(html)
            if m_meta:
                content = self._clean(m_meta.group(1))

        content = INTRO_PREFIX + "\n" + content if content else INTRO_PREFIX

        director = ""
        m = _RE_DIRECTOR.search(html)
        if m:
            director = self._clean(m.group(1))

        actor = ""
        m = _RE_ACTOR.search(html)
        if m:
            actor = re.sub(r"\s*,\s*", ", ", self._clean(m.group(1)))

        score = ""
        m = _RE_SCORE.search(html)
        if m:
            score = m.group(1)

        area = ""
        m = _RE_AREA.search(html)
        if m:
            area = self._clean(m.group(1))

        year = ""
        m = _RE_YEAR.search(html)
        if m:
            year = self._clean(m.group(1))

        play_from = []
        play_url = []

        tabs = _RE_EPISODE_TAB.findall(html)
        playlists = _RE_EPISODE_LIST.findall(html)

        self.log("  线路: %d, 播放列表: %d" % (len(tabs), len(playlists)))

        for i, pl_html in enumerate(playlists):
            if i >= len(tabs):
                break
            line_name = tabs[i][1].strip()
            episodes = _RE_EPISODE_LINK.findall(pl_html)
            if not episodes:
                continue

            ep_strs = []
            for ep_href, ep_name in episodes:
                ep_href = ep_href.replace("&amp;", "&")
                if ep_href.startswith("/"):
                    ep_href = self.site_url + ep_href
                ep_strs.append("%s$%s" % (self._clean(ep_name), ep_href))

            if ep_strs:
                play_from.append(line_name)
                play_url.append("#".join(ep_strs))

        self.log("  有效线路: %d" % len(play_from))

        if not play_from:
            return {"list": []}

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": name,
            "vod_pic": pic,
            "vod_content": content,
            "vod_actor": actor,
            "vod_director": director,
            "vod_score": score,
            "vod_area": area,
            "vod_year": year,
            "vod_remarks": "共%d条线路" % len(play_from),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }]}

    # ---------- 播放解析（AES 优先 + 嗅探兜底）----------
    def playerContent(self, flag, id, vipFlags):
        play_page = id if id.startswith("http") else self._fix_url(id)
        self.log("player: %s" % play_page)

        now = int(time.time())
        if play_page in self._play_cache:
            ts, res = self._play_cache[play_page]
            if now - ts < 600:
                return res

        html = self._fetch(play_page)
        if not html:
            return {"parse": 1, "playUrl": "", "url": play_page,
                    "header": {"User-Agent": UA, "Referer": self.site_url + "/"}}

        # 解析 player_aaaa
        encrypt = 0
        url_val = ""
        m = _RE_PLAYER_AA.search(html)
        if m:
            try:
                raw = m.group(1)
                raw = (raw.replace("\\\\u0026", "&").replace("\\u0026", "&")
                          .replace("\\\\u0022", '"').replace("\\u0022", '"')
                          .replace("\\/", "/"))
                player_data = json.loads(raw)
                encrypt = player_data.get("encrypt", 0)
                url_val = player_data.get("url", "")
                self.log("  encrypt=%s, url_len=%d" % (encrypt, len(url_val)))
            except Exception as e:
                self.log("  解析 player_aaaa 失败: %s" % e)

        # ---------- encrypt 0/1/2：直接处理 ----------
        if encrypt == 0 and url_val.startswith("http"):
            res = {
                "parse": 0, "playUrl": "",
                "url": url_val,
                "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
            }
            self._play_cache[play_page] = (now, res)
            return res

        if encrypt == 1 and url_val:
            url_dec = urllib.parse.unquote(url_val)
            if url_dec.startswith("http"):
                res = {
                    "parse": 0, "playUrl": "",
                    "url": url_dec,
                    "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
                }
                self._play_cache[play_page] = (now, res)
                return res

        if encrypt == 2 and url_val:
            try:
                url_dec = urllib.parse.unquote(
                    base64.b64decode(url_val).decode("utf-8", "ignore"))
                if url_dec.startswith("http"):
                    res = {
                        "parse": 0, "playUrl": "",
                        "url": url_dec,
                        "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
                    }
                    self._play_cache[play_page] = (now, res)
                    return res
            except Exception as e:
                self.log("  base64 解码失败: %s" % e)

        # ---------- encrypt==3：优先 AES 解密 ----------
        if encrypt == 3 and url_val:
            self.log("  => 尝试 AES 解密")
            real_url = self._try_artplayer_decrypt(url_val, play_page)
            if real_url:
                res = {
                    "parse": 0, "playUrl": "",
                    "url": real_url,
                    "header": {"User-Agent": UA, "Referer": self.site_url + "/"},
                }
                self._play_cache[play_page] = (now, res)
                return res
            self.log("  AES 解密未成功，回退嗅探")

        # ---------- 兜底：嗅探播放页 ----------
        self.log("  => 嗅探播放页")
        res = {
            "parse": 1, "playUrl": "",
            "url": play_page,
            "header": {
                "User-Agent": UA,
                "Referer": self.site_url + "/",
            },
        }
        self._play_cache[play_page] = (now, res)
        return res

    # ---------- 其他 ----------
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
