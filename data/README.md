# data/ 目录说明

本目录包含三类内容：**社区格式文档**（安装时获取一次）、**由本机游戏生成的数据**，以及
**本机进度状态**。前两类不进仓库，第三类同样不进仓库；仅本文件（格式说明，属本项目自身文字）
会被提交。

## 1. 社区格式文档：由 `tools/fetch_docs.py` 获取

| 路径 | 来源 | 用途 |
|---|---|---|
| `paramdefs/*.xml` | [Paramdex](https://github.com/soulsmods/Paramdex) | 参数表字段布局，用于读取 regulation.bin。其中 `NpcParam.xml`（商人种类名）与 `WorldMapPlaceNameParam.xml`（地区名）上游未提供，取自 Paramdex |
| `eventflag_bst.txt` | [ER-Save-Lib](https://github.com/ClayAmore/ER-Save-Lib) | 事件旗标分块表，用于判断标记的获得状态 |
| `mfg/*.json` | [Map for Goblins](https://github.com/VirusAlex/ERR-MapForGoblins-DLL) | 物品 id 分类表（灵灰、制作材料、护符、弹药、分类排序等），用于将道具归入界面分类 |

以上文件既非游戏素材，也非本项目成果，按各自条款分发，**不随本仓库提交**。`Setup.bat` 在构建前调用
`tools/fetch_docs.py` 获取一次：

```bash
python tools/fetch_docs.py            # 仅下载缺失文件，已存在则跳过
python tools/fetch_docs.py --force    # 全部重新下载
```

离线时可从 `https://github.com/egormagurin/EldenRingMap/tree/main/data`（或上表三个原始项目）手动
下载到相同路径。Reforged 专用的三个文件（`ember_pieces`、`rune_pieces`、`_piece_final_map`）已不再
获取，本分支不提供模组兼容。

## 2. 由本机游戏生成：不进仓库

每份文件的生成者与用途登记在 `tools/erlib/layers.py` 的注册表中，可用
`python tools/erlib/layers.py check` 输出各层当前标记数：

| 文件 | 生成者 | 内容 |
|---|---|---|
| `markers.json` | `tools/build_markers.py` | 赐福、Boss、据点、地图碎片等世界标记（名称取自游戏官方文本） |
| `regions.json` | `tools/build_markers.py` | 游戏地区名及其矩形范围 |
| `legacy-conv.json` | `tools/build_markers.py` | 母图与子图坐标换算缓存 |
| `items.json` | `tools/extract_items.py` | 道具拾取点、名称与图标编号 |
| `npcs.json` | `tools/extract_items.py`，再由 `dev/link_bell_bearings.py` 补充 `dropsBell` | 商人位置与名称（名称由 extract_items 按最近的赐福生成） |
| `drops.json` | `tools/extract_items.py`，再由 `dev/fix_bell_positions.py` 校正铃珠位置 | 角色一次性掉落，含 29 个商人铃珠（其中 `via: bell-owner` 的 19 个已移至主人坐标） |
| `boss-drops.json` | `tools/extract_items.py` | Boss 击杀奖励 |
| `emevd-drops.json` | `tools/extract_emevd_drops.py` | 事件脚本发放的掉落 |
| `emevd-rewards.json` | `tools/extract_emevd_rewards.py` | 事件脚本发放且无世界物件的奖励 |
| `followup.json` | `tools/extract_followup_lots.py` | 连续 lot 的后续物品 |
| `gather-nodes.json` | `tools/extract_gather_nodes.py` | 采集点（`once` 标记一次性与可刷新） |
| `farm.json` | `tools/extract_farm_nodes.py` | 可刷取材料的地点 |
| `shop-stock.json` | `tools/dev/shop_register.py` | 商店货架及其归属商人 |
| `quest-rewards.json` | `tools/extract_quest_rewards.py` | 任务奖励中可落到坐标的部分 |
| `quest-rewards-unplaced.json` | `tools/extract_quest_rewards.py` | 其余任务奖励，每条含判定与理由，无坐标 |
| `user-verified.json` | 人工 / `tools/dev/place_from_save.py` | 手动核定的位置 |
| `quantities.json` | `tools/annotate_quantities.py` | 每个 lot 实际给予的数量 |
| `layers.json` | `tools/erlib/layers.py policy` | 供客户端使用的层策略（分类所属层与进度口径） |

上述文件包含游戏名称与坐标，属 FromSoftware 的文本与数据，因此由 `.gitignore` 排除，并在本机由
`Setup.bat` 重新生成。

## 3. 本机进度状态：不进仓库

`user-state.json`：界面勾选状态与上次打开的角色。
