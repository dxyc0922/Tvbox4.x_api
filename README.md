# Tvbox4.x_api
适配安卓4.x的tvbox接口

源地址：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

Github加速地址：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json

说明:由于盒子是安卓4.x会导致加载一些新的接口会崩溃,无法加载,无法播放等异常情况,况且有些线路含18禁内容不适合在电视上展示,以及一些线路含赌博广告,播放卡顿等问题都需要清除

1.符合下面要求的接口会添加进接口给电视用

2.在电视盒子上接口加载正常;自营线路播放正常

3.不存在18禁内容,比如伦理,福利等分类;搜索"女教师"等关键字无漏点图

4.无赌博广告,播放不卡顿,比如cms资源站的资源一般都不合格

5.直播使用本地电信组播IPTV源,需要路由器启用IGMP嗅探

## 自动同步接口

更新逻辑：`scripts/update_api.py`；定时运行在**本机**（Windows 任务计划程序），
GitHub Actions 只保留手动触发作为备用通道。

- 临时拉取上游 `wzxxcz/wzxxcz` 的 `py/` 目录，不提交脚本文件。
- 解析每个脚本里的 host（支持 `HOST`、`HOSTS`、`host`、`xurl` 等变量，以及 `_dk8` 混淆字符串）。
- 只接受定义了 `class Spider` 的脚本：上游混入的报错 HTML、命令行脚本会被跳过。
- 代码内容相同的脚本（改名副本）只保留一个，优先保留文件名不带广告后缀、更短的那个。
- host 返回 `2xx/3xx/4xx` 视为可达；`5xx`、DNS 失败、连接超时视为失效。
- 重建 `接口.json` 的 `sites`：
  - `api` 以 `./` 开头（本地脚本）或其他非 http 站点原样保留；
  - 所有 http/https 站点删除后，用校验通过的上游脚本重新生成；
  - 脚本链接统一使用 `https://gh-proxy.com/https://raw.githubusercontent.com/...`。
- `wallpaper`、`lives`、`doh`、`rules`、`ads` 等其他顶层字段保持不变。
- 可用站点骤降保护：本次生成数少于上次的一半、或下载失败率超过 20% 时不写入，直接报错退出。

### 本机定时运行（推荐）

```powershell
# 1. 先手动跑一次，确认能生成、能推送
python scripts/run_local.py --dry-run     # 只校验，不写文件
python scripts/run_local.py               # 校验 + 生成 + 提交推送

# 2. 注册每周任务（默认每周一 02:00，当前登录用户）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1

# 可选参数
#   -Day Sunday -Time 03:30        改时间
#   -Functional                    顺带跑功能校验
#   -RunWhenLoggedOff              未登录也运行（会提示输入该用户密码）
#   -Unregister                    删除任务
```

`run_local.py` 每次运行会：

1. `git pull --rebase --autostash`（失败忽略，不影响生成）；
2. 可选跑 `functional_check.py`（`--functional`，默认关闭）；
3. 调用 `update_api.py` 重建 `接口.json`；
4. 有变化才提交，推送失败会重试 3 次；仍失败则保留本地提交，下次运行自动带上。

日志写在 `logs/local-run-<时间>.log`，任务计划程序里也能看到上次运行结果。

### 功能校验（可选）

host 可达不代表脚本能用。`scripts/functional_check.py` 会在隔离环境里真正调用脚本：

1. `homeContent` —— 能否取到首页片单；
2. `searchContent` —— 用关键词搜索能否取到结果；
3. `detailContent` —— 能否拿到 `vod_play_url` 播放地址。

每通过一项记 1 分，满分 3 分。结果写入 `reports/functional-report.json`，`update_api.py`
用 `--functional-report` 读取并附加到 `接口.json` 的校验报告里。

```bash
# 本地调试（会执行第三方代码，建议在虚拟机里跑）
python scripts/functional_check.py --source-dir /path/to/py --limit 20

# 把评分合并进校验报告
python scripts/update_api.py --functional-report reports/functional-report.json
```

GitHub Actions 里这一步跑在 Docker 容器中：不注入任何密钥、`/work` 只读、限制内存/CPU/进程数、
禁止访问内网和回环地址。**本机运行（`--functional`）没有容器隔离**，等于在自己的机器上执行
221 个陌生脚本，只做了超时杀进程和「禁止访问内网地址」两道防护；除非装了 Docker/WSL2，
否则不建议在本机开启。

默认 **只评分不删源**（`functional.min_score = 0`）。实测 221 个脚本里约 47% 能拿到 2 分以上，
0 分的绝大多数是「请求成功但搜不到结果」——多半是境外 IP 被地区限制，按分数删源会误删。
确认识别准确后再把 `min_score` 设为 2 或 3。

### 源质量分级（A/B/C/D）

