# coding=utf-8
"""
目标站: 共和国动漫 (www.ghgdm.com)
站点类型: WordPress 动漫站 (传统HTML渲染)
功能: 首页推荐、分类、搜索、详情、播放
优化: 双线路支持 (ghgyun / dmyun)，播放加载速度优化
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://www.ghgdm.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.timeout = 15
        self.categories = [
            {"type_id": "1", "type_name": "中国动漫"},
            {"type_id": "2", "type_name": "日本动漫"},
            {"type_id": "3", "type_name": "欧美动漫"},
            {"type_id": "4", "type_name": "动漫电影"},
        ]
        self.max_recursion = 3
        self._play_cache = {}  # 缓存已解析的播放地址

    def getName(self):
        return "共和国动漫"

    def _fetch(self, url):
        try:
            resp = self.fetch(url, headers=self.headers, timeout=self.timeout)
            if resp:
                return resp.text
        except Exception as e:
            print(f"[共和国动漫] 请求失败: {e}")
        return None

    def _fix_url(self, url):
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return self.site_url + url
        return url

    def _extract_vod_id(self, href):
        if not href:
            return None
        match = re.search(r'/d/(\d+)\.html', href)
        if match:
            return match.group(1)
        match = re.search(r'/m/(\d+)-\d+-\d+\.html', href)
        if match:
            return match.group(1)
        return None

    def _parse_video_cards(self, html, limit=0):
        videos = []
        if not html:
            return videos
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select('.TPostMv, .TPost')
        if not items:
            items = soup.select('a[href*="/d/"]')

        seen = set()
        for item in items:
            a = item if item.name == "a" else item.find("a")
            if not a:
                continue
            href = a.get("href", "")
            vod_id = self._extract_vod_id(href)
            if not vod_id or vod_id in seen:
                continue
            seen.add(vod_id)

            title_elem = item.select_one('h2.Title, .Title, h2')
            title = title_elem.get_text(strip=True) if title_elem else ""
            if not title:
                title = a.get("title", "")
            if not title:
                continue

            img = item.select_one('img')
            pic = ""
            if img:
                pic = img.get('data-original') or img.get('src', "")
            pic = self._fix_url(pic)

            remark_elem = item.select_one('.Qlty, .vod-remarks, .remarks')
            remark = remark_elem.get_text(strip=True) if remark_elem else ""

            videos.append({
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remark,
            })

            if limit and len(videos) >= limit:
                break

        return videos

    def _parse_detail(self, html, vod_id):
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        vod = {
            "vod_id": vod_id,
            "vod_name": "",
            "vod_pic": "",
            "vod_content": "",
            "vod_year": "",
            "vod_area": "",
            "vod_actor": "",
            "vod_director": "",
            "vod_remarks": "",
            "vod_type": "",
            "vod_play_from": "",
            "vod_play_url": "",
        }

        # 标题
        title_elem = soup.select_one('h1') or soup.select_one('.entry-title')
        if title_elem:
            vod["vod_name"] = title_elem.get_text(strip=True)
        if not vod["vod_name"]:
            og_title = soup.select_one('meta[property="og:title"]')
            if og_title:
                vod["vod_name"] = og_title.get("content", "").strip()

        # 封面
        og_img = soup.select_one('meta[property="og:image"]')
        if og_img:
            vod["vod_pic"] = self._fix_url(og_img.get("content", ""))
        if not vod["vod_pic"]:
            img = soup.select_one('.Image img, .post-thumbnail img')
            if img:
                vod["vod_pic"] = self._fix_url(img.get('data-original') or img.get('src', ""))

        # 简介
        desc_elem = soup.select_one('.Description, .entry-content p')
        if desc_elem:
            vod["vod_content"] = desc_elem.get_text(" ", strip=True)
        if not vod["vod_content"]:
            meta_desc = soup.select_one('meta[name="description"]')
            if meta_desc:
                vod["vod_content"] = meta_desc.get("content", "").strip()

        # 元数据
        info_elem = soup.select_one('.Info, .entry-meta')
        if info_elem:
            text = info_elem.get_text(strip=True)
            year_match = re.search(r'(\d{4})', text)
            if year_match:
                vod["vod_year"] = year_match.group(1)
            actor_match = re.search(r'主演[:：]\s*([^导演]+)', text)
            if actor_match:
                vod["vod_actor"] = actor_match.group(1).strip()
            director_match = re.search(r'导演[:：]\s*([^主]+)', text)
            if director_match:
                vod["vod_director"] = director_match.group(1).strip()

        area_elem = soup.select_one('.area, .region')
        if area_elem:
            vod["vod_area"] = area_elem.get_text(strip=True)

        # ================= 多线路提取（双线路） =================
        play_from = []
        play_url = []

        # 查找所有线路标签（ghgyun / dmyun）
        nav_items = soup.select('.playlist-nav-item')
        line_names = []
        for nav in nav_items:
            name = nav.get_text(strip=True)
            if name:
                line_names.append(name)

        # 查找所有剧集列表（对应每个线路）
        tab_contents = soup.select('.ewave-tab-content')
        if tab_contents and len(tab_contents) == len(line_names):
            for idx, tab in enumerate(tab_contents):
                line_name = line_names[idx] if idx < len(line_names) else f"线路{idx+1}"
                episodes = []
                for a in tab.select('a[href*="/m/"]'):
                    href = a.get("href", "")
                    if not href or "javascript:" in href:
                        continue
                    ep_name = a.get_text(strip=True)
                    if not ep_name:
                        match = re.search(r'/m/\d+-\d+-(\d+)\.html', href)
                        if match:
                            ep_name = f"第{match.group(1)}集"
                        else:
                            ep_name = "播放"
                    full_url = self._fix_url(href)
                    episodes.append(f"{ep_name}${full_url}")
                if episodes:
                    play_from.append(line_name)
                    play_url.append("#".join(episodes))

        # 如果上述方法未提取到，回退到全局 /m/ 链接（单线路）
        if not play_from:
            play_links = soup.select('a[href*="/m/"]')
            if play_links:
                episodes = []
                for a in play_links:
                    href = a.get("href", "")
                    if not href or "javascript:" in href:
                        continue
                    ep_name = a.get_text(strip=True)
                    if not ep_name:
                        match = re.search(r'/m/\d+-\d+-(\d+)\.html', href)
                        if match:
                            ep_name = f"第{match.group(1)}集"
                        else:
                            ep_name = "播放"
                    full_url = self._fix_url(href)
                    episodes.append(f"{ep_name}${full_url}")
                if episodes:
                    play_from.append("默认线路")
                    play_url.append("#".join(episodes))

        vod["vod_play_from"] = "$$$".join(play_from) if play_from else "默认线路"
        vod["vod_play_url"] = "$$$".join(play_url) if play_url else ""

        return vod

    def _parse_play_page(self, html):
        """从播放页提取视频链接（可能是中间页）"""
        if not html:
            return None

        # 1. 查找 var now
        now_match = re.search(r'var\s+now\s*=\s*"([^"]+)"', html)
        if now_match:
            return now_match.group(1)

        # 2. player_aaaa
        player_match = re.search(r'player_aaaa\s*=\s*({[^;]+})', html)
        if player_match:
            try:
                data = json.loads(player_match.group(1))
                return data.get("url", "")
            except:
                pass

        # 3. iframe
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            return iframe.group(1)

        # 4. 直接匹配 m3u8/mp4
        m3u8 = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
        if m3u8:
            return m3u8.group(1)
        mp4 = re.search(r'(https?://[^\s"\']+\.mp4[^\s"\']*)', html)
        if mp4:
            return mp4.group(1)

        return None

    # ========== TVBox 接口 ==========

    def homeContent(self, filter=False):
        html = self._fetch(self.site_url + "/")
        result = {"class": self.categories, "list": [], "filters": {}}
        if not html:
            return result
        videos = self._parse_video_cards(html, limit=30)
        result["list"] = videos[:30]
        return result

    def homeVideoContent(self):
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter=False, extend=None):
        page = int(pg) if pg else 1
        tid = str(tid)
        if page == 1:
            url = f"{self.site_url}/h/{tid}.html"
        else:
            url = f"{self.site_url}/h/{tid}/page/{page}.html"
            if not self._fetch(url):
                url = f"{self.site_url}/h/{tid}_{page}.html"

        html = self._fetch(url)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        videos = self._parse_video_cards(html)
        pagecount = page
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.select('.page-numbers, .pagination a, .page a')
        for a in pagination:
            text = a.get_text(strip=True)
            if text.isdigit():
                pagecount = max(pagecount, int(text))

        return {
            "list": videos,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(videos) * pagecount,
        }

    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, list) else ids
        if not vid:
            return {"list": []}
        url = f"{self.site_url}/d/{vid}.html"
        html = self._fetch(url)
        if not html:
            return {"list": []}
        vod = self._parse_detail(html, vid)
        if not vod or not vod.get("vod_name"):
            return {"list": []}
        return {"list": [vod]}

    def searchContent(self, key, quick=False, pg="1"):
        page = int(pg) if pg else 1
        encoded = urllib.parse.quote(key)
        url = f"{self.site_url}/search.php?searchword={encoded}&page={page}"
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": page, "pagecount": 1}
        videos = self._parse_video_cards(html)
        pagecount = page
        soup = BeautifulSoup(html, "html.parser")
        pagination = soup.select('.page-numbers, .pagination a, .page a')
        for a in pagination:
            text = a.get_text(strip=True)
            if text.isdigit():
                pagecount = max(pagecount, int(text))
        return {"list": videos, "page": page, "pagecount": pagecount}

    # ==================== 播放解析（缓存优化 + 快速返回） ====================
    def playerContent(self, flag, id, vipFlags=None):
        """
        播放解析，使用缓存避免重复解析，并优化递归深度
        """
        play_url = self._fix_url(id)

        # 检查缓存
        cache_key = play_url
        if cache_key in self._play_cache:
            cached = self._play_cache[cache_key]
            if cached:
                return cached

        # 尝试直接返回播放页，让播放器自行处理（加快速度）
        # 如果播放页URL本身是视频直链，直接返回
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', play_url, re.I):
            result = {
                "parse": 0,
                "url": play_url,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.site_url + "/"
                }
            }
            self._play_cache[cache_key] = result
            return result

        # 非直链，尝试递归解析
        result = self._resolve_play_url(play_url, depth=0, cache_key=cache_key)
        self._play_cache[cache_key] = result
        return result

    def _resolve_play_url(self, url, depth, cache_key):
        """递归解析，带深度限制和缓存"""
        if depth > self.max_recursion:
            return {"parse": 1, "url": url, "header": self.headers}

        # 如果已经是视频直链，直接返回
        if re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I):
            return {
                "parse": 0,
                "url": url,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.site_url + "/"
                }
            }

        # 请求当前 URL
        html = self._fetch(url)
        if not html:
            return {"parse": 1, "url": url, "header": self.headers}

        # 从页面中提取可能的视频链接
        next_url = self._parse_play_page(html)
        if next_url:
            if not next_url.startswith('http'):
                next_url = self._fix_url(next_url)
            if next_url == url:
                return {"parse": 1, "url": url, "header": self.headers}
            # 继续递归
            return self._resolve_play_url(next_url, depth + 1, cache_key)

        # 如果页面内还有 iframe，尝试提取
        iframe = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if iframe:
            iframe_url = self._fix_url(iframe.group(1))
            if iframe_url != url:
                return self._resolve_play_url(iframe_url, depth + 1, cache_key)

        # 兜底：交给客户端解析
        return {"parse": 1, "url": url, "header": self.headers}

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv)(\?|$)', url, re.I))

    def manualVideoCheck(self):
        return True

    def localProxy(self, param):
        pass


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["dmyun"]
_TVBOX_LINE_ORDER = ["dmyun", "ghgyun"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "bfzy", "rrcdnbf", "fengbao", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "JS", "JY", "KC", "LZ", "MT", "MY", "NN", "SD", "SN", "UK", "WJ", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼"]
_TVBOX_ZY_NEG = ["官方", "自营", "自有", "正版"]

def _tvbox_is_zy_url(url, flag=''):
    import re, urllib.parse
    u = str(url or '')
    f = str(flag or '').strip()
    if re.search(_TVBOX_ZY_API, u, re.I):
        return True
    # 播放地址可能是多集拼接串：'第01集$https://a.com/x.m3u8#第02集$https://b.com/y.m3u8'
    # 必须逐段提取 URL 再取 host，不能对整个串 urlparse（取不到 host）。
    hosts = set()
    for seg in re.split(r'[#$]', u):
        seg = seg.strip()
        if seg.startswith('http://') or seg.startswith('https://'):
            try:
                h = (urllib.parse.urlparse(seg).hostname or '').lower()
            except Exception:
                h = ''
            if h:
                hosts.add(h)
    for h in hosts:
        for p in _TVBOX_ZY_CDN:
            if re.search(r'(^|[.\-_])' + re.escape(p), h, re.I):
                return True
        if re.search(r'(^|[.\-_])lzv\d+', h, re.I):
            return True
    if hosts:
        return False  # 有真实 host 但没命中 CDN → 自有线路，不靠名字
    # 无 host（占位符型脚本，detail 给相对路径/id）：回退到线路名判定。
    # 官方/自营字样优先豁免，避免误伤。
    if any(neg in f for neg in _TVBOX_ZY_NEG):
        return False
    if f.upper() in _TVBOX_ZY_CODES:
        return True
    if any(kw in f for kw in _TVBOX_ZY_KW):
        return True
    if re.search(r'(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|MY)(?:线路|线)', f):
        return True
    return False

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
    if _TVBOX_ZY_ENABLED:
        keep = [(f, u) for f, u in zip(parts_from, parts_url)
                if f not in drop and not _tvbox_is_zy_url(u, f)]
    else:
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
