import sys
import re
import json
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
requests.packages.urllib3.disable_warnings()

from base.spider import Spider

class Spider(Spider):
    # ========== 插件基础配置 ==========
    def getName(self):
        return "黑猫动漫"

    # ========== 初始化全局配置 ==========
    def init(self, extend=""):
        super().init(extend)
        self.site_url = "https://www.bmmdmm.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
            "Referer": self.site_url,
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        self.sess = requests.Session()
        self.sess.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.sess.mount("http://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.page_size = 24

    # ========== 通用请求方法 ==========
    def fetch(self, url, timeout=10):
        try:
            res = self.sess.get(url, headers=self.headers, timeout=timeout, verify=False)
            res.encoding = "utf-8"
            return res
        except Exception as e:
            return None

    # ========== 首页分类接口 ==========
    def homeContent(self, filter):
        cate_list = [
            {"type_name": "最新更新", "type_id": "order=更新时间"},
            {"type_name": "日本动漫", "type_id": "region=日本"},
            {"type_name": "国产动漫", "type_id": "region=中国"},
            {"type_name": "美国动漫", "type_id": "region=美国"},
            {"type_name": "剧场版", "type_id": "genre=剧场版"},
            {"type_name": "OVA版", "type_id": "genre=OVA"},
            {"type_name": "连载动漫", "type_id": "status=连载"},
            {"type_name": "完结动漫", "type_id": "status=完结"}
        ]
        return {"class": cate_list}

    # ========== 分类列表接口 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        page_index = pg - 1
        list_url = f"{self.site_url}/list/?{tid}&pagesize=24&pageindex={page_index}"
        res = self.fetch(list_url)
        video_list = []
        
        if res and res.ok:
            html = res.text
            lpic_match = re.search(r'<div class="lpic">\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
            if lpic_match:
                ul_html = lpic_match.group(1)
                for li in re.finditer(r'<li>(.*?)</li>', ul_html, re.S):
                    li_html = li.group(1)
                    vod_id = re.search(r'<a href=["\'](/show/\d+\.html)["\']', li_html)
                    vod_name = re.search(r'<h2>.*?<a href=["\'][^"\']*["\'] title=["\']([^"\']+)["\']', li_html, re.S)
                    if not vod_name:
                        vod_name = re.search(r'<h2>.*?>([^<]+)</a>', li_html, re.S)
                    vod_pic = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', li_html)
                    vod_remarks = re.search(r'<font color="red">(.*?)</font>', li_html)
                    
                    if vod_id and vod_name and vod_pic:
                        video_list.append({
                            "vod_id": self.site_url + vod_id.group(1),
                            "vod_name": vod_name.group(1).strip(),
                            "vod_pic": vod_pic.group(1).strip(),
                            "vod_remarks": vod_remarks.group(1).strip() if vod_remarks else "",
                            "style": {"type": "rect", "ratio": 1.33}
                        })
        
        pagecount = pg + 1 if len(video_list) == self.page_size else pg
        if res and res.ok:
            total_match = re.search(r'pageindex=(\d+)"[^>]*>尾页</a>', res.text)
            if total_match:
                pagecount = int(total_match.group(1)) + 1
        
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": 99999
        }

    # ========== 视频详情接口 ==========
    def detailContent(self, ids):
        vod_id = ids[0] if ids else ""
        if not vod_id:
            return {"list": [{"vod_name": "视频ID为空"}]}
        
        detail_url = vod_id
        res = self.fetch(detail_url)
        if not res or not res.ok:
            return {"list": [{"vod_id": vod_id, "vod_name": "视频详情解析失败"}]}
        
        html = res.text
        
        title_match = re.search(r'<h1>(.*?)</h1>', html, re.S)
        vod_name = title_match.group(1).strip() if title_match else "未知名称"
        vod_name = re.sub(r'<[^>]+>', '', vod_name)
        
        pic_match = re.search(r'<div class="thumb">.*?<img[^>]+src=["\']([^"\']+)["\']', html, re.S)
        vod_pic = pic_match.group(1).strip() if pic_match else ""
        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        
        desc_match = re.search(r'<div class="info">(.*?)</div>', html, re.S)
        vod_content = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else ""
        
        remarks_match = re.search(r'更新至[：:]?\s*(.*?)</p>', html, re.S)
        vod_remarks = remarks_match.group(1).strip() if remarks_match else ""
        vod_remarks = re.sub(r'<[^>]+>', '', vod_remarks)
        
        type_match = re.search(r'<label>类型:</label>.*?>([^<]+)</a>', html, re.S)
        type_name = type_match.group(1).strip() if type_match else ""
        
        # 播放线路与集数解析
        play_from_list = []
        play_url_list = []
        
        menu_matches = re.findall(r'<li[^>]*onClick="setTab\(0,\d+\)"[^>]*>(.*?)</li>', html, re.S)
        movurl_blocks = re.findall(r'<div class="movurl"[^>]*>\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
        
        for idx, block_html in enumerate(movurl_blocks):
            from_name = re.sub(r'<[^>]+>', '', menu_matches[idx]).strip() if idx < len(menu_matches) else f"播放{idx+1}"
            if not from_name:
                from_name = f"播放{idx+1}"
            play_from_list.append(from_name)
            
            ep_list = []
            for ep in re.finditer(r'<a href=["\'](/play/[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', block_html):
                ep_url = self.site_url + ep.group(1)
                ep_name = ep.group(2).strip()
                ep_list.append(f"{ep_name}${ep_url}")
            
            play_url_list.append("#".join(ep_list))
        
        if not play_from_list:
            return {"list": [{"vod_id": vod_id, "vod_name": "未找到播放线路"}]}
        
        detail_info = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_remarks": vod_remarks,
            "type_name": type_name,
            "vod_content": vod_content,
            # 核心修复：多线路分隔符必须用 $$$ 而不是 |
            "vod_play_from": "$$$".join(play_from_list),
            "vod_play_url": "$$$".join(play_url_list)
        }
        
        return {"list": [detail_info]}

    # ========== 搜索接口 ==========
    def searchContent(self, key, quick, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        page_index = pg - 1
        search_url = f"{self.site_url}/s_all?ex=1&kw={requests.utils.quote(key)}&pageindex={page_index}"
        res = self.fetch(search_url)
        video_list = []
        
        if res and res.ok:
            html = res.text
            lpic_match = re.search(r'<div class="lpic">\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
            if lpic_match:
                ul_html = lpic_match.group(1)
                for li in re.finditer(r'<li>(.*?)</li>', ul_html, re.S):
                    li_html = li.group(1)
                    vod_id = re.search(r'<a href=["\'](/show/\d+\.html)["\']', li_html)
                    vod_name = re.search(r'<h2>.*?<a href=["\'][^"\']*["\'] title=["\']([^"\']+)["\']', li_html, re.S)
                    if not vod_name:
                        vod_name = re.search(r'<h2>.*?>([^<]+)</a>', li_html, re.S)
                    vod_pic = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', li_html)
                    vod_remarks = re.search(r'<font color="red">(.*?)</font>', li_html)
                    
                    if vod_id and vod_name and vod_pic:
                        video_list.append({
                            "vod_id": self.site_url + vod_id.group(1),
                            "vod_name": vod_name.group(1).strip(),
                            "vod_pic": vod_pic.group(1).strip(),
                            "vod_remarks": vod_remarks.group(1).strip() if vod_remarks else "搜索结果",
                            "style": {"type": "rect", "ratio": 1.33}
                        })
        
        pagecount = pg + 1 if len(video_list) == self.page_size else pg
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": len(video_list) if len(video_list) < 99999 else 99999
        }

    # ========== 播放解析接口 ==========
    def playerContent(self, flag, id, vipFlags):
        play_url = id.split("$")[1] if "$" in id else id
        if not play_url:
            return {"parse": 0, "url": "", "header": self.headers}
        
        return {
            "parse": 1,
            "url": play_url,
            "header": self.headers
        }



# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = []
_TVBOX_LINE_ORDER = ["播放Ⅰ", "播放Ⅱ", "播放Ⅲ", "播放Ⅳ"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "lzcdn", "lz-cdn", "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8", "ppqrrs", "qqqrst", "hhuus", "bdzybf", "bfikuncdn", "wlcdn88", "dious", "ly166", "xgplay13", "taopianplay", "kuktxu", "2767.org", "892539"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "IK", "IQY", "JS", "JY", "KC", "LZ", "MT", "MY", "MZ", "NN", "PL", "RY", "SD", "SN", "TK", "UK", "WJ", "WL", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼", "无尽", "魔爪", "猫眼", "快车", "百度", "ikun", "速播", "站外", "西瓜", "淘宝片", "天空", "卧龙", "拍律", "xiguam3u8", "ikm3u8", "tpm3u8", "rym3u8", "taopian"]
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
                parsed = urllib.parse.urlparse(seg)
                h = (parsed.hostname or '').lower()
            except Exception:
                h = ''; parsed = None
            # 本地代理型脚本（如 APP影院1）：真实地址藏在 url= 参数里，
            # 需解码后再提取 host，否则只会拿到 127.0.0.1 而漏判。
            if parsed and h in ('127.0.0.1', 'localhost', '::1'):
                qs = urllib.parse.parse_qs(parsed.query)
                real = (qs.get('url') or [''])[0]
                if real.startswith('//'): real = 'https:' + real
                if real.startswith('http://') or real.startswith('https://'):
                    try:
                        rh = (urllib.parse.urlparse(real).hostname or '').lower()
                    except Exception:
                        rh = ''
                    if rh: hosts.add(rh)
            if h:
                hosts.add(h)
            # 中转缓存型：真实 URL 拼在路径里（/cache/https://cdn/...），
            # 取内层 host（如 47电影天堂 dl.gybkw.com/cache/https://c1.7bbffvip.com）。
            im = re.search(r'/(https?://[^/?#]+)', seg)
            if im:
                ih = re.match(r'https?://([^/?]+)', im.group(1))
                if ih:
                    hosts.add(ih.group(1).split(':')[0].lower())
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
    if re.search(r'(?i)\b(LZ|FF|BF|HF|HN|YZ|DY|MY|IK|WL|TK|IQY|XL|WJ|BD|DB|SB|SN|MZ|PL)(?:线路|线)', f):
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
