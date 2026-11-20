# -*- coding: utf-8 -*-
# 看戏影视 (www.kanxiya.com) - TVBox/Drpy 爬虫
# 模板: maccms / stui
import re
import json
import urllib.parse
from bs4 import BeautifulSoup
from base.spider import Spider as BaseSpider


class Spider(BaseSpider):
    def init(self, extend=""):
        self.host = "https://www.kanxiya.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def getName(self):
        return '看戏影视'

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def homeContent(self, filter):
        return {"class": [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "综艺"},
            {"type_id": "4", "type_name": "动漫"},
        ], "filters": self._build_filters()}

    def _build_filters(self):
        area = [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"}, {"n": "新加坡", "v": "新加坡"},
                {"n": "马来西亚", "v": "马来西亚"}, {"n": "印度", "v": "印度"}, {"n": "英国", "v": "英国"},
                {"n": "法国", "v": "法国"}, {"n": "加拿大", "v": "加拿大"}, {"n": "西班牙", "v": "西班牙"},
                {"n": "俄罗斯", "v": "俄罗斯"}, {"n": "其它", "v": "其它"}]
        year = [{"n": "全部", "v": ""}, {"n": "2026", "v": "2026"}, {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"}, {"n": "2023", "v": "2023"}, {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"}, {"n": "2020", "v": "2020"}, {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"}, {"n": "2017", "v": "2017"}, {"n": "2016", "v": "2016"},
                {"n": "2015", "v": "2015"}, {"n": "2014", "v": "2014"}, {"n": "2013", "v": "2013"},
                {"n": "2012", "v": "2012"}, {"n": "2011", "v": "2011"}, {"n": "2010", "v": "2010"}]
        # class 实际是把 tid 切换到子分类 id
        return {
            "1": [
                {"key": "class", "name": "类型",
                 "value": [{"n": "全部", "v": "1"}, {"n": "动作片", "v": "5"}, {"n": "喜剧片", "v": "6"},
                           {"n": "爱情片", "v": "7"}, {"n": "科幻片", "v": "8"}, {"n": "恐怖片", "v": "9"},
                           {"n": "剧情片", "v": "10"}, {"n": "战争片", "v": "11"}]},
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": year},
            ],
            "2": [
                {"key": "class", "name": "类型",
                 "value": [{"n": "全部", "v": "2"}, {"n": "国产剧", "v": "12"}, {"n": "港台剧", "v": "13"},
                           {"n": "欧美剧", "v": "14"}, {"n": "日韩剧", "v": "15"}, {"n": "海外剧", "v": "16"}]},
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": year},
            ],
            "3": [
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": year},
            ],
            "4": [
                {"key": "area", "name": "地区", "value": area},
                {"key": "year", "name": "年份", "value": year},
            ],
        }

    def homeVideoContent(self):
        html = self._fetch('/')
        return {"list": self._parse_list(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        # 取筛选参数：extend 优先，回退 filter
        args = {}
        if isinstance(extend, dict):
            for k, v in extend.items():
                if v:
                    args[k] = str(v)
        if isinstance(filter, dict):
            for k, v in filter.items():
                if v and k not in args:
                    args[k] = str(v)
        # class 直接切换 tid
        route_tid = args.get('class', str(tid))
        area = args.get('area', '')
        year = args.get('year', '')
        # URL: /tags/{tid}-{area}-------{page}---{year}.html  (12 段, 11 个 '-')
        # 实测: 1--------1--- / 1-大陆-------1--- / 1--------1---2026
        segs = [route_tid, area, '', '', '', '', '', '', str(page), '', '', year]
        url = '/tags/' + '-'.join(segs) + '.html'
        html = self._fetch(url)
        items = self._parse_list(html)
        # 解析总页数：取"尾页"链接中的页码
        pagecount = page
        if items:
            m = re.search(r'/tags/[^.]*?-(\d+)---[^.]*\.html', html)
            # 优先找尾页
            tail = re.search(r'<a[^>]*>尾页</a>', html)
            if tail:
                mm = re.search(r'-(\d+)---', tail.group(0))
                if not mm:
                    mm = re.search(r'-(\d+)---', html[tail.start():tail.start() + 200])
                if mm:
                    pagecount = int(mm.group(1))
            if pagecount < page:
                pagecount = page
        else:
            pagecount = page - 1 if page > 1 else 1
        return {"list": items, "page": page, "pagecount": pagecount,
                "limit": 24, "total": pagecount * 24}

    def detailContent(self, ids):
        result = {"list": []}
        vid = ids[0].split(',')[0].strip()
        try:
            html = self._fetch(f'/post/{vid}.html')
            if not html:
                return result
            soup = BeautifulSoup(html, 'html.parser')
            # 标题
            vod_name = ''
            h1 = soup.select_one('h1.title') or soup.select_one('.stui-content__detail h1')
            if h1:
                vod_name = h1.get_text(strip=True)
            # 封面
            vod_pic = ''
            img = soup.select_one('.stui-content__thumb img') or soup.select_one('.stui-vodlist__thumb img')
            if img:
                vod_pic = self._fix_pic(img.get('data-original') or img.get('src') or '')
            # 详情字段: 状态/年份/类型/地区/更新/导演 在 p.data; 演员 在 p.desc.detail
            vod_year = vod_area = vod_remarks = vod_director = vod_actor = vod_content = ''
            det = soup.select_one('.stui-content__detail')
            if det:
                for p in det.select('p'):
                    lab_el = p.select_one('.data2')
                    if not lab_el:
                        continue
                    lab = lab_el.get_text(strip=True)
                    if lab.startswith('演员'):
                        actor_el = p.select_one('.data5') or p
                        vod_actor = actor_el.get_text(' ', strip=True)
                    elif lab.startswith('状态'):
                        vod_remarks = p.get_text(' ', strip=True).replace(lab, '', 1).strip()
                    elif lab.startswith('年份'):
                        vod_year = p.get_text(' ', strip=True).replace(lab, '', 1).strip()
                    elif lab.startswith('地区'):
                        vod_area = p.get_text(' ', strip=True).replace(lab, '', 1).strip()
                    elif lab.startswith('导演'):
                        vod_director = p.get_text(' ', strip=True).replace(lab, '', 1).strip()
            # 剧情
            content_el = soup.select_one('.detail-content') or soup.select_one('.detail-sketch')
            if content_el:
                vod_content = content_el.get_text(' ', strip=True)
            # 播放源
            play_from, play_url = [], []
            for hd in soup.select('.stui-vodlist__head'):
                ul = hd.select_one('ul.stui-content__playlist')
                if not ul:
                    continue
                h4 = hd.select_one('h4')
                src_name = h4.get_text(' ', strip=True) if h4 else ''
                src_name = re.sub(r'\s+', '', src_name)
                if not src_name:
                    continue
                ep_list = []
                for a in ul.select('li a'):
                    href = a.get('href', '')
                    m = re.search(r'/play/(.*?)\.html', href)
                    if m:
                        ep_list.append(f'{a.get_text(strip=True)}${m.group(1)}')
                if ep_list:
                    play_from.append(src_name)
                    play_url.append('#'.join(ep_list))
            result["list"].append({
                "vod_id": vid, "vod_name": vod_name, "vod_pic": vod_pic,
                "vod_year": vod_year, "vod_area": vod_area, "vod_remarks": vod_remarks,
                "vod_director": vod_director, "vod_actor": vod_actor,
                "vod_content": vod_content,
                "vod_play_from": "$$$".join(play_from),
                "vod_play_url": "$$$".join(play_url),
            })
        except Exception as e:
            print(e)
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            decoded = urllib.parse.unquote(key)
        except Exception:
            decoded = key
        page = int(pg) if pg else 1
        # /search/{关键词}-------------.html  (14 段, 关键词后 13 个 '-')
        segs = [urllib.parse.quote(decoded)] + [''] * 13
        url = '/search/' + '-'.join(segs) + '.html'
        html = self._fetch(url)
        items = self._parse_list(html)
        return {"list": items, "page": page, "pagecount": 1, "limit": 24, "total": len(items)}

    def playerContent(self, flag, id, vipFlags):
        url = id if id.startswith('http') else f'{self.host}/play/{id}.html'
        try:
            html = self._fetch(url)
            if html:
                pd = self._extract_player_data(html)
                if pd:
                    play_url = pd.get('url', '')
                    if play_url and play_url.startswith('http') and (
                            play_url.endswith('.m3u8') or play_url.endswith('.mp4')):
                        return {"parse": 0, "url": play_url, "header": {
                            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
                                          'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                                          'Version/16.0 Mobile/15E148 Safari/604.1'}}
        except Exception as e:
            print(e)
        return {"parse": 1, "url": url}

    def localProxy(self, param=''):
        return {}

    # ---------- helpers ----------
    def _fetch(self, url):
        try:
            if not url.startswith('http'):
                url = self.host + url
            rsp = self.fetch(url, headers=self.headers)
            return rsp.text if rsp else ''
        except Exception:
            return ''

    def _fix_pic(self, u):
        if not u:
            return ''
        u = u.replace('&amp;', '&')
        if u.startswith('//'):
            return 'https:' + u
        if u.startswith('/'):
            return self.host + u
        return u

    def _parse_list(self, html):
        videos, seen = [], set()
        if not html:
            return videos
        soup = BeautifulSoup(html, 'html.parser')
        for box in soup.select('ul.stui-vodlist li .stui-vodlist__box'):
            a = box.select_one('a.stui-vodlist__thumb')
            if not a:
                continue
            href = a.get('href', '')
            m = re.search(r'/post/(\d+)\.html', href)
            if not m:
                continue
            vod_id = m.group(1)
            if vod_id in seen:
                continue
            seen.add(vod_id)
            vod_name = a.get('title', '') or ''
            if not vod_name:
                img = a.select_one('img')
                vod_name = img.get('alt', '') if img else ''
            vod_pic = self._fix_pic(a.get('data-original', '') or a.get('data-src', ''))
            remark_el = a.select_one('.pic-text')
            vod_remarks = remark_el.get_text(strip=True) if remark_el else ''
            videos.append({
                "vod_id": vod_id, "vod_name": vod_name.strip(),
                "vod_pic": vod_pic, "vod_remarks": vod_remarks,
            })
        return videos

    def _extract_player_data(self, html):
        # 平衡花括号提取 player_data = {...}
        m = re.search(r'player_data\s*=\s*\{', html)
        if not m:
            return None
        start = m.end() - 1
        depth = 0
        in_str = False
        esc = False
        end = None
        for i in range(start, len(html)):
            c = html[i]
            if in_str:
                if esc:
                    esc = False
                elif c == '\\':
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
        if not end:
            return None
        try:
            return json.loads(html[start:end])
        except Exception as e:
            print(e)
            return None


if __name__ == '__main__':
    sp = Spider()
    sp.init()
    # 首页
    home = sp.homeVideoContent()
    print('首页数量:', len(home['list']))
    if home['list']:
        print('首页首条:', home['list'][0])
    # 分类(电影第1页)
    cat = sp.categoryContent('1', '1', {}, {})
    print('分类数量:', len(cat['list']), '页数:', cat['pagecount'])
    if cat['list']:
        print('分类首条:', cat['list'][0])
    # 搜索
    sea = sp.searchContent('唐探', '')
    print('搜索数量:', len(sea['list']))
    if sea['list']:
        print('搜索首条:', sea['list'][0])
        # 详情 + 播放
        det = sp.detailContent([sea['list'][0]['vod_id']])
        print('详情:', det['list'][0]['vod_name'], '| 源:', det['list'][0]['vod_play_from'])
        # 取第一个剧集 id 测试播放
        play_url = det['list'][0]['vod_play_url']
        if play_url:
            first_ep = play_url.split('#')[0]
            ep_id = first_ep.split('$')[-1]
            print('测试播放 id:', ep_id)
            pc = sp.playerContent('', ep_id, [])
            print('播放结果:', pc)


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["无尽云", "暴风云", "索尼云", "红牛云", "量子云"]
_TVBOX_LINE_ORDER = ["量子云", "红牛云", "索尼云", "暴风云"]

_TVBOX_ZY_ENABLED = True
_TVBOX_ZY_CDN = ["ffzy", "feifei", "yzzy", "cdnlz", "lzzy", "bfzy", "rrcdnbf", "fengbao", "ffvip", "7bbffvip", "modujx", "modudm", "mujizybf", "jisuzy", "jisuzyv", "zuidazy", "wsyzym3u8", "xluuss", "bfvvs", "dytt", "phimgood", "ryiplay", "ryplay", "ruyijx", "gsuus", "guangsuzy", "maowushi", "ukuzi", "niuniuzy", "rstu6", "mzm3u8", "ppqrrs", "qqqrst", "hhuus"]
_TVBOX_ZY_API = "/api\\.php/(provide|providedown)|/inc/api_mac|provide/vod|providedown/vod"
_TVBOX_ZY_CODES = ["BD", "BF", "FF", "HH", "HN", "JS", "JY", "KC", "LZ", "MT", "MY", "NN", "SD", "SN", "UK", "WJ", "XL", "YZ"]
_TVBOX_ZY_KW = ["量子", "非凡", "暴风", "魔都", "极速", "最大", "蜗牛", "影库", "红牛", "新浪", "光速", "如意", "卧龙", "无界", "人尽", "牛牛", "猫屋", "电影天堂", "天堂", "4K资源", "索尼", "无尽", "魔爪", "猫眼", "快车", "百度"]
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
