# -*- coding: utf-8 -*-

import re
import sys
from pyquery import PyQuery as pq

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.extend = extend

    def getName(self):
        return "毒舌影视"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    host = 'https://www.xnhrsb.com/'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; Mobile) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/114.0.0.0 Mobile Safari/537.36',
        'Referer': host,
    }

    # 对应 js 里的 class_name / class_url
    classes_config = [
        ("电影", "1"),
        ("电视剧", "2"),
        ("综艺", "3"),
        ("动漫", "4"),
        ("短剧", "5"),
        ("豆瓣", "duoban"),
    ]

    def homeContent(self, filter):
        result = {}
        classes = []
        vlist = []

        # 静态分类
        for name, tid in self.classes_config:
            classes.append({
                "type_name": name,
                "type_id": tid
            })

        # 首页推荐，沿用一级规则里的 .mrb ul li
        rsp = self.fetch(self.host, headers=self.headers)
        data = pq(rsp.text)

        # 一级: '.mrb&&ul li;.dytit&&Text;.lazy&&data-original;.hdinfo&&Text;a&&href'
        vlist.extend(self.getlist(data('.mrb ul li')))

        result['class'] = classes
        result['list'] = vlist
        return result

    def homeVideoContent(self):
        return {}

    def categoryContent(self, tid, pg, filter, extend):
        # js: url: '/dsshiyisw/fyclass--------fypage---.html'
        url = f'{self.host}dsshiyisw/{tid}--------{pg}---.html'
        rsp = self.fetch(url, headers=self.headers)
        data = pq(rsp.text)

        videos = self.getlist(data('.mrb ul li'))

        result = {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999
        }
        return result

    def detailContent(self, ids):
        vid = ids[0]
        if not vid.startswith('http'):
            if vid.startswith('/'):
                url = self.host.rstrip('/') + vid
            else:
                url = self.host.rstrip('/') + '/' + vid
        else:
            url = vid

        rsp = self.fetch(url, headers=self.headers)
        data = pq(rsp.text)

        # 二级: title/img/desc/content/tabs/lists
        # title: 'h1&&Text;.moviedteail_list li&&a&&Text'
        name = data('h1').text()

        info_list = data('.moviedteail_list li')

        def li_text(idx):
            return info_list.eq(idx).text() if idx < len(info_list) else ''

        # 参考 desc 顺序，大致映射
        # desc: '.moviedteail_list li:eq(3)&&Text;
        #        .moviedteail_list li:eq(2)&&Text;
        #        .moviedteail_list li:eq(1)&&Text;
        #        .moviedteail_list li:eq(6)&&Text;
        #        .moviedteail_list li:eq(4)&&Text'
        type_name = li_text(3)
        director = li_text(2)
        actor = li_text(1)
        remarks = li_text(6)
        year_or_area = li_text(4)

        pic = data('div.dyimg img').attr('src') or ''
        if pic and not pic.startswith('http'):
            if pic.startswith('/'):
                pic = self.host.rstrip('/') + pic
            else:
                pic = self.host.rstrip('/') + '/' + pic

        content = data('.yp_context').text()

        vod = {
            'vod_id': vid,
            'vod_name': name,
            'vod_pic': pic,
            'type_name': type_name,
            'vod_year': year_or_area,
            'vod_area': '',
            'vod_remarks': remarks,
            'vod_actor': actor,
            'vod_director': director,
            'vod_content': content,
            'vod_play_from': '',
            'vod_play_url': ''
        }

        # tabs: '.mi_paly_box .ypxingq_t'
        tabs = [i.text() for i in data('.mi_paly_box .ypxingq_t').items()]

        # lists: '.paly_list_btn:eq(#id) a:gt(0)'
        # 对应每个 tab 一组播放列表
        play_lists = []
        play_uls = list(data('.paly_list_btn').items())

        for idx, ul in enumerate(play_uls):
            items = []
            for i, a in enumerate(ul('a').items()):
                # a:gt(0) => 跳过第一个
                if i == 0:
                    continue
                title = a.text()
                href = a.attr('href') or ''
                if href and not href.startswith('http'):
                    if href.startswith('/'):
                        href = self.host.rstrip('/') + href
                    else:
                        href = self.host.rstrip('/') + '/' + href
                items.append(f'{title}${href}')
            play_lists.append('#'.join(items))

        vod['vod_play_from'] = '$$$'.join(tabs)
        vod['vod_play_url'] = '$$$'.join(play_lists)

        return {'list': [vod]}

    def searchContent(self, key, quick, pg="1"):
        # js: searchUrl: '/dsshiyisc/**----------fypage---.html'
        url = f'{self.host}dsshiyisc/{key}----------{pg}---.html'
        rsp = self.fetch(url, headers=self.headers)
        data = pq(rsp.text)

        videos = self.getlist(data('.mrb ul li'))
        return {
            'list': videos,
            'page': pg
        }

    def playerContent(self, flag, id, vipFlags):
        """
        对应 js 里的 lazy 解析：
        - 如果页面中存在 player_aaaa 且脚本里有 "url":"xxx.m3u8" 就直接取 m3u8
        - 否则返回原始地址
        """
        if id.startswith('http'):
            play_url = id
        else:
            if id.startswith('/'):
                play_url = self.host.rstrip('/') + id
            else:
                play_url = self.host.rstrip('/') + '/' + id

        p = 0  # 直接返回真实地址，不再二级解析

        # 如果本身就是 m3u8
        if '.m3u8' in play_url:
            return {'parse': p, 'url': play_url, 'header': self.headers}

        rsp = self.fetch(play_url, headers=self.headers)
        html = rsp.text

        # 查找包含 player_aaaa 的脚本并提取 m3u8
        # js 里正则: /\"url\"\\s*:\\s*\"([^\"]+\\.m3u8[^\"]*)\"/
        m = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
        if m:
            real = m.group(1).replace('\\/', '/')
            return {'parse': p, 'url': real, 'header': self.headers}

        # 兜底，返回原地址
        return {'parse': p, 'url': play_url, 'header': self.headers}

    def localProxy(self, param):
        return None

    def getlist(self, data):
        """
        对应 js 一级/搜索 规则:
        '.mrb&&ul li;.dytit&&Text;.lazy&&data-original;.hdinfo&&Text;a&&href'
        """
        vlist = []
        for j in data.items():
            name = j('.dytit').text()
            pic = j('.lazy').attr('data-original') or ''
            remark = j('.hdinfo').text()
            href = j('a').attr('href') or ''

            if pic and not pic.startswith('http'):
                if pic.startswith('/'):
                    pic = self.host.rstrip('/') + pic
                else:
                    pic = self.host.rstrip('/') + '/' + pic

            vod_id = href
            vlist.append({
                'vod_id': vod_id,
                'vod_name': name,
                'vod_pic': pic,
                'vod_remarks': remark
            })
        return vlist


# ---- TVBox 本地线路过滤（自动生成，勿改） ----
_TVBOX_DROP_LINES = ["极速-在线播放", "索尼-在线播放", "量子-在线播放"]

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

def _tvbox_apply(cls):
    fn = getattr(cls, 'detailContent', None)
    if fn is None:
        return
    def wrapper(self, *a, _fn=fn, **k):
        return _tvbox_filter_lines(_fn(self, *a, **k), _TVBOX_DROP_LINES)
    setattr(cls, 'detailContent', wrapper)

_tvbox_apply(Spider)