功能校验拿到播放地址后，`scripts/stream_check.py` 会再走一遍 `playerContent`，用真实播放地址判断来源
（每个源最多取 `quality.max_lines` 条线路，逐条判断，同时测量码率）：

| 等级 | 含义 | 判断依据 |
|---|---|---|
| **A 自营** | 播放地址和站点同主域，自己转码自己发 | 域名比对一致 |
| **B 第三方直连** | 直连 m3u8/mp4，但走的是别家 CDN | 域名不一致 |
| **C 搬运/解析** | 播放地址落在抖音/快手/西瓜等平台 CDN，或需要网页解析 | 平台域名 / 字节 `tos-cn-` 路径 / `parse=1` / 页面型地址 |
| **D 无法验证** | 请求失败、返回非视频内容 | — |
| **U 未取得播放地址** | 没解析出播放地址（地区限制/超时/本地代理） | 不参与过滤 |

另外会记录 `ad_score`：`#EXT-X-CUE-OUT` / `#EXT-X-DATERANGE` / `SCTE35` 广告标记各 +3，
分片来自多个域名（少数域名占比 ≤20%）+2。命中即判 C。

```bash
# 单独看某个播放地址
python scripts/stream_check.py "https://xxx/index.m3u8" --site-host https://www.example.com
```

**关于「广告藏在 m3u8 不规则时间段」**：实测不成立。221 个脚本里 87 个能解析出播放地址，
其中 55 个 HLS 全部单域名分片、无 CUE/DATERANGE 标记、`ad_score` 全为 0；而正常转码源（VFR）
普遍存在 0.2–1 秒短分片和大量 `#EXT-X-DISCONTINUITY`（例如金牌蓝兔子 307 个短分片、
低端影视 277 个），按「时长不规则」判断会把正常源大面积误判成广告。广告更可能来自
解析器/网页播放器（C 级）或视频画面本身（搬运源水印）。

想按等级过滤，把 `scripts/config.json` 里的 `quality.min_grade` 设为 `B`（保留 A/B，剔除 C/D）
或 `A`（只保留自营）。默认空字符串表示不过滤。

**注意**：拿不到播放地址的脚本（地区限制、超时、本地代理 `127.0.0.1`）单独记为 **U 未取得播放地址**。
`quality.drop_unverified` 默认 `false`，即 U 不参与等级过滤——测不出来不等于源差，实测 221 个脚本里
U 有 146 个，全删会误伤大量可用站点。本仓库现在显式设为 `true`，只保留验证过的源。

当前仓库的配置是 `min_grade = "B"` + `drop_unverified = true`，即**只保留验证过的 A/B 源**：
221 个脚本里可用 55 个（A 5 + B 50），其余是等级不足/U 113 个、成人内容 6 个、
低码率 7 个、host 不可达 29 个、无 host 7 个、跳过/重复 4 个。
最终 `接口.json` 是 57 个站点（55 自动 + 2 本地）。想放宽就关掉 `drop_unverified`。

### 本地运行

```bash
python scripts/update_api.py --dry-run
python scripts/update_api.py

# 用已经下载好的 py 目录调试，不访问 GitHub
python scripts/update_api.py --source-dir /path/to/py --dry-run
```

### 成人内容过滤

默认开启（`filters.exclude_adult = true`）。判定分两条，都不依赖关键词搜索是否准确：

1. **分类名**：首页 `homeContent` 返回的分类里出现 `伦理片` / `理论片` / `福利` / `里番` / `无码` /
   `三级` / `成人` / `麻豆` / `蜜桃` / `星空传媒` / `自拍` / `偷拍` / `乱伦` 等。
   `伦理` / `理论` 必须带「片」或单独成词，所以「家庭伦理」「伦理现实」「女性成长」这类正常短剧分类不会被误判。
2. **探针搜索**：用 `functional.adult_probe_keywords`（默认「麻豆传媒」「被家长调教的女教师」）再搜一遍。
   只要结果标题里出现探针关键词原文、工作室品牌或明确成人词，就判定为成人源——能搜出完整成人片名，
   说明站点确实收录了这类内容。

实测 221 个脚本命中 6 个：EcoHub影视（`伦理片` 分类）、ZIP0影视、飞流视频（能搜出
《家访后，被家长调教的女教师》）、悟空传媒、熊猫秒播、黄豆短剧。`接口.json` 因此从 70 个站点降到 64 个。

如果某个源被误判，把文件名加进 `filters.adult_allow`（例如 `["ZIP0影视.py"]`）即可豁免。
代价是每个首页正常的脚本多 1–2 次搜索，整轮多约 17 秒。

### 低码率过滤

功能校验会为每个源取前 `quality.max_lines` 条线路（默认 4）各测一集，逐条量码率：

