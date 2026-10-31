# -*- coding: utf-8 -*-
import sys
import re
import json
import html as htmllib
import urllib.parse

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except ImportError:
    class _Base:
        pass

try:
    import requests as rq
    rq.packages.urllib3.disable_warnings()
except Exception:
    rq = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
SITE = "https://chengguodj.com"
DEBUG = True


def _dbg(*a):
    if DEBUG:
        print("[橙果]", *a)


def _clean(s):
    if not s:
        return ""
    s = htmllib.unescape(str(s))
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def _de_esc(u):
    """还原 Nuxt 转义后的 URL：\\u002F / \\/ 都转成 /"""
    return u.replace('\\u002F', '/').replace('\\/', '/').replace('\\\\', '\\')


class Spider(_Base):

    def getName(self):
        return "橙果短剧"

    def init(self, extend=""):
        try:
            self.s = rq.Session()
            self.s.verify = False
            self.s.headers.update({
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": SITE + "/",
            })
        except Exception:
            self.s = None

    # ────────── HTTP ──────────
    def _get(self, path, ref="/"):
        if path.startswith("http"):
            url = path
        else:
            url = SITE + path
        try:
            headers = {"Referer": SITE + ref}
            if self.s is not None:
                r = self.s.get(url, timeout=15, allow_redirects=True, headers=headers)
            else:
                r = rq.get(url, timeout=15, verify=False,
                           headers={"User-Agent": UA, **headers})
            if r.status_code == 200 and r.text:
                r.encoding = "utf-8"
                return r.text
        except Exception as e:
            _dbg("_get error:", e)
        return ""

    # ────────── Nuxt 原始文本 ──────────
    @staticmethod
    def _nuxt_raw(html):
        m = re.search(
            r'<script type="application/json" data-nuxt-data="nuxt-app"[^>]*id="__NUXT_DATA__">(.*?)</script>',
            html, re.S)
        if not m:
            m = re.search(r'id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        return m.group(1) if m else ""

    @classmethod
    def _nuxt_arr(cls, html):
        raw = cls._nuxt_raw(html)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception as e:
            _dbg("nuxt json err:", e)
            return None

    # ────────── Nuxt 扁平引用还原 ──────────
    @classmethod
    def _resolve(cls, arr, i, depth=0):
        if depth > 200:
            return None
        if not isinstance(i, int) or i < 0 or i >= len(arr):
            return None
        v = arr[i]
        if isinstance(v, list):
            if not v:
                return []
            head = v[0]
            if head in ("ShallowReactive", "Reactive", "ShallowRef", "Ref", "ComputedRef"):
                return cls._resolve(arr, v[1], depth + 1) if len(v) > 1 else None
            if head == "Set":
                return [cls._resolve(arr, x, depth + 1) for x in v[1:]]
            return [cls._resolve(arr, x, depth + 1) for x in v]
        if isinstance(v, dict):
            return {k: cls._resolve(arr, x, depth + 1) for k, x in v.items()}
        return v

    @classmethod
    def _nuxt_tree(cls, html):
        arr = cls._nuxt_arr(html)
        if not isinstance(arr, list) or len(arr) < 2:
            return None
        return cls._resolve(arr, 1)

    @classmethod
    def _walk(cls, obj, out):
        if isinstance(obj, dict):
            slug = obj.get("slug")
            if isinstance(slug, str) and slug.startswith("dj-") and "title" in obj:
                out.append(obj)
            for v in obj.values():
                cls._walk(v, out)
        elif isinstance(obj, list):
            for x in obj:
                cls._walk(x, out)

    @classmethod
    def _find_page(cls, obj, node):
        if isinstance(obj, dict):
            if isinstance(obj.get("total_pages"), int) and "page" in obj:
                node.clear()
                node.update(obj)
            for v in obj.values():
                cls._find_page(v, node)
        elif isinstance(obj, list):
            for x in obj:
                cls._find_page(x, node)

    @classmethod
    def _nuxt_items(cls, html):
        tree = cls._nuxt_tree(html)
        if not tree:
            return [], {}
        buf = []
        cls._walk(tree, buf)
        seen = {}
        for it in buf:
            s = it.get("slug")
            if s and s not in seen:
                seen[s] = it
        page = {}
        cls._find_page(tree, page)
        return list(seen.values()), page

    # ────────── 封面：只认 __NUXT_DATA__ 里的真图 ──────────
    @staticmethod
    def _cover_from_item(it):
        c = it.get("cover")
        if isinstance(c, dict):
            u = c.get("url") or ""
            if u.startswith("http"):
                return u
            f = c.get("fallback_url") or ""
            if f.startswith("http"):
                return f
            if f.startswith("/"):
                return SITE + f
        return ""

    @staticmethod
    def _cover_from_raw(nuxt_raw):
        """从 Nuxt 原始文本里抠 pic.wlwvch.cn 真图（不还原树，稳）"""
        if not nuxt_raw:
            return ""
        for m in re.finditer(r'"url":"(https?:\\?/\\?/pic\.wlwvch\.cn/[^"]+?)"', nuxt_raw):
            u = _de_esc(m.group(1))
            if u.startswith("http"):
                return u
        return ""

    # ────────── items → 卡片 ──────────
    @staticmethod
    def _episode_remark(it):
        n = it.get("latest_episode_number") or it.get("published_episode_count") or 0
        try:
            n = int(n)
        except Exception:
            n = 0
        if not n:
            return ""
        if it.get("serial_status", "") == "completed":
            return "全%d集" % n
        return "更新至%d集" % n

    @classmethod
    def _cards_from_items(cls, items):
        videos = []
        for it in items:
            slug = it.get("slug", "")
            if not slug:
                continue
            title = _clean(it.get("title", ""))
            if not title:
                continue
            pic = cls._cover_from_item(it)
            videos.append({
                "vod_id": "drama_" + slug,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": cls._episode_remark(it),
            })
        return videos

    # ────────── 详情页取图（按 slug 定位主剧） ──────────
    @staticmethod
    def _detail_cover(html, slug):
        nuxt_raw = Spider._nuxt_raw(html)
        if nuxt_raw:
            # 优先按 slug 定位主剧封面
            pat = (re.escape(slug) +
                   r'(?:(?!dj-)[^"\\])*?"url":"(https?:\\?/\\?/pic\.wlwvch\.cn/[^"]+?)"')
            m = re.search(pat, nuxt_raw, re.S)
            if m:
                u = _de_esc(m.group(1))
                if u.startswith("http"):
                    return u
            # 兜底：整段里第一个 pic.wlwvch.cn
            return Spider._cover_from_raw(nuxt_raw)
        return ""

    # ────────── 详情页选集 ──────────
    @staticmethod
    def _detail_episodes(html, slug):
        nums = set()
        for n in re.findall(r'/play/' + re.escape(slug) + r'/(\d+)', html):
            try:
                nums.add(int(n))
            except Exception:
                pass
        return sorted(nums)

    @staticmethod
    def _detail_count(html):
        m = re.search(r'更新至(\d+)集', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        m = re.search(r'共(\d+)集', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return 0

    # ────────── 分类定义 ──────────
    def homeContent(self, filter):
        return {
            "class": [
                {"type_name": "推荐", "type_id": "home"},
                {"type_name": "原创", "type_id": "yuanchuang"},
                {"type_name": "魔改", "type_id": "mogai"},
                {"type_name": "AI漫剧", "type_id": "manju"},
                {"type_name": "真人短剧", "type_id": "zhenren"},
                {"type_name": "AI短剧", "type_id": "aiduanju"},
                {"type_name": "刷剧", "type_id": "feed"},
                {"type_name": "分类", "type_id": "browse"},
            ]
        }

    # ────────── 首页 ──────────
    def homeVideoContent(self):
        html = self._get("/")
        items, _ = self._nuxt_items(html)
        videos = self._cards_from_items(items)
        _dbg("home items:", len(videos))
        return {"list": videos}

    # ────────── 分页 URL ──────────
    @staticmethod
    def _page_url(tid, pg):
        if tid == "home" or not tid:
            return "/" if pg <= 1 else "/page-%d" % pg
        base = "/" + tid
        if pg <= 1:
            return base
        return "%s/page-%d" % (base, pg)

    # ────────── 分类 + 翻页 ──────────
    def categoryContent(self, tid, pg, flt, extend):
        pg = int(pg or 1)
        html = self._get(self._page_url(tid, pg))
        items, page = self._nuxt_items(html)
        videos = self._cards_from_items(items)
        if not videos and pg == 1:
            home_html = self._get("/")
            items2, _ = self._nuxt_items(home_html)
            videos = self._cards_from_items(items2)

        total_pages = int(page.get("total_pages", 1)) if page else 1
        if total_pages < 1:
            total_pages = 1
        page_size = int(page.get("page_size", 30)) if page else 30
        total = int(page.get("total", len(videos))) if page else len(videos)

        return {
            "list": videos,
            "page": pg,
            "pagecount": total_pages,
            "limit": page_size,
            "total": total,
        }

    # ────────── 详情 ──────────
    def detailContent(self, ids):
        raw = ids[0] if isinstance(ids, list) else ids
        slug = raw.replace("drama_", "")
        m = re.search(r'(dj-[a-zA-Z0-9]+)', slug)
        if m:
            slug = m.group(1)

        html = self._get("/drama/" + slug)
        if len(html) < 200:
            return {"list": []}

        # 标题
        title = ""
        m = re.search(r'<div class="mt-\[1\.2rem\][^>]*>.*?<p[^>]*>([^<]+)</p>', html, re.S)
        if m:
            title = _clean(m.group(1))
        if not title:
            m = re.search(r'<h1>([^<]+)</h1>', html)
            if m:
                title = _clean(m.group(1))
        if not title:
            items, _ = self._nuxt_items(html)
            for it in items:
                if it.get("slug") == slug:
                    title = _clean(it.get("title", ""))
                    break
        if not title:
            title = slug

        # 封面：只信 __NUXT_DATA__
        pic = self._detail_cover(html, slug)

        # 集数
        cnt = self._detail_count(html)
        if cnt < 1:
            items, _ = self._nuxt_items(html)
            for it in items:
                if it.get("slug") == slug:
                    n = it.get("latest_episode_number") or it.get("published_episode_count") or 0
                    try:
                        cnt = max(cnt, int(n))
                    except Exception:
                        pass
                    break

        # 选集
        nums = self._detail_episodes(html, slug)
        if nums:
            eps = ["第%d集$ep_%s_%d" % (n, slug, n) for n in nums]
        elif cnt > 0:
            eps = ["第%d集$ep_%s_%d" % (n, slug, n) for n in range(1, cnt + 1)]
        else:
            eps = ["第1集$ep_%s_1" % slug]

        _dbg("detail slug=", slug, "title=", title, "pic=", pic[:60] if pic else "EMPTY",
             "cnt=", cnt, "eps=", len(eps))

        return {
            "list": [{
                "vod_id": "drama_" + slug,
                "vod_name": title,
                "vod_pic": pic,
                "vod_play_from": "橙果短剧",
                "vod_play_url": "#".join(eps),
                "vod_remarks": ("更新至%d集" % cnt) if cnt else "",
            }]
        }

    # ────────── 播放 ──────────
    def playerContent(self, flag, id, vipFlags):
        try:
            _, slug, num = id.split("_")
        except Exception as e:
            _dbg("player id err:", e, id)
            return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

        html = self._get("/play/" + slug + "/" + num)
        if len(html) < 200:
            return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

        cand = []

        # 1) __NUXT_DATA__ 原始文本
        nuxt_raw = self._nuxt_raw(html)
        if nuxt_raw:
            for u in re.findall(r'(https?:\\?/\\?/[^\s"\\\']+?\.m3u8[^\s"\\\']*)', nuxt_raw):
                cand.append(u)
            for u in re.findall(r'"url":"(https?:\\?/\\?/[^"]+\.m3u8[^"]*)"', nuxt_raw):
                cand.append(u)

        # 2) HTML 多层兜底
        for u in re.findall(r'(https?:\\?/\\?/[^\s"\'\\)]+?\.m3u8[^\s"\'\\)]*)', html):
            cand.append(u)
        for u in re.findall(r'https?://[^\s"\'\\)]+\.m3u8[^\s"\'\\)]*', html):
            cand.append(u)
        for u in re.findall(r'"[^"]*\.m3u8[^"]*"', html):
            cand.append(u.strip('"'))
        m = re.search(r'<meta property="og:video(?::secure_url)?" content="([^"]+\.m3u8)"', html)
        if m:
            cand.append(m.group(1))
        m = re.search(r'<video[^>]*src="([^"]+\.m3u8)"', html, re.I)
        if m:
            cand.append(m.group(1))
        m = re.search(r'data-src="([^"]+\.m3u8)"', html)
        if m:
            cand.append(m.group(1))

        for raw in cand:
            u = _de_esc(raw)
            u = u.replace('\\"', '"').strip('"\'\\ ').rstrip('\",]}')
            if '.m3u8' in u and u.startswith('http'):
                _dbg("m3u8 ok:", u[:90])
                return {
                    "parse": 0,
                    "url": u,
                    "header": {
                        "User-Agent": UA,
                        "Referer": "https://chengguodj.com/",
                        "Origin": "https://chengguodj.com",
                    }
                }

        _dbg("未找到 m3u8 slug=", slug, "num=", num, "html_len=", len(html))
        _dbg("head:", html[:150].replace("\n", " "))
        return {"parse": 0, "url": "", "header": {"User-Agent": UA}}

    # ────────── 搜索 ──────────
    def searchContent(self, key, quick, pg="1"):
        pg = int(pg or 1)
        key = str(key)

        videos = []
        page = {}
        for path in (
            "/search?s=" + urllib.parse.quote(key),
            "/search/" + urllib.parse.quote(key),
        ):
            html = self._get(path)
            if not html:
                continue
            items, page = self._nuxt_items(html)
            videos = self._cards_from_items(items)
            if videos:
                break

        if not videos and pg == 1:
            home_html = self._get("/")
            items, _ = self._nuxt_items(home_html)
            videos = self._cards_from_items(items)

        total_pages = int(page.get("total_pages", 1)) if page else 1
        if total_pages < 1:
            total_pages = 1
        return {
            "list": videos,
            "page": pg,
            "pagecount": total_pages,
            "limit": int(page.get("page_size", 30)) if page else 30,
            "total": int(page.get("total", len(videos))) if page else len(videos),
        }

    def localProxy(self, param):
        return None

    def isVideoFormat(self, url):
        return bool(url) and (".m3u8" in url or url.lower().endswith((".mp4", ".ts")))

    def manualVideoCheck(self):
        return False


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
