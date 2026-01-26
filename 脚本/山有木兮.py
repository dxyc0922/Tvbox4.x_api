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
        self.name = "山有木兮"
        self.host = "https://film.symx.club"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "X-Platform": "web",
            "Referer": "https://film.symx.club/index",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "DNT": "1",
        }

    def getName(self):
        return self.name

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
        url = f"{self.host}/api/film/detail"
        params = {"id": str(ids[0])}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"视频详情请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            play_from_list = []
            play_url_list = []
            data = res_json["data"]

            # 解析播放线路
            for play_line in data.get("playLineList", []):
                player_name = play_line.get("playerName", "")
                play_from_list.append(player_name)

                # 解析线路下的播放源
                line_urls = []
                for line in play_line.get("lines", []):
                    line_name = line.get("name", "")
                    line_id = line.get("id", "")
                    line_urls.append(f"{line_name}${line_id}")
                play_url_list.append("#".join(line_urls))
                
            video = {
                "vod_id": data.get("id", ""),
                "vod_name": data.get("name", ""),
                "vod_pic": data.get("cover", ""),
                "vod_remarks": data.get("remarks", ""),
                "vod_year": data.get("year", ""),
                "vod_area": data.get("area", ""),
                "vod_actor": data.get("actor", ""),
                "vod_director": data.get("director", ""),
                "vod_content": data.get("blurb", ""),
                "vod_score": data.get("doubanScore", ""),
                "type_name": data.get("class", ""),
                "vod_play_from": "$$$".join(play_from_list),
                "vod_play_url": "$$$".join(play_url_list),
            }

            return {"list": [video]}
        except Exception as e:
            self.log(f"视频详情解析失败")
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
        # 检查"第*季"前面是否有空格，如果没有空格则在前面加一个空格,兼容xxx第x季这种没空格的搜索
        processed_key = re.sub(r"(?<!\s)(\w)(第\d+季)", r"\1 \2", key)
        url = f"{self.host}/api/film/search"
        params = {
            "keyword": str(processed_key),
            "pageNum": str(pg),
            "pageSize": "10",
        }
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"搜索结果请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            videos = self.json2vods(res_json["data"]["list"])
            return {"list": videos}
        except Exception as e:
            self.log(f"搜索结果解析失败")
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
        url = f"{self.host}/api/line/play/parse"
        params = {"lineId": str(id)}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"搜索结果请求失败")
            return {"parse": 0, "url": ""}
        else:
            res_json = rsp.json()
            return {
                "parse": 0,
                "jx": 0,
                "url": res_json.get("data", ""),
                "header": {"User-Agent": self.user_agent}
            }

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
                    "vod_id": str(i.get("id", "")),
                    "vod_name": i.get("name", ""),
                    "vod_pic": i.get("cover", ""),
                    "vod_remarks": i.get("updateStatus", ""),
                }
            )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp = spider.searchContent("仙逆", True, "1")
    print(rsp)
    time.sleep(1)
    print("\n-------------------获取视频列表测试------------------------------")
    rsp = spider.detailContent([rsp["list"][0]["vod_id"]])
    print(rsp)
    print("\n-------------------解析视频地址测试------------------------------")
    id = rsp["list"][0]["vod_play_url"].split("$$$")
    rsp = spider.playerContent("", id, [])
    print(rsp)
