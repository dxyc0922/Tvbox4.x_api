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
        """
        初始化配置文件传过来的参数
        :param extend: 来源于配置文件中的ext
        """
        self.name = "3Q影视"
        self.host = "https://qqqys.com"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def getName(self):
        return self.name

    def homeContent(self, filter):
        """
        获取分类列表
        :param filter: 表示是否需要返回filters,True表示需要,False表示不需要,默认为True
        :return: 示例
        {
            "class": [
                {
                    "type_id": "1", "type_name": "电影"
                }
            ],
            filters: {
                "1": [
                    {
                        "key": "type",
                        "name": "类型",
                        "value": [
                            {"n": "动作", "v": "2"}
                        ]
                    }
                ]
            },
            api如果有完整的list数组可以直接使用,而不需要再调用homeVideoContent方法获取首页推荐
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ]
        }
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
            self.log(f"分类列表解析失败:{e}")
            return {"class": []}

    def homeVideoContent(self):
        """
        获取首页推荐内容,如果homeContent方法返回了list数组,则该方法可以不用实现
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ]
        }
        """
        url = self.host + "/api.php/index/home"
        rsp = self.fetch(url, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"首页视频列表请求失败")
            return {"list": []}
        try:
            res_json = rsp.json() 
            videos = []

            for video in res_json["data"]["categories"]["videos"]:
                videos.extend(self.json2vods(video))

            return {"list": videos}
        except Exception as e:
            self.log(f"首页视频列表解析失败:{e}")
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        """
        获取分类列表内容
        :param tid: 类型id,来源于homeContent的class数组中的type_id
        :param pg: 页数,来源于app翻页操作
        :param filter: 是否开启筛选,来源于app筛选操作
        :param extend: 扩展参数,来源于app筛选操作,选中的筛选项会传过来{"type":"2"}
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ],
            如果api有提供可以写入,不写入也没影响
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        }
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
            self.log(f"分类视频列表解析失败:{e}")
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        """
        获取搜索内容
        :param key: 搜索关键字
        :param quick: 是否是快捷搜索,True表示是,False表示否,默认为True
        :param pg: 页数,来源于app翻页操作,默认1
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "电影id(不显示)", "vod_name": "电影名称(显示)", "vod_pic": "封面图片(显示)", "vod_remarks": "备注(显示)"
                }
            ],
            如果api有提供可以写入,不写入也没影响
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
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
            self.log(f"搜索结果解析失败:{e}")
            return {"list": []}

    def detailContent(self, ids):
        """
        获取视频详情
        :param ids: 视频id组,来源于app点击视频进入详情页,会带上vod_id参数,使用ids[0]获取
        :return: 示例
        {
            "list": [
                {
                    "vod_id": "视频id(不显示)", # 示例:1
                    "vod_name": "视频名称(显示)", # 示例:申肖克的救赎
                    "vod_pic": "视频封面(显示)", # 示例:https://example.com/cover.jpg
                    "vod_remarks": "备注(显示)", # 示例:更新至第10集
                    "vod_year": "年份(显示)", # 示例:2023
                    "vod_area": "地区(显示)", # 示例:中国大陆
                    "vod_actor": "主演(显示)", # 示例:张三,李四,王五
                    "vod_director": "导演(显示)", # 示例:赵六
                    "vod_content": "视频简介(显示)", # 示例:这是一个精彩的视频...
                    "vod_score": "评分(显示)", # 示例:9.5
                    "type_name": "分类名称(显示)", # 示例:电影
                    "vod_play_from": "播放来源(显示)", # 示例:线路1$$$线路2
                    "vod_play_url": "播放地址(显示)" # 示例:第1集$http://example.com/video1.mp4#第2集$http://example.com/video2.mp4$$$第1集$http://backup.com/video1.mp4"
                }
            ]
        }
        """
        vid = ids[0]

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

            videos = []
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

            videos.append(
                {
                    "vod_id": str(data.get("vod_id", "")),
                    "vod_name": data.get("vod_name", ""),
                    "vod_pic": data.get("vod_pic", ""),
                    "vod_remarks": data.get("vod_remarks", ""),
                    "vod_year": data.get("vod_year", ""),
                    "vod_area": data.get("vod_area", ""),
                    "vod_actor": data.get("vod_actor", ""),
                    "vod_director": data.get("vod_director", ""),
                    "vod_content": data.get("vod_content", ""),
                    "vod_score": str(data.get("vod_score", "暂无评分")),
                    "type_name": data.get("vod_class", ""),
                    "vod_play_from": "$$$".join(shows),
                    "vod_play_url": "$$$".join(play_urls),
                }
            )

            return {"list": videos}
        except Exception as e:
            self.log(f"视频详情解析失败:{e}")
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """
        :param flag: 视频标识,来源于detailContent的vod_play_from
        :param id: 视频id来源于detailContent的vod_play_url
        :param vipFlags: 默认是空的,应该是猫影视vip会员的标识
        :return: {
            "parse": 表示是否调用配置中的parses解析,0表示不需要,1表示需要
            "playUrl": 表示是否需要在url前面添加播放器地址,示例:http://example.com/player.html?url=
            "url": 表示视频播放地址
            "jx": 表示播放器是否显示解析列表,0表示不需要,1表示需要
            "header": 表示是否需要添加请求头,触发防盗链时添加
        }
        """
        parts = id.split("@")
        if len(parts) >= 3:
            play_from = parts[0]
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
                "parse": jx,
                "jx": jx,
                "url": final_url,
                "header": {"User-Agent": self.user_agent},
            }
        else:
            # 直接使用传入的ID作为播放地址
            return {
                "parse": jx,
                "jx": jx,
                "url": id,
                "header": {"User-Agent": self.user_agent},
            }

    def parse_js_challenge(self, js_code):
        """
        解析JavaScript挑战码并返回token
        """
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

    def json2vods(self, video):
        """
        将API返回的视频列表转为标准vod格式
        """
        videos = []
        for i in video:
            type_name = i.get("type_name", "")
            if i.get("vod_class"):
                type_name = type_name + "," + i["vod_class"]

            videos.append(
                {
                    "vod_id": str(i.get("vod_id", "")),
                    "vod_name": i.get("vod_name", ""),
                    "vod_pic": i.get("vod_pic", ""),
                    "vod_remarks": i.get("vod_remarks", ""),
                }
            )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    # print("---------------------获取分类列表测试------------------------------")
    # rsp = spider.homeContent(True)
    # print(rsp)
    # time.sleep(1)
    # print("\n-------------------获取分类内容测试------------------------------")
    # rsp = spider.categoryContent(rsp["class"][0]["type_id"], 1, True, "")
    # print(rsp)
    # time.sleep(1)
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp2 = spider.searchContent("剑来", False, 1)
    print(rsp2)
    time.sleep(1)
    # print("\n-------------------获取视频列表测试------------------------------")
    # rsp = spider.detailContent(["53205"])
    # print(rsp)
    # time.sleep(1)
    # print("\n-------------------解析视频地址测试------------------------------")
    # id = rsp["list"][0]["vod_play_url"].split("$$$")
    # for i in id:
    #     if i.startswith("正片$YYNB"):
    #         id = i[3:]
    #         break
    # rsp = spider.playerContent("", id, [])
    # print(rsp)
