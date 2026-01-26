"""
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""

import re
import sys
import time
from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend=""):
        self.name = "3Q影视"
        self.host = "https://qqqys.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }

    def getName(self):
        return self.name

    def homeContent(self, filter):
        """
        获取分类列表
        """
        url = self.host + "/api.php/index/home"
        rsp = self.fetch(url, headers=self.headers)
        if rsp.status_code != 200:
            self.log(f"分类列表请求失败")
            return {"class": []}
        try:
            res_json = rsp.json()
            classes = []
            for i in res_json["data"]["categories"]:
                name = i["type_name"]
                # 跳过一些不需要的分类
                if name in ["问答", "专题", "排行榜"]:
                    continue
                classes.append({"type_id": name, "type_name": name})

            return {"class": classes}
        except Exception as e:
            self.log(f"分类列表解析失败")
            return {"class": []}

    def homeVideoContent(self):
        """
        获取首页视频列表
        """
        url = self.host + "/api.php/index/home"
        rsp = self.fetch(url, headers=self.headers)
        if rsp.status_code != 200:
            self.log(f"首页视频列表请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            videos = []
            for category in res_json["data"]["categories"]:
                videos.extend(self.json2vods(category.get("videos", [])))

            return {"list": videos}
        except Exception as e:
            self.log(f"首页视频列表解析失败")
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        """
        获取分类视频列表
        """
        url = f"{self.host}/api.php/filter/vod"
        params = {"type_name": tid, "sort": "hits", "page": pg, "limit": 24}
        rsp = self.fetch(url, params=params, headers=self.headers)
        if rsp.status_code != 200:
            self.log(f"分类视频列表请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            videos = self.json2vods(res_json["data"])
            return {"list": videos}
        except Exception as e:
            self.log(f"分类视频列表解析失败")
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        """
        获取搜索结果
        """
        url = f"{self.host}/api.php/search/index"
        params = {"wd": key, "page": pg, "limit": 15}
        rsp = self.fetch(url, params=params, headers=self.headers)
        if rsp.status_code != 200:
            self.log(f"搜索结果请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            videos = self.json2vods(res_json["data"])
            return {"list": videos}
        except Exception as e:
            self.log(f"搜索结果解析失败")
            return {"list": []}

    def detailContent(self, ids):
        """
        获取视频详情
        """
        vid = ids[0]
        # 处理视频ID格式
        if "/vd/" in vid:
            vid = (
                vid.split("/")[-1]
                .replace(".html", "")
                .replace("vod-detail-id-", "")
                .replace(".html", "")
            )

        url = f"{self.host}/api.php/vod/get_detail"
        params = {"vod_id": vid}

        rsp = self.fetch(url, params=params, headers=self.headers)
        if rsp.status_code != 200:
            self.log(f"视频详情请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            data = res_json["data"][0]
            vodplayer = res_json.get("vodplayer", [])

            shows = []
            play_urls = []

            raw_shows = (
                data["vod_play_from"].split("$$$") if data.get("vod_play_from") else []
            )
            raw_urls_list = (
                data["vod_play_url"].split("$$$") if data.get("vod_play_url") else []
            )

            for i in range(len(raw_shows)):
                show_code = raw_shows[i]
                urls_str = raw_urls_list[i] if i < len(raw_urls_list) else ""

                need_parse = 0
                is_show = 0
                name = show_code

                for player in vodplayer:
                    if player.get("from") == show_code:
                        is_show = 1
                        need_parse = player.get("decode_status", 0)
                        if show_code.lower() != player.get("show", "").lower():
                            name = f"{player.get('show', show_code)} ({show_code})"
                        break

                if is_show == 1:
                    urls = []
                    items = urls_str.split("#")
                    for item in items:
                        if "$" in item:
                            parts = item.split("$")
                            episode = parts[0]
                            m_url = parts[1]
                            urls.append(f"{episode}${show_code}@{need_parse}@{m_url}")
                    if urls:
                        play_urls.append("#".join(urls))
                        shows.append(name)

            video = {
                "vod_id": str(data.get("vod_id", "")),
                "vod_name": data.get("vod_name", ""),
                "vod_pic": data.get("vod_pic", ""),
                "vod_remarks": data.get("vod_remarks", ""),
                "vod_year": data.get("vod_year", ""),
                "vod_area": data.get("vod_area", ""),
                "vod_actor": data.get("vod_actor", ""),
                "vod_director": data.get("vod_director", ""),
                "vod_content": data.get("vod_content", ""),
                "vod_play_from": "$$$".join(shows),
                "vod_play_url": "$$$".join(play_urls),
                "type_name": data.get("vod_class", ""),
            }

            return {"list": [video]}
        except Exception as e:
            self.log(f"视频详情解析失败")
            return {"list": []}

    def parse_js_challenge(self, js_code):
        """
        解析JavaScript挑战码并返回token
        """
        import re

        # 提取数组中的值
        array_match = re.search(r"_0x1=\[(.*?)\]", js_code)
        if array_match:
            values = [
                val.strip().strip("'\"") for val in array_match.group(1).split(",")
            ]
            if len(values) >= 4:
                _0xa, _0_b, _0_c, _0_d = values[0], values[1], values[2], values[3]

                # 模拟JavaScript中的计算过程
                _0_e = f"{_0xa}:{_0_b}:{_0_c}:{_0_d}"
                _0_f = 0
                for char in _0_e:
                    _0_f = ((_0_f << 5) - _0_f) + ord(char)
                    _0_f = _0_f & 0xFFFFFFFF

                _0_h = hex(abs(_0_f))
                _0xi = f"{_0xa}:{_0_h[2:]}:{_0_b[:8]}"  # 移除hex输出的'0x'前缀
                return _0xi

        return None

    def playerContent(self, flag, id, vipFlags):
        """
        播放地址解析
        """
        parts = id.split("@")
        if len(parts) >= 3:
            play_from = parts[0].split("$")[1]
            need_parse = parts[1]
            raw_url = parts[2]

            jx = 0
            final_url = ""

            if need_parse == "1":
                auth_token = ""
                for i in range(2):
                    try:
                        api_url = f"{self.host}/api.php/decode/url/?url={raw_url}&vodFrom={play_from}{auth_token}"
                        rsp = self.fetch(api_url, headers=self.headers, timeout=30)
                        res_json = rsp.json()
                        if res_json.get("code") == 2 and res_json.get("challenge"):
                            # 解析JavaScript挑战码
                            challenge_data = res_json["challenge"]
                            token = self.parse_js_challenge(challenge_data)
                            if token:
                                auth_token = f"&token={token}"
                                continue
                        play_url = res_json.get("data", "")
                        if play_url and play_url.startswith("http"):
                            final_url = play_url
                            break
                    except Exception as e:
                        print(f"解析播放地址出错: {e}")
                        break
            else:
                final_url = raw_url
                if re.search(
                    r"(?:www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com",
                    raw_url,
                ):
                    jx = 1

            return {
                "parse": jx, # 是否使用解析器
                "jx": 0, # 使用第几个解析器
                "url": final_url, # 播放地址
                "header": {"User-Agent": self.headers["User-Agent"]},
            }
        else:
            # 直接使用传入的ID作为播放地址
            return {
                "parse": jx,
                "jx": 0,
                "url": id,
                "header": {"User-Agent": self.headers["User-Agent"]},
            }

    def json2vods(self, arr):
        """
        将API返回的视频列表转为标准vod格式
        """
        videos = []
        for i in arr:
            type_name = i.get("type_name", "")
            if i.get("vod_class"):
                type_name = type_name + "," + i["vod_class"]

            videos.append(
                {
                    "vod_id": str(i.get("vod_id", "")),
                    "vod_name": i.get("vod_name", ""),
                    "vod_pic": i.get("vod_pic", ""),
                    "vod_remarks": i.get("vod_remarks", ""),
                    "type_name": type_name,
                    "vod_year": i.get("vod_year", ""),
                }
            )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print("---------------------获取分类列表测试------------------------------")
    rsp = spider.homeContent(True)
    print(rsp)
    time.sleep(1)
    print("\n-------------------获取分类内容测试------------------------------")
    rsp = spider.categoryContent(rsp["class"][0]["type_id"], 1, True, "")
    print(rsp)
    time.sleep(1)
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp2 = spider.searchContent(rsp["list"][0]["vod_name"], False, 1)
    print(rsp2)
    time.sleep(1)
    print("\n-------------------获取视频列表测试------------------------------")
    rsp = spider.detailContent([rsp["list"][0]["vod_id"]])
    print(rsp)
    print("\n-------------------解析视频地址测试------------------------------")
    id = rsp["list"][0]["vod_play_url"].split("$$$")
    for i in id:
        if i.startswith("正片$YYNB"):
            id = i
            break
    rsp = spider.playerContent("", id, [])
    print(rsp)
