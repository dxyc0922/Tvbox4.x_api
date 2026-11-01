# Tvbox4.x_api

适配安卓4.x的tvbox接口

- 源地址：https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- Github加速地址：https://gh-proxy.com/https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口.json
- 远程直链版（生成站点用 gh-proxy 绝对链接，不带 `脚本/` 目录也能用）：
  https://raw.githubusercontent.com/dxyc0922/Tvbox4.x_api/refs/heads/main/接口-remote.json

说明：由于盒子是安卓4.x会导致加载一些新的接口会崩溃、无法加载、无法播放等异常情况，
况且有些线路含18禁内容不适合在电视上展示，以及一些线路含赌博广告、播放卡顿等问题都需要清除。

1. 符合下面要求的接口会添加进接口给电视用。
2. 在电视盒子上接口加载正常；自营线路播放正常。
3. 不存在18禁内容，比如伦理、福利等分类；搜索「女教师」等关键字无漏点图。
4. 无赌博广告，播放不卡顿，比如 cms 资源站的资源一般都不合格。
5. 直播使用本地电信组播 IPTV 源，需要路由器启用 IGMP 嗅探。

## 自动更新

`scripts/update_api.py` 从**多个上游仓库**（`config.json` 的 `upstream` 列表，默认
`wzxxcz/wzxxcz` + `zzq1234567890/tvbox1` + `jak0099/dr` + `maoystv/6`）拉取 py 脚本，按文件名去重，
校验后同步到 `脚本/` 目录、重建 `接口.json`，定时在**本机**运行（Windows 任务计划程序）。

```powershell
# 先手动跑一次，确认能生成、能推送
python scripts/run_local.py --dry-run     # 只校验，不写文件
python scripts/run_local.py               # 校验 + 生成 + 提交推送

# 注册每周任务（默认每周一 02:00）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1

# 注册两套任务：每天 update_api 快速刷新 + 每周完整功能校验
#  - TVBox-UpdateApi：每天 02:00 跑 update_api（不执行第三方脚本，用已有功能报告过滤）
#  - TVBox-UpdateApi-Functional：每周一 02:30 跑 --functional（完整校验，执行第三方脚本）
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -Daily -Time 02:00
powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 -TaskName TVBox-UpdateApi-Functional -Functional -Time 02:30 -Day Monday
```

`run_local.py` 每次：`git pull` → 可选功能校验（`--functional`）→ 重建 `接口.json` →
有变化才提交推送。日志写在 `logs/local-run-<时间>.log`。

`接口.json` 的生成站点 `api` 指向本地 `./脚本/<脚本名>.py`（随仓库发布）；
`接口-remote.json` 用 gh-proxy 绝对链接，只发布单个 JSON 也能用。

## 每周搜新源

项目不依赖固定仓库——若上游删库/分支变动，重新按关键字搜 GitHub 收集新源。
`scripts/search_new_sources.py` 每周搜 GitHub（tvbox/接口/影视源等关键词），
排除已接入的 4 上游，筛选最近活跃 + 有 py 脚本的仓库，输出建议加入的 upstream：

```powershell
python scripts/search_new_sources.py          # 搜索 + 写建议 reports/new-source-candidates.json
python scripts/search_new_sources.py --dry-run  # 只打印不写
```

实测找到 6 个候选（qist/tvbox 12518★、cluntop/tvbox 637★ 等），并排除非源仓库
（播放器壳/不带内容源）。候选加入 `config.json` 的 `upstream` 后由功能校验
（三方法门槛）筛选去留。

## 筛选机制（概述）

`接口.json` 只保留**验证过的高质量源**；源级质量过滤（低质/低码率/慢速）**立即剔除**，
线路级走「两振出局」（连续两轮差才剔除）：

