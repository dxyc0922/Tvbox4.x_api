"""
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""
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
        self.name = "荐片"
        self.host = "https://ev2089.zxbwv.com"
        self.user_agent = "Mozilla/5.0 (Linux; Android 11; M2012K10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/87.0.4280.141 Mobile Safari/537.36;webank/h5face;webank/1.0;netType:NETWORK_WIFI;appVersion:416;packageName:com.jp3.xg3"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "x-requested-with": "com.jp3.xg3",
            "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        # 初始化图片服务器地址
        self.ihost = self.imgsite()

    def getName(self):
        return self.name

    def imgsite(self):
        """获取图片服务器地址"""
        data = self.fetch(f"{self.host}/api/appAuthConfig", headers=self.headers).json()
        host = data["data"]["imgDomain"]
        return host if host.startswith("http") else f"https://{host}"

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
            "page": 当前页数,
            "limit": 每页显示数量,
            "pagecount": 总页数=总数/每页数量
            "total": 总数
        }
        """
        url = f"{self.host}/api/v2/search/videoV2"
        params = {"key": key, "page": pg, "pageSize": 20}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"搜索结果请求失败")
            return {"list": []}

        try:
            res_json = rsp.json()
            result = {}
            result["list"] = self.build_cl(res_json["data"])
            result["page"] = pg
            result["pagecount"] = 9999
            result["limit"] = 20
            result["total"] = 999999
            return result
        except Exception as e:
            self.log(f"搜索结果解析失败: {e}")
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
        url = f"{self.host}/api/video/detailv2"
        params = {"id": vid}
        rsp = self.fetch(url, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"视频详情请求失败")
            return {"list": []}

        try:
            res_json = rsp.json()
            v = res_json["data"]

            # 只处理极速蓝光线路
            names, play_urls = [], []
            for source in v.get("source_list_source", []):
                source_name = source.get("name", "")
                if "极速蓝光" in source_name:  # 只处理包含"极速蓝光"的线路
                    names.append(source_name)
                    urls = "#".join(
                        [
                            f"{j.get('source_name') or j.get('weight')}${j['url']}"
                            for j in source.get("source_list", [])
                        ]
                    )
                    if urls:
                        play_urls.append(urls)

            # 构建视频详情
            video = {
                "vod_id": str(v.get("id", "")),
                "vod_name": v.get("title", ""),
                "vod_pic": f"{self.ihost}{v.get('path') or v.get('cover_image') or v.get('thumbnail', '')}",
                "vod_remarks": v.get("update_cycle", ""),
                "vod_year": v.get("year", ""),
                "vod_area": v.get("area", ""),
                "vod_actor": "/".join([i.get("name", "") for i in v.get("actors", [])]),
                "vod_director": "/".join(
                    [i.get("name", "") for i in v.get("director", [])]
                ),
                "vod_content": v.get("description", ""),
                "vod_score": str(v.get("score", "")),
                "type_name": "/".join([i.get("name", "") for i in v.get("types", [])]),
                "vod_play_from": "$$$".join(names),
                "vod_play_url": "$$$".join(play_urls),
            }

            return {"list": [video]}
        except Exception as e:
            self.log(f"视频详情解析失败: {e}")
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
        return {
            "parse": 0,
            "playUrl": "",
            "url": id,
            "header": {"User-Agent": self.user_agent},
        }

    def build_cl(self, data, tid=""):
        """
        将API返回的视频列表转为标准vod格式
        :param data: API返回的视频数据
        :param tid: 分类ID
        :return: 标准vod格式的视频列表
        """
        videos = []
        for i in data:
            # 过滤短剧内容：检查type字段是否为2（短剧）或res_categories中是否包含短剧分类
            is_short_play = i.get('type') == 2
            res_categories = i.get('res_categories', [])
            has_short_play_category = any(cat.get('id') == 67 and cat.get('name') == '短剧' for cat in res_categories)
            
            # 过滤情色类型视频
            video_types = i.get('types', [])
            has_erotic_category = '情色' in video_types
            
            # 如果是短剧或包含情色类型则跳过
            if is_short_play or has_short_play_category or has_erotic_category:
                continue
            
            videos.append(
                {
                    "vod_id": f"{i.get('id')}",
                    "vod_name": i.get("title", ""),
                    "vod_pic": f"{self.ihost}{i.get('path') or i.get('cover_image') or i.get('thumbnail', '')}",
                    "vod_remarks": i.get("mask", ""),
                    "vod_year": i.get("score", ""),
                }
            )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print("\n-------------------获取搜索内容测试------------------------------")
    rsp = spider.searchContent("斗破苍穹", False, 1)
    print(rsp)
    time.sleep(1)
    print("\n-------------------获取视频详情测试------------------------------")
    rsp = spider.detailContent([rsp["list"][0]["vod_id"]])
    print(rsp)
    time.sleep(1)
    print("\n-------------------解析视频地址测试------------------------------")
    play_url = (
        rsp["list"][0]["vod_play_url"].split("$$$")[0].split("#")[0]
    )
    if "$" in play_url:
        play_url = play_url.split("$")[1]
    rsp = spider.playerContent("", play_url, [])
    print(rsp)
