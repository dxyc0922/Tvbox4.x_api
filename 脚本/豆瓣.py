"""
请勿用于商业用途，请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任
"""

from datetime import datetime
import sys
from base.spider import Spider

sys.path.append("..")


class Spider(Spider):
    def init(self, extend=""):
        """
        初始化配置文件传过来的参数
        :param extend: 来源于配置文件中的ext
        """
        self.name = "豆瓣"
        self.douban_host = "https://movie.douban.com/j/new_search_subjects"
        self.ffzy_host = "https://ffzy.tv/index.php/ajax/data"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        self.current_year = datetime.now().year

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
        categories = [
            {"type_id": "29", "type_name": "最新动漫"},  # 非凡动漫分类
            {"type_id": "13", "type_name": "最新剧集"},  # 非凡电视剧分类
            {"type_id": "电视", "type_name": "热门剧集"},  # 豆瓣电视剧分类
            # {"type_id": "1", "type_name": "最新电影"},  # 非凡电影分类
            {"type_id": "电影", "type_name": "热门电影"},  # 豆瓣电影分类
            # {"type_id": "3", "type_name": "最新综艺"},  # 非凡综艺分类
            {"type_id": "综艺", "type_name": "热门综艺"},  # 豆瓣综艺分类
        ]
        filters = {
            "29": [  # 非凡动漫分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "29", "n": "国产动漫"},
                        {"v": "30", "n": "日韩动漫"},
                        {"v": "31", "n": "欧美动漫"},
                        {"v": "32", "n": "港台动漫"},
                        {"v": "33", "n": "海外动漫"},
                    ],
                }
            ],
            "13": [  # 非凡电视剧分类的筛选条件
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"v": "13", "n": "国产剧"},
                        {"v": "14", "n": "香港剧"},
                        {"v": "15", "n": "韩国剧"},
                        {"v": "16", "n": "欧美剧"},
                        {"v": "21", "n": "台湾剧"},
                        {"v": "22", "n": "日本剧"},
                        {"v": "23", "n": "海外剧"},
                        {"v": "24", "n": "泰国剧"},
                        {"v": "36", "n": "短剧"},
                    ],
                },
            ],
            "电视": [  # 豆瓣电视剧分类的筛选条件
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "古装", "v": "古装"},
                        {"n": "家庭", "v": "家庭"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "历史", "v": "历史"},
                        {"n": "战争", "v": "战争"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "传记", "v": "传记"},
                        {"n": "剧情", "v": "剧情"},
                        {"n": "玄幻", "v": "玄幻"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "音乐", "v": "音乐"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
            # "1": [  # 非凡电影分类的筛选条件
            #     {
            #         "key": "类型",
            #         "name": "类型",
            #         "value": [
            #             {"v": "6", "n": "动作片"},
            #             {"v": "7", "n": "喜剧片"},
            #             {"v": "8", "n": "爱情片"},
            #             {"v": "9", "n": "科幻片"},
            #             {"v": "10", "n": "恐怖片"},
            #             {"v": "11", "n": "剧情片"},
            #             {"v": "12", "n": "战争片"},
            #             {"v": "20", "n": "记录片"},
            #         ],
            #     },
            # ],
            "电影": [  # 豆瓣电影分类的筛选条件
                {
                    "key": "排序",  # 排序方式
                    "name": "排序",
                    "value": [  # 排序选项
                        {"n": "近期热度", "v": "U"},  # 近期热度
                        {"n": "高分优先", "v": "S"},  # 高分优先
                        {"n": "综合排序", "v": "T"},  # 综合排序
                        {"n": "首播时间", "v": "R"},  # 首播时间
                    ],
                },
                {
                    "key": "类型",  # 类型筛选
                    "name": "类型",
                    "value": [  # 电影类型选项
                        {"n": "动画", "v": "动画"},
                        {"n": "喜剧", "v": "喜剧"},
                        {"n": "动作", "v": "动作"},
                        {"n": "科幻", "v": "科幻"},
                        {"n": "爱情", "v": "爱情"},
                        {"n": "悬疑", "v": "悬疑"},
                        {"n": "犯罪", "v": "犯罪"},
                        {"n": "惊悚", "v": "惊悚"},
                        {"n": "冒险", "v": "冒险"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "历史", "v": "历史"},
                        {"n": "奇幻", "v": "奇幻"},
                        {"n": "恐怖", "v": "恐怖"},
                        {"n": "战争", "v": "战争"},
                        {"n": "传记", "v": "传记"},
                        {"n": "歌舞", "v": "歌舞"},
                        {"n": "武侠", "v": "武侠"},
                        {"n": "灾难", "v": "灾难"},
                        {"n": "西部", "v": "西部"},
                        {"n": "纪录片", "v": "纪录片"},
                        {"n": "短片", "v": "短片"},
                    ],
                },
                {
                    "key": "地区",  # 地区筛选
                    "name": "地区",
                    "value": [  # 电影地区选项
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "日本", "v": "日本"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "印度", "v": "印度"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                    ],
                },
            ],
            # "3": [  # 非凡综艺分类的筛选条件
            #     {
            #         "key": "类型",
            #         "name": "类型",
            #         "value": [
            #             {"v": "25", "n": "大陆综艺"},
            #             {"v": "26", "n": "港台综艺"},
            #             {"v": "27", "n": "日韩综艺"},
            #             {"v": "28", "n": "欧美综艺"},
            #         ],
            #     },
            # ],
            "综艺": [  # 豆瓣综艺分类的筛选条件
                {
                    "key": "排序",
                    "name": "排序",
                    "value": [
                        {"n": "近期热度", "v": "U"},
                        {"n": "高分优先", "v": "S"},
                        {"n": "综合排序", "v": "T"},
                        {"n": "首播时间", "v": "R"},
                    ],
                },
                {
                    "key": "类型",
                    "name": "类型",
                    "value": [
                        {"n": "真人秀", "v": "真人秀"},
                        {"n": "脱口秀", "v": "脱口秀"},
                        {"n": "音乐", "v": "音乐"},
                        {"n": "歌舞", "v": "歌舞"},
                    ],
                },
                {
                    "key": "地区",
                    "name": "地区",
                    "value": [
                        {"n": "中国大陆", "v": "中国大陆"},
                        {"n": "韩国", "v": "韩国"},
                        {"n": "日本", "v": "日本"},
                        {"n": "欧美", "v": "欧美"},
                        {"n": "国外", "v": "国外"},
                        {"n": "中国香港", "v": "中国香港"},
                        {"n": "中国台湾", "v": "中国台湾"},
                        {"n": "华语", "v": "华语"},
                        {"n": "美国", "v": "美国"},
                        {"n": "英国", "v": "英国"},
                        {"n": "泰国", "v": "泰国"},
                        {"n": "意大利", "v": "意大利"},
                        {"n": "法国", "v": "法国"},
                        {"n": "德国", "v": "德国"},
                        {"n": "西班牙", "v": "西班牙"},
                        {"n": "俄罗斯", "v": "俄罗斯"},
                        {"n": "瑞典", "v": "瑞典"},
                        {"n": "巴西", "v": "巴西"},
                        {"n": "丹麦", "v": "丹麦"},
                        {"n": "印度", "v": "印度"},
                        {"n": "加拿大", "v": "加拿大"},
                        {"n": "爱尔兰", "v": "爱尔兰"},
                        {"n": "澳大利亚", "v": "澳大利亚"},
                    ],
                },
            ],
        }
        return {"class": categories, "filters": filters}

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
        params = {
            "sort": "U",  # 排序:近期热度
            "range": "0,10",  # 评分区间:0-10分
            "playable": "0",  # 是否可播放:0-不开启，1-开启
            "start": "0",  # 视频起始位置
            "limit": "100",  # 每页数量
            "tags": "",  # 根据分类筛选
            "countries": "中国大陆",
            "year_range": f"{self.current_year-1},{self.current_year}",  # 年份范围：去年到今年
        }

        rsp = self.fetch(self.douban_host, params=params, headers=self.headers)

        if rsp.status_code != 200:
            self.log(f"首页视频列表请求失败")
            return {"list": []}
        try:
            res_json = rsp.json()
            videos = []

            videos.extend(self.json2vods("douban", res_json["data"]))

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
        if tid == "电视" or tid == "电影" or tid == "综艺":
            limit = 100
            start = (int(pg) - 1) * limit

            params = {
                "sort": "U",  # 排序:近期热度
                "range": "0,10",  # 评分区间:0-10分
                "playable": "0",  # 是否只显示可播放的:0-否,1-是
                "start": str(start),  # 视频起始索引
                "limit": str(limit),  # 每页数量
                "tags": tid,  # 根据分类筛选,还可以拼日期之类的比如:电影,2025
                "countries": "中国大陆",
                "year_range": f"{self.current_year-1},{self.current_year}",  # 年份范围：去年到今年
            }

            if extend and isinstance(extend, dict):
                if "类型" in extend:
                    params["genres"] = extend["类型"]  # 按类型筛选
                if "排序" in extend:
                    params["sort"] = extend["排序"]  # 按指定排序方式排序
                if "地区" in extend:
                    params["countries"] = extend["地区"]  # 按地区筛选

            rsp = self.fetch(self.douban_host, params=params, headers=self.headers)
            if rsp.status_code != 200:
                self.log(f"分类视频列表请求失败")
                return {"list": []}
            try:
                res_json = rsp.json()
                videos = []

                videos.extend(self.json2vods("douban", res_json["data"]))

                return {
                    "list": videos,
                    "page": pg,
                    "limit": 20,
                    "pagecount": 9999,
                    "total": 999999,
                }
            except Exception as e:
                self.log(f"分类视频列表解析失败:{e}")
                return {"list": []}
        else:
            params = {
                "mid": "1",
                "tid": tid,
                "page": pg,
                "limit": "30",  # 每页数量,最大支持30
            }
            if extend and isinstance(extend, dict):
                if "类型" in extend:
                    params["tid"] = extend["类型"]  # 按类型筛选

            rsp = self.fetch(self.ffzy_host, params=params, headers=self.headers)
            if rsp.status_code != 200:
                self.log(f"分类视频列表请求失败")
                return {"list": []}
            try:
                res_json = rsp.json()
                videos = []
                videos.extend(self.json2vods("ffzy", res_json["list"]))

                return {
                    "list": videos,
                    "page": pg,
                    "limit": 20,
                    "pagecount": 9999,
                    "total": 999999,
                }
            except Exception as e:
                self.log(f"分类视频列表解析失败:{e}")
                return {"list": []}

    def json2vods(self, flag, video):
        """
        将API返回的视频列表转为标准vod格式
        """
        videos = []

        if flag == "douban":
            for i in video:
                rate = i.get("rate", "")
                cover = i.get("cover", "")

                if cover:
                    cover = f"{cover}@Referer=https://api.douban.com/@User-Agent={self.user_agent}"

                videos.append(
                    {
                        "vod_id": f"msearch:{str(i.get("id", ""))}",
                        "vod_name": i.get("title", ""),
                        "vod_pic": cover,
                        "vod_remarks": f"{rate}分" if rate else "暂无评分",
                    }
                )
        elif flag == "ffzy":
            for i in video:
                if "伦理片" in i.get("type_name", ""):
                    continue
                videos.append(
                    {
                        "vod_id": f"msearch:{str(i.get("vod_id", ""))}",
                        "vod_name": i.get("vod_name", ""),
                        "vod_pic": i.get("vod_pic", ""),
                        "vod_remarks": i.get("vod_remarks", ""),
                    }
                )
        return videos


if __name__ == "__main__":
    spider = Spider()
    spider.init()
    print("\n-------------------获取非凡分类内容测试------------------------------")
    rsp = spider.categoryContent("4", 1, True, "")
    print(rsp)
    # print("\n-------------------获取豆瓣分类内容测试------------------------------")
    # rsp = spider.categoryContent("电视", 1, True, "")
    # print(rsp)