| 机制 | 说明 |
|---|---|
| 功能校验 | **硬门槛**：真正调用 `searchContent`/`detailContent`/`playerContent`，任一失败=源废（不评分）；homeContent/分类不重要（豆瓣.py `categoryContent` 提供）。搜索词用**最新**动漫/剧集（豆瓣非凡分类），带**降级链**兼容同名不同源 |
| 源质量分级 | A 高画质+快 / B 画质速度达标 / C 偏低 / U 画质未知；**只按画质+速度，不看链接类型**（直链/解析/page 无区别）；**音频**（听书/音乐）无分辨率**按码率分级**（≥320K+快=A、≥128K=B）；U 级**音频源保留、非音频剔**（用户实测 page/local/无线路/unknown 有问题） |
| 低码率过滤 | 按分辨率分档 + bpp 下限（`min_bpp=0.05`），只留真正高码率源 |
| 加载速度过滤 | 实测吞吐/启动耗时，只留流畅源 |
| 线路级裁减 | 给脚本注入过滤，去掉不通/低质/慢速线路（同源另有达标线路才删）；线路级两振 |
| 线路级推荐 | 注入脚本按画质速度**重排线路**（最优排第一，TVBox 默认播它）；未知线路保持原序后置 |
| 成人内容过滤 | 分类名 + 探针搜索，自动剔除 |
| 源级质量 | 低质（C/D/U）/低码率/慢速源**立即剔除**（不走两振），只留 A/B |

站点按**质量排序**：等级 → 最高 bpp（画质密度）→ 速度比 → 名称（功能 score 不参与评分，只作门槛），接口第一个就是最好的源。

详细规则、阈值、判定逻辑见 [docs/技术说明.md](docs/技术说明.md)。

## 配置

编辑 `scripts/config.json`，常用项：

| 配置 | 默认 | 说明 |
|---|---|---|
| `upstream` | 4 个仓库 | 上游 py 脚本仓库列表（`owner/repo/branch/path`），按文件名去重合并 |
| `quality.min_grade` | `"B"` | 最低源质量等级（A/B/C/D），设 `""` 不过滤 |
| `quality.drop_unverified` | `true` | U 级**非音频**（page/local/无线路/unknown）源剔除；音频源（听书/音乐，无分辨率）保留 |
| `quality.dynamic_grade_thresholds` | `false` | 按源池分布动态算分级阈值（P75/P50，只收紧），默认固定阈值 |
| `quality.min_bpp` | `0.05` | 每像素每帧最低比特数，设 `0` 关闭 |
| `quality.min_speed_ratio` | `0.7` | 实测吞吐 ÷ 码率下限，设 `0` 关闭 |
| `quality.max_startup_ms` | `12000` | 播放列表+首个分片首字节耗时上限（毫秒） |
| `quality.line_prune.dead_status_min` | `0` | 4xx 视为死线路的状态码下限；`0`=连续两轮 4xx 才删 |
| `quality.line_prune.blacklist` | `{}` | 手动剔线路名，默认空（交给规则自动走两振） |
| `exclude_scripts` / `exclude_names` | `[]` | 排除不想加入的脚本 / 站点 |
| `quality.bitrate_allow` / `speed_allow` | `[]` | 码率 / 速度误判豁免 |
| `filters.exclude_adult` | `true` | 成人内容过滤 |
| `filters.adult_allow` | `[]` | 成人误判豁免 |
| `jsm_sync` | 开启 | 从 `qist/tvbox` 的 `jsm.json` 同步 `hosts`/`doh`/`rules`/`ads` |

完整配置清单、阈值表见 [docs/技术说明.md](docs/技术说明.md)。

## 自定义

- **保留自己的首页**：`sites` 里加一个 `api` 以 `./` 开头的站点（如 `./脚本/首页.py`），
  自动更新只替换 http/https 开头的网络站点，它保留。
- **`lives`（广东IPTV组播）和 `wallpaper`（深色壁纸）**是自定义字段，不会被 jsm 同步覆盖；
  `hosts`/`doh`/`rules`/`ads` 始终跟随上游 `jsm.json`。

## 开发工具

```bash
python scripts/update_api.py --dry-run         # 只校验不写
python scripts/functional_check.py --limit 20  # 功能校验（跑第三方代码，建议虚拟机）
python scripts/stream_check.py "<m3u8>" --site-host https://x.com   # 单独看某个播放地址
python scripts/ban_line.py 某源.py --line 某线路  # 手动剔线路（默认不用，交给规则）
```
