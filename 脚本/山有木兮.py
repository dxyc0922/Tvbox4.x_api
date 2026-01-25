"""
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""

import sys
import random
import re

sys.path.append("..")
from base.spider import Spider


class Spider(Spider):  # 继承基类Spider，实现具体的脚本逻辑
    def init(self, extend=""):  # 初始化脚本的基本配置信息
        self.name = "山有木兮"  # 脚本名称
        # API接口地址，用于获取搜索结果
        self.api = "https://film.symx.club"
        # 用户代理字符串，模拟浏览器访问
        self.user_agent = [
            # Safari - iOS
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
            # Samsung Browser - Android
            "Mozilla/5.0 (Linux; Android 10; SAMSUNG SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.5790.166 Mobile Safari/537.36",
            # Chrome - Android
            "Mozilla/5.0 (Linux; Android 10; Pixel 4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
        ]
        # 请求头信息，模拟正常浏览器访问网站
        self.header = {
            "Accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-platform": "web",
        }

    def getName(self):  # 获取脚本名称的方法
        return self.name

    def getRandomHeader(self):
        """获取带有随机user-agent的请求头"""
        headers = self.header.copy()
        headers["User-Agent"] = random.choice(self.user_agent)
        return headers

    def searchContent(self, key, quick, pg="1"):
        """搜索指定视频内容"""
        try:
            # 检查"第*季"前面是否有空格，如果没有空格则在前面加一个空格,兼容xxx第x季这种没空格的搜索
            processed_key = re.sub(r"(?<!\s)(\w)(第\d+季)", r"\1 \2", key)

            url = f"{self.api}/api/film/search"
            params = {
                "keyword": str(processed_key),
                "pageNum": str(pg),
                "pageSize": "10",
            }
            # 发送请求获取数据
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            video_list = []
            for item in rsp["data"]["list"]:
                video_list.append(
                    {
                        "vod_id": item.get("id", ""),
                        "vod_name": item.get("name", ""),
                        "vod_pic": item.get("cover", ""),
                        "vod_remarks": item.get("updateStatus", ""),
                        "vod_year": item.get("year", ""),
                        "vod_area": item.get("area", ""),
                        "vod_director": item.get("director", ""),
                    }
                )
            return {"list": video_list}
        except Exception as e:
            return {"list": []}

    def detailContent(self, ids):
        """获取视频详情"""
        try:
            url = f"{self.api}/api/film/detail"
            params = {"id": str(ids[0])}  # 确保id参数是字符串类型
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            video_list = {}
            play_from_list = []
            play_url_list = []
            data = rsp["data"]
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

            video_list.update(
                {
                    "vod_id": data.get("id", ""),
                    "vod_name": data.get("name", ""),
                    "vod_pic": data.get("cover", ""),
                    "vod_year": data.get("year", ""),
                    "vod_area": data.get("area", ""),
                    "vod_actor": data.get("actor", ""),
                    "vod_director": data.get("director", ""),
                    "vod_content": data.get("blurb", ""),
                    "vod_score": data.get("doubanScore", ""),
                    "vod_play_from": "$$$".join(play_from_list),
                    "vod_play_url": "$$$".join(play_url_list),
                }
            )
            result = {"list": [video_list]}
            return result
        except Exception as e:
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址"""
        try:
            url = f"{self.api}/api/line/play/parse"
            params = {"lineId": str(id)}
            rsp = self.fetch(
                url=url,
                params=params,
                headers=self.getRandomHeader(),
            ).json()
            result = {
                "jx": "0",
                "parse": "0",
                "url": rsp.get("data", ""),
                "header": {"User-Agent": random.choice(self.user_agent)},
            }
            return result
        except Exception as e:
            return {"parse": "0", "url": ""}


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print(spider.searchContent("一人之下", "", "1"))