- **HLS**：均匀抽 6 个分片，用 `Content-Length / EXTINF` 算平均码率。不用 master 里的
  `BANDWIDTH`——实测大量源写的是 `128`、`800000` 这种占位值，和分片实测能差 2 倍以上。
- **mp4 / 直链视频**：用 `ffprobe` 读 `bit_rate`（需要本机装了 ffmpeg，没装就记为未知）。
- **音频源**（听书/音乐）和本地代理线路不参与码率判定。

只有**所有采样线路都测到码率、且都低于 `quality.min_bitrate_kbps`（默认 800）**才剔除；
任何一条线路高于阈值、或者测不出来（解析线路、页面、本地代理、抽片失败），源都保留。
默认 800 kbps 大约相当于 480p 以下的码率。

实测 221 个脚本里 76 个能量出码率，7 个被剔除：瓜子APP（360）、分享央视（489）、
低端影视（639）、河马剧场（481–672）、河马短剧（730）、滴答影院（735）、毒舌影视（757）。
像动漫巴士（790/1123/1278）这种只要有一条正常线路就保留。`接口.json` 因此从 64 个站点降到 57 个。

调阈值就改 `quality.min_bitrate_kbps`：实测 700 会少删 3 个（河马短剧/滴答影院/毒舌影视），
1000 会多删 3 个（55影院/6080影视/无极电影网，都在 900–1000 档）。设 `0` 关闭码率过滤。
如果某个源被误判，把文件名加进 `quality.bitrate_allow`。

### 耗时与并发

一次完整流程（221 个脚本）约 **5–6 分钟**：

| 阶段 | 耗时 | 并发 |
|---|---|---|
| 功能校验 + 逐线路播放地址分析 | ~230s | 12 |
| 读取脚本 + host 校验 | ~80s | 12 / 20 |
| 提交推送 | ~5s | — |

逐线路采样是码率过滤的主要开销：每个 HLS 线路要多抽 6 个分片（只请求响应头，不下载内容），
比只测第一条线路多约 70 秒。

功能校验会把脚本缓存到 `%TEMP%\tvbox-py-cache`，生成阶段直接复用（`--source-dir`），
不再重复下载——之前重复下载 221 个文件要走 gh-proxy，光这一项就要 5 分钟。上游删掉的脚本
会自动从缓存清理。并发数在 `config.json` 里调：`functional.workers`（功能校验）、
`functional.stream_workers`（播放地址分析）、`request.workers`（host 校验）、
`request.download_workers`（下载）。

### 自定义

编辑 `scripts/config.json`：

- `accelerator`：GitHub 加速前缀，默认 `https://gh-proxy.com/`。
- `exclude_scripts` / `exclude_names`：排除不想加入的脚本。
- `filters.require_spider_class`：只接受定义了 `class Spider` 的脚本，默认 `true`。
- `filters.dedupe_identical_scripts`：按代码内容去重改名副本，默认 `true`。
- `filters.exclude_adult`：剔除成人内容源，默认 `true`。
- `filters.adult_keywords` / `adult_title_keywords`：自定义分类/标题关键词，留空用内置词表。
- `filters.adult_allow`：误判豁免的文件名列表，例如 `["ZIP0影视.py"]`。
- `functional.adult_probe_keywords`：成人内容探针关键词，默认「麻豆传媒」「被家长调教的女教师」。
- `functional.enabled` / `functional.report`：是否自动读取功能校验报告。
- `functional.min_score`：最低功能评分（0–3），默认 `0` 表示只评分不删源。
- `functional.keyword` / `timeout` / `workers`：搜索关键词、单脚本超时、并发数。
- `quality.min_grade`：最低源质量等级（`A`/`B`/`C`/`D`），默认 `""` 不过滤；设为 `B` 会剔除 C/D。
- `quality.drop_unverified`：是否连「拿不到播放地址（U）」的源一起剔除，默认 `false`。
- `quality.min_bitrate_kbps`：最低码率（kbps），默认 `800`；只有所有采样线路都低于它才剔除，设 `0` 关闭。
- `quality.max_lines`：每个源最多采样几条线路，默认 `4`；超出部分按未知处理，不会因此删源。
- `quality.bitrate_allow`：码率误判豁免的文件名列表，例如 `["低端影视.py"]`。
- `request.accept_4xx`：是否把 403/404 等算作可达，默认 `true`。
- `request.timeout` / `request.workers`：请求超时和并发数。

### 保留自己的首页

在 `接口.json` 的 `sites` 里添加一个 `api` 以 `./` 开头的站点，例如：

```json
{
    "key": "home",
    "name": "首页",
    "type": 3,
    "api": "./脚本/首页.py"
}
```

每次自动更新都会保留它，只替换 http/https 开头的网络站点。