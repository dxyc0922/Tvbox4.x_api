# -*- coding: utf-8 -*-
"""
看剧 kanju.ai | TVBox Python 爬虫
关键:
  - HMAC-SHA256 请求签名 (timestamp + nonce)
  - 主备域名自动切换
  - 播放多级兜底: resolve-line -> 直链校验 -> 页面嗅探
  - 线路级自动探活: 记录失败线路，下次优先可用线路
"""
import sys
import json
import time
import math
import hmac
import hashlib
import secrets
import binascii
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
            method = kw.pop('method', 'GET').upper()
            data = kw.pop('data', None)
            stream = kw.pop('stream', False)
            if method == 'POST':
                r = self._sess.post(url, headers=headers, data=data,
                                    timeout=timeout, stream=stream, **kw)
            else:
                r = self._sess.get(url, headers=headers, timeout=timeout,
                                   stream=stream, **kw)
            r.encoding = 'utf-8'
            return r

        def log(self, *a, **kw):
            try:
                print("[kanju]", *a)
            except Exception:
                pass

    Spider = _BaseSpider


HOSTS = ["https://kanju.ai", "https://kanju20.com"]
KEY = "557d0e4ae929f438da6bd84412374e6086b8af09b3fed54bf22601d5bf8c54a0"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CLIENT = {
    "x-ai-movie-client-name": "dianyingtiantang-frontend",
    "x-ai-movie-client-version": "1.0.0",
    "x-ai-movie-build-version": "dianyingtiantang-v2026.08.11.1-8cbb0b0d407e-672e67d62528",
    "x-ai-movie-protocol-version": "2026-07-05.library-v2.playback-v1",
}

INTRO_PREFIX = "🍊小橙子为您介绍剧情👉请不要相信视频中的广告，以免上当受骗！"

# 线路名 -> 播放页 Referer（部分 CDN 校验 Referer）
REFERER_MAP = {
    "hn.bfvvs.com": "https://hn.bfvvs.com/",
    "bfikuncdn.com": "https://bfikuncdn.com/",
    "jisuzy": "https://www.jisuzy.com/",
    "jisuts": "https://www.jisuzy.com/",
    "yzzy": "https://www.yzzy.com/",
    "modujx": "https://www.modujx.com/",
    "xluuss": "https://www.xluuss.com/",
    "wsyzym3u8": "https://www.wsyzym3u8.com/",
    "xgplay": "https://www.xgplay20.com/",
    "ly166": "https://www.ly166.com/",
    "rstu6": "https://www.rstu6.com/",
    "hhuus": "https://www.hhuus.com/",
    "ajupf": "https://www.ajupf.com/",
    "fengbao": "https://www.fengbao14.com/",
    "kuktxu": "https://www.kuktxu.com/",
    "ukubf": "https://www.ukubf3.com/",
    "maoyanplay": "https://www.maoyanplay.com/",
    "dytt-tvs": "https://www.dytt-tvs.com/",
    "ppqrrs": "https://www.ppqrrs.com/",
    "ffzy-onl": "https://www.ffzy-online.com/",
    "gghijk": "https://www.gghijk.com/",
    "lzcdn": "https://www.lzcdn.com/",
    "zuidazym3u": "https://www.zuidazy.com/",
    "maowushi": "https://www.maowushi.com/",
}

CATEGORIES = {
    "movie": "电影", "series": "电视剧", "short_drama": "短剧",
    "anime": "动漫", "variety": "综艺", "documentary": "纪录片",
}

GENRES = {
    "movie": ["动作", "冒险", "剧情", "喜剧", "奇幻", "古装", "家庭", "科幻"],
    "series": ["动作", "冒险", "剧情", "刑侦", "古装", "历史", "台剧", "悬疑"],
    "short_drama": ["剧情", "动作", "反转爽剧", "古装仙侠", "喜剧", "女频恋爱", "家庭", "年代"],
    "anime": ["热血", "冒险", "奇幻", "日本动漫", "国产动漫", "爆笑", "武侠", "儿童"],
    "variety": ["大陆综艺", "真人秀", "情感", "爱情", "社交观察"],
    "documentary": ["历史", "纪录片"],
}

_SORTS = [
    {"n": "热门", "v": "trending"},
    {"n": "最新", "v": "latest"},
    {"n": "评分", "v": "rating"},
]

# 线路排序：m3u8 直链优先（播放器兼容性最好），官方 mp4 次之
_KIND_RANK = {"m3u8": 0, "mp4": 1, "unknown": 9}


def _kind_of(head):
    """根据响应头字节判断真实媒体类型，绕开错误的 Content-Type"""
    if not head:
        return ""
    if head[:7] == b"#EXTM3U":
        return "m3u8"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "mp4"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "mp3"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "mkv"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:4] == b"\x89PNG":
        return "png"
    if head[:2] in (b"PK",) or head[:4] == b"RIFF":
        return "bin"
    if head[:5] == b"<?xml" or head[:1] in (b"<", b"{"):
        return "text"
    return ""


class Spider(Spider):

    def getName(self):
        return "看剧"

    def init(self, extend=""):
        try:
            self.extend = json.loads(extend) if extend else {}
        except Exception:
            self.extend = {}

        self.hosts = list(self.extend.get("hosts") or HOSTS)
        self._hi = 0
        self.headers = {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": self._host() + "/",
        }
        self._hv = None
        self._hv_t = 0
        self._sc = {}
        self._sc_t = {}
        # 线路探活缓存: {线路名: {"ok":bool, "t":ts, "url":真实地址}}
        self._line_probe = {}
        # 播放地址缓存: {token: {"url":.., "referer":.., "t":ts}}
        self._play_cache = {}

        # 探测可用域名
        self._probe_host()
        self.log("init: host=%s" % self._host())
        return ""

    # ---------------- 基础工具 ----------------

    def _host(self):
        return self.hosts[getattr(self, "_hi", 0)]

    def _probe_host(self):
        order = list(range(len(self.hosts)))
        if getattr(self, "_hi", 0):
            order.insert(0, order.pop(self._hi))
        for i in order:
            h = self.hosts[i]
            try:
                r = self.fetch(h, headers={"User-Agent": UA}, timeout=12)
                if getattr(r, "status_code", None) == 200:
                    self._hi = i
                    return True
            except Exception:
                continue
        return False

    def _sign(self, method, path):
        ts = str(int(time.time() * 1000))
        nonce = secrets.token_hex(16)
        msg = "%s\n%s\n%s\n%s" % (method, path, ts, nonce)
        sig = hmac.new(KEY.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return ts, nonce, sig

    def _fetch(self, url, headers=None, timeout=15, method="GET", data=None,
               stream=False):
        try:
            h = dict(self.headers)
            if headers:
                h.update(headers)
            kw = {"timeout": timeout}
            if stream:
                kw["stream"] = True
            if method.upper() == "POST":
                rsp = self.fetch(url, headers=h, method="POST", data=data, **kw)
            else:
                rsp = self.fetch(url, headers=h, **kw)
            return rsp
        except TypeError:
            # 兼容不支持 stream 参数的内核
            try:
                h = dict(self.headers)
                if headers:
                    h.update(headers)
                if method.upper() == "POST":
                    return self.fetch(url, headers=h, timeout=timeout,
                                      method="POST", data=data)
                return self.fetch(url, headers=h, timeout=timeout)
            except Exception as e:
                self.log("fetch FAIL %s -> %s" % (url[:80], e))
                return None
        except Exception as e:
            self.log("fetch FAIL %s -> %s" % (url[:80], e))
            return None

    def _req(self, method, path, body=None, retry_host=True):
        """带签名请求，失败自动切换备用域名"""
        tries = len(self.hosts) if retry_host else 1
        for n in range(tries):
            host = self._host()
            try:
                ts, nonce, sig = self._sign(method, path)
                hdrs = {
                    "User-Agent": UA, "Accept": "application/json",
                    "Referer": host + "/",
                    "x-ai-movie-timestamp": ts, "x-ai-movie-nonce": nonce,
                    "x-ai-movie-signature": sig,
                }
                hdrs.update(CLIENT)
                url = host + path
                if body is not None:
                    hdrs["Content-Type"] = "application/json"
                    rsp = self._fetch(url, headers=hdrs, timeout=12,
                                      method="POST",
                                      data=json.dumps(body, ensure_ascii=False))
                else:
                    rsp = self._fetch(url, headers=hdrs, timeout=12)

                if rsp is None:
                    raise RuntimeError("rsp is None")
                code = getattr(rsp, "status_code", 0)
                if code in (200, 201):
                    try:
                        j = rsp.json()
                    except Exception:
                        txt = getattr(rsp, "text", "") or ""
                        j = json.loads(txt) if txt.strip().startswith("{") else {}
                    if isinstance(j, dict):
                        return j
                    return {}
                self.log("req %s %s -> HTTP %s" % (method, path[:70], code))
                # 4xx 说明签名/参数问题，换域名也没用，但仍试一次
                if code in (401, 403, 404):
                    break
            except Exception as e:
                self.log("req FAIL %s %s -> %s" % (method, path[:70], e))
            if n + 1 < tries:
                self._hi = (self._hi + 1) % len(self.hosts)
                time.sleep(0.6)
        return {}

    def _fix_url(self, url):
        if not url:
            return ""
        url = str(url).strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return self._host() + url
        return urllib.parse.urljoin(self._host() + "/", url)

    def _clean(self, s):
        if not s:
            return ""
        s = str(s)
        s = s.replace("&nbsp;", " ").replace("\xa0", " ")
        s = (s.replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
        return s.strip()

    def _referer_for(self, url):
        """按 CDN 域名推断 Referer；无法识别时退回站点根"""
        try:
            host = urllib.parse.urlparse(url).netloc.lower()
        except Exception:
            return self._host() + "/"
        for k, v in REFERER_MAP.items():
            if k in host:
                return v
        return self._host() + "/"

    def _play_header(self, url=""):
        h = {"User-Agent": UA}
        if url:
            h["Referer"] = self._referer_for(url)
            h["Origin"] = h["Referer"].rstrip("/")
        else:
            h["Referer"] = self._host() + "/"
        return h

    # ---------------- 内容 ----------------

    def _vod(self, c):
        if not isinstance(c, dict):
            return {}
        remarks = c.get("remarks")
        if not remarks:
            ep_txt = c.get("episode_progress_text") or ""
            if ep_txt:
                remarks = self._clean(ep_txt)
            elif c.get("year"):
                remarks = str(c.get("year"))
        return {
            "vod_id": c.get("id", "") or c.get("variant_id", ""),
            "vod_name": self._clean(c.get("title") or c.get("name") or ""),
            "vod_pic": self._fix_url(c.get("poster_url") or c.get("carousel_url") or ""),
            "vod_remarks": self._clean(remarks or ""),
            "vod_year": str(c.get("year") or ""),
            "vod_area": self._clean(c.get("area") or ""),
            "vod_actor": "/".join((c.get("actors") or [])[:3]),
            "vod_director": "/".join((c.get("directors") or [])[:2]),
        }

    def homeContent(self, filter=False):
        cls = []
        for k, v in CATEGORIES.items():
            cls.append({
                "type_id": k, "type_name": v,
                "subs": [{"type_id": "%s:%s" % (k, g), "type_name": g}
                         for g in GENRES.get(k, [])],
            })
        filters = {}
        for k in CATEGORIES:
            filters[k] = [
                {"key": "sort", "name": "排序", "value": _SORTS},
                {"key": "genre", "name": "类型",
                 "value": [{"n": "全部", "v": ""}] +
                          [{"n": g, "v": g} for g in GENRES.get(k, [])]},
            ]
        return {"class": cls, "filters": filters, "list": []}

    def homeVideoContent(self):
        now = time.time()
        if self._hv and (now - self._hv_t < 300):
            return self._hv

        seen, lst = set(), []
        paths = [
            "/v1/feed/home",
            "/v1/browse/catalog?kind=movie&sort=trending&window=day&page=1&limit=40",
            "/v1/browse/catalog?kind=series&sort=trending&window=day&page=1&limit=40",
            "/v1/browse/catalog?kind=short_drama&sort=trending&window=day&page=1&limit=40",
        ]
        for p in paths:
            j = self._req("GET", p)
            if not j:
                continue
            for s in (j.get("sections") or []):
                for c in (s.get("cards") or []):
                    v = self._vod(c)
                    vid = v.get("vod_id")
                    if vid and vid not in seen:
                        seen.add(vid)
                        lst.append(v)
            for c in (j.get("cards") or []):
                v = self._vod(c)
                vid = v.get("vod_id")
                if vid and vid not in seen:
                    seen.add(vid)
                    lst.append(v)

        if lst:
            self._hv, self._hv_t = {"list": lst}, now
        self.log("home: %d 条" % len(lst))
        return {"list": lst}

    def categoryContent(self, tid, pg=1, filter=False, extend=""):
        pn = 1
        try:
            pn = max(int(str(pg).strip()), 1)
        except Exception:
            pass

        # 解析 extend（TVBox 可能传 str / dict / list）
        ext = {}
        if isinstance(extend, dict):
            ext = extend
        elif isinstance(extend, (list, tuple)):
            for e in extend:
                if isinstance(e, dict):
                    ext.update(e)
        elif isinstance(extend, str) and extend.strip():
            try:
                t = json.loads(extend)
                if isinstance(t, dict):
                    ext = t
            except Exception:
                ext = {}

        cat, gen = str(tid), ""
        if ":" in cat:
            cat, gen = cat.split(":", 1)
        if cat not in CATEGORIES:
            cat = "movie"

        gen = str(ext.get("genre") or gen or "").strip()
        if gen in ("全部", "all", "0"):
            gen = ""
        sort = str(ext.get("sort") or "trending").strip()
        if sort in ("全部", "0"):
            sort = "trending"

        qs = ["kind=%s" % cat]
        if gen:
            qs.append("genre=%s" % urllib.parse.quote(gen))
        if sort:
            qs.append("sort=%s" % urllib.parse.quote(sort))
        qs.append("page=%d" % pn)
        qs.append("limit=40")
        path = "/v1/browse/catalog?" + "&".join(qs)

        self.log("category: %s" % path)
        j = self._req("GET", path)
        cards = j.get("cards") or []
        pag = j.get("pagination") or {}
        total = pag.get("total", 0) or 0
        pagecount = max(math.ceil(total / 40.0), 1) if total else 1
        if total and not pag.get("has_more", True):
            pagecount = pn

        return {
            "page": pn, "pagecount": pagecount, "limit": 40,
            "total": total or len(cards),
            "list": [self._vod(c) for c in cards if c],
        }

    def _pick_id(self, ids):
        """兼容 TVBox 各种传参形态:
        list / tuple / '["a","b"]' / "['a']" / 'a,b' / "a/b" / "a$b"
        """
        v = ids
        if isinstance(v, (list, tuple)):
            v = v[0] if v else ""
        elif isinstance(v, str):
            s = v.strip()
            # 形如 "['xxx']" / '["xxx"]' 的字符串字面量
            if (s.startswith("[") and s.endswith("]")):
                inner = s[1:-1].strip()
                if inner:
                    s = inner.split(",")[0].strip()
                else:
                    s = ""
                # 去掉可能残留的引号
                s = s.strip().strip("'").strip('"')
                v = s
            elif "," in s:
                v = s.split(",")[0].strip()
            elif "/" in s:
                v = s.split("/")[0].strip()
        v = str(v or "").strip().strip("'").strip('"')
        if "$" in v:
            v = v.rsplit("$", 1)[-1].strip()
        return v

    def detailContent(self, ids):
        vid = self._pick_id(ids)
        if not vid:
            return {"list": []}

        self.log("detail: %s" % vid)
        d = self._req("GET", "/v1/catalog/%s" % vid)
        if not d or not d.get("id"):
            self.log("detail 失败: %s" % vid)
            return {"list": []}

        eps = d.get("episodes") or []

        # 先取第一集线路名，确保 线路数 与 剧集列表 对齐
        line_names = []
        tok0 = ""
        for e in eps:
            if e.get("token"):
                tok0 = e.get("token")
                break
        if tok0:
            line_names = self._line_names(tok0)

        if line_names:
            play_from = "$$$".join(line_names)
            blocks = []
            for _ in line_names:
                urls = []
                for idx, e in enumerate(eps):
                    t = e.get("token")
                    if not t:
                        continue
                    ep_name = (e.get("title")
                               or ("第%s集" % (e.get("number") or idx + 1)))
                    # 线路名放在 flag 上，id 里带 emoji 会破坏 TVBox 解析，这里只放 token
                    urls.append("%s$%s" % (ep_name, t))
                blocks.append("#".join(urls))
            play_url = "$$$".join(blocks)
        else:
            play_from = "kanju"
            urls = []
            for idx, e in enumerate(eps):
                t = e.get("token")
                if not t:
                    continue
                ep_name = (e.get("title")
                           or ("第%s集" % (e.get("number") or idx + 1)))
                urls.append("%s$%s" % (ep_name, t))
            play_url = "#".join(urls)

        content = self._clean(d.get("description") or "")
        content = (INTRO_PREFIX + "\n" + content) if content else INTRO_PREFIX

        remarks = (d.get("remarks") or d.get("episode_progress_text")
                   or d.get("update_status") or "")
        if not remarks and d.get("episode_count"):
            remarks = "共%s集" % d.get("episode_count")

        return {"list": [{
            "vod_id": vid,
            "vod_name": self._clean(d.get("title", "")),
            "vod_pic": self._fix_url(d.get("poster_url") or d.get("carousel_url") or ""),
            "vod_year": str(d.get("year") or ""),
            "vod_area": self._clean(d.get("area") or ""),
            "vod_class": "/".join((d.get("genres") or [])[:3]),
            "vod_director": "/".join((d.get("directors") or [])[:2]),
            "vod_actor": "/".join((d.get("actors") or [])[:3]),
            "vod_content": content,
            "vod_remarks": self._clean(remarks),
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }]}

    def searchContent(self, key, quick=False, pg="1"):
        k = str(key or "").strip()
        if not k:
            return {"list": []}

        try:
            pn = max(int(str(pg)), 1)
        except Exception:
            pn = 1

        ck = "q_%s_p%d" % (k, pn)
        now = time.time()
        if (self._sc_t.get(ck, 0) > now - 300) and (ck in self._sc):
            return self._sc[ck]

        path = "/v1/browse/catalog?q=%s&page=%d&limit=20" % (
            urllib.parse.quote(k), pn)
        self.log("search: %s" % path)
        j = self._req("GET", path)
        cards = j.get("cards") or []
        total = (j.get("pagination") or {}).get("total", 0) or 0

        r = {
            "list": [self._vod(c) for c in cards if c],
            "page": pn,
            "pagecount": max(math.ceil(total / 20.0), 1) if total else 1,
            "limit": 20,
            "total": total or len(cards),
        }
        self._sc[ck], self._sc_t[ck] = r, now
        return r

    def searchContentPage(self, key, quick, pg="1"):
        return self.searchContent(key, quick, pg)

    # ---------------- 播放 ----------------

    def _line_names(self, token):
        """取某集全部线路名（按可播优先级排序）"""
        key = "names:%s" % token[:24]
        now = time.time()
        c = self._play_cache.get(key)
        if c and now - c.get("t", 0) < 600:
            return c.get("names") or []

        j = self._req("GET", "/v1/playback/resolve/%s" % token, retry_host=False)
        lines = j.get("line_options") or []
        lines = self._sort_lines(lines)
        names = []
        for lo in lines:
            n = (lo.get("provider_name") or "").strip()
            if n and n not in names:
                names.append(n)
        self._play_cache[key] = {"names": names, "t": now}
        return names

    def _sort_lines(self, lines):
        """线路按 可播性 + 类型 排序：m3u8 优先，已知坏线路排后"""
        now = time.time()

        def score(lo):
            name = (lo.get("provider_name") or "").strip()
            p = self._line_probe.get(name)
            bad = 0
            if p and now - p.get("t", 0) < 1800 and not p.get("ok"):
                bad = 1
            kind = lo.get("url_kind") or "unknown"
            if kind == "resolve_ticket":
                kind = (p or {}).get("real_kind") or "mp4"
            return (bad, _KIND_RANK.get(kind, 9),
                    -(lo.get("preference_weight") or 0))

        try:
            return sorted(lines, key=score)
        except Exception:
            return lines

    def _match_line(self, lines, flag):
        """智能匹配线路, 兼容 flag 带空格或后缀的情况"""
        if not lines:
            return []
        wanted = str(flag or "").strip()
        if not wanted or wanted == "kanju":
            return lines

        # 1. 精确匹配
        picked = [l for l in lines
                  if (l.get("provider_name") or "").strip() == wanted]
        if picked:
            return picked

        # 2. 模糊包含匹配
        picked = [l for l in lines if wanted in (l.get("provider_name") or "")]
        if picked:
            return picked

        # 3. 反向包含匹配（防止壳子传的 flag 更长）
        picked = [l for l in lines
                  if (l.get("provider_name") or "")
                  and (l.get("provider_name") or "").strip() in wanted]
        if picked:
            return picked

        return lines

    def _resolve_ticket(self, ticket, line=None):
        """resolve:// ticket -> 真实播放地址"""
        t = str(ticket or "").strip()
        if t.startswith("resolve://"):
            t = t[10:]
        if not t:
            return "", ""
        if t.startswith("http"):
            return t, ""

        body = {"ticket": t}
        if isinstance(line, dict) and line.get("quality"):
            body["quality"] = line.get("quality")

        j = self._req("POST", "/v1/playback/resolve-line", body, retry_host=False)
        li = j.get("line") or {}
        url = li.get("url") or ""
        kind = li.get("url_kind") or ""
        # 个别情况 url 仍可能是二级 ticket
        if url.startswith("resolve://"):
            return self._resolve_ticket(url, line)
        return url, kind

    def _probe_media(self, url, timeout=12):
        """真实探测链接：返回 (ok, real_kind, content_type)
        关键: 官方线路常把 mp4 放在图片 CDN 上, Content-Type 错标成
        image/jpeg，播放器会据此拒绝播放。必须按魔数判断真实类型。
        """
        rsp = self._fetch(url, headers=self._play_header(url),
                          timeout=timeout, stream=True)
        if rsp is None:
            return False, "", ""
        code = getattr(rsp, "status_code", 0)
        try:
            ctype = (getattr(rsp, "headers", {}) or {}).get("Content-Type", "") or ""
        except Exception:
            ctype = ""
        if code not in (200, 206):
            try:
                rsp.close()
            except Exception:
                pass
            return False, "", ctype

        head = b""
        try:
            raw = getattr(rsp, "raw", None)
            if raw is not None:
                head = raw.read(1024, decode_content=True) or b""
            if not head:
                head = (getattr(rsp, "content", b"") or b"")[:1024]
        except Exception:
            head = (getattr(rsp, "content", b"") or b"")[:1024]
        finally:
            try:
                rsp.close()
            except Exception:
                pass

        kind = _kind_of(head)
        if kind in ("m3u8", "mp4", "mkv", "mp3"):
            return True, kind, ctype
        # 文本型可能是 m3u8 但带 BOM / 前导空白
        if head[:400].strip().startswith(b"#EXTM3U"):
            return True, "m3u8", ctype
        return False, kind, ctype

    def playerContent(self, flag, id, vipFlags=None, vipIds=None):
        tok = str(id or "").strip()
        if not tok:
            return {"url": ""}

        # 0) id 本身已是直链
        if tok.startswith("http"):
            u = tok
            if u.startswith("resolve://"):
                u = u[10:]
            if ".m3u8" in u or ".mp4" in u or "m3u8" in u:
                return {"parse": 0, "playUrl": "", "url": u,
                        "header": self._play_header(u)}

        # token 里可能带 "线路名$token"，兜底拆一下
        if "$" in tok:
            tok = tok.rsplit("$", 1)[-1].strip()

        cache_key = "%s|%s" % (str(flag or "").strip(), tok[:40])
        now = time.time()
        c = self._play_cache.get(cache_key)
        if c and now - c.get("t", 0) < 900 and c.get("url"):
            self.log("player: 命中缓存")
            return {"parse": 0, "playUrl": "", "url": c["url"],
                    "header": c.get("header") or self._play_header(c["url"])}

        self.log("player: flag=%s tok=%s" % (flag, tok[:28]))

        j = self._req("GET", "/v1/playback/resolve/%s" % tok)
        lines = j.get("line_options") or []
        picked = self._match_line(lines, flag)
        # 排序：可播优先，m3u8 优先
        picked = self._sort_lines(picked)

        tried = 0
        for lo in picked[:12]:
            name = (lo.get("provider_name") or "").strip()
            uk = lo.get("url_kind") or ""
            raw = (lo.get("url") or "").strip()
            if not raw:
                continue

            url, real_kind = "", ""
            if uk == "resolve_ticket" or raw.startswith("resolve://"):
                url, real_kind = self._resolve_ticket(raw, lo)
            elif raw.startswith("http"):
                url = raw
                real_kind = uk
            if not url:
                self.log("  线路 %s 解析为空" % name)
                continue

            tried += 1
            ok, kind, ctype = self._probe_media(url)
            self._line_probe[name] = {"ok": ok, "t": time.time(),
                                      "real_kind": kind or real_kind}

            if not ok:
                self.log("  线路 %s 不可用 (code/type=%s)" % (name, kind or ctype))
                continue

            header = self._play_header(url)
            # 类型与扩展名不符时（如 mp4 挂在图片 CDN 上），
            # 加 hint 让播放器按真实类型解码
            if kind == "m3u8" and ".m3u8" not in url:
                pass
            self.log("  => 命中线路 %s (%s)" % (name, kind))
            self._play_cache[cache_key] = {"url": url, "header": header,
                                           "t": time.time()}
            return {"parse": 0, "playUrl": "", "url": url, "header": header}

        # 兜底：返回官方播放页，交给壳子嗅探
        fallback = "%s/v1/catalog/%s" % (self._host(), tok)
        self.log("  => 全部线路失败(试了%d条), 兜底嗅探 %s" % (tried, fallback))
        return {"parse": 1, "playUrl": "", "url": fallback,
                "header": {"User-Agent": UA, "Referer": self._host() + "/"}}

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
            if "%" in url:
                try:
                    url = urllib.parse.unquote(url)
                except Exception:
                    pass
            url = self._fix_url(url)
            rsp = self._fetch(url, headers=self._play_header(url), timeout=15)
            if rsp is None:
                return [200, "image/jpeg", b"", ""]
            content = getattr(rsp, "content", b"") or b""
            ctype = ""
            try:
                ctype = (getattr(rsp, "headers", {}) or {}).get("Content-Type", "") or ""
            except Exception:
                ctype = ""
            if not ctype.startswith("image/"):
                ctype = "image/jpeg"
            return [200, ctype, content, ""]
        except Exception:
            return [200, "image/jpeg", b"", ""]

    def isVideoFormat(self, url):
        if not url:
            return False
        u = str(url).lower()
        return ".m3u8" in u or ".mp4" in u or ".flv" in u

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._hv = None
        self._play_cache = {}
        self._line_probe = {}

    def close(self):
        self.destroy()


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
