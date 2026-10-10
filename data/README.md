# data/ 里放什么 / what lives here

这个目录里的内容**分三类**，其中两类不进仓库。

This directory holds three kinds of file. Two of them are never committed.

## 1. 社区格式文档 —— `tools/fetch_docs.py` 自动获取

| 路径 | 来源 | 用途 |
|---|---|---|
| `paramdefs/*.xml` | [Paramdex](https://github.com/soulsmods/Paramdex) | 参数表字段布局，读 regulation.bin 用。其中 `NpcParam.xml`（商人种类名）与 `WorldMapPlaceNameParam.xml`（地区名）上游没有，从 Paramdex 取 |
| `eventflag_bst.txt` | [ER-Save-Lib](https://github.com/ClayAmore/ER-Save-Lib) | 事件旗标索引，判断"这个标记拿到了吗" |
| `mfg/*.json` | [Map for Goblins](https://github.com/VirusAlex/ERR-MapForGoblins-DLL) | 物品 id 分类表，把道具归入界面上的分类 |

都不是游戏素材，但也不是本项目的成果，因此以 MIT/各自条款分发，并**不随本仓库提交**——
`Setup.bat` / `setup-linux.sh` 会在构建前调用 `tools/fetch_docs.py` 取一次：

```bash
python tools/fetch_docs.py            # 缺失的才下载，已有就跳过
python tools/fetch_docs.py --force    # 全部重新下载
```

离线时可以从 `https://github.com/egormagurin/EldenRingMap/tree/main/data`
（或上表三个原始项目）手动下载，放到同样的路径即可。

## 2. 从你的游戏生成 —— 不要提交

| 文件 | 生成者 | 内容 |
|---|---|---|
| `markers.json` | `tools/build_markers.py` | 赐福、Boss、地点、碎片等世界标记（名字取自游戏官方文本） |
| `items.json` | `tools/extract_items.py` | 道具拾取点、名称与图标编号 |
| `npcs.json` | `tools/extract_items.py` | 商人位置与名字（同一个 MSB 遍历顺带产出，`c3200` 流浪商人；名字来自 `NpcParam` → `NpcName`） |
| `regions.json` | `tools/build_markers.py` | 游戏的地区名（宁姆格福、湖之利耶尼亚……）及各自范围，界面用它说明"这个标记在哪" |
| `catalog.json` | `tools/build_catalog.py` | 图鉴数据：游戏命名的每件物品一条 + 来源列表（拾取 / 角色奖励 / Boss / 可刷掉落 / 商店含价格 / 脚本发放 / 不可考）。数据来自游戏自己的消息表与参数表，不抓 wiki |
| `boss-drops.json` | `tools/extract_items.py` | Boss 掉落：从事件脚本按击败旗标定位奖励 lot（两条计数过滤去噪），追忆/大卢恩按 Boss 命名精确匹配；位置用对应的 Boss 标记 |
| `drops.json` | `tools/extract_items.py` | 一次性奖励（角色掉落 / 任务奖励）：从 NPC 部件的 `NpcParam` 读 `itemLotId_map / itemLotId_enemy`，只取带持久旗标的 lot，按奖励种类分为角色铃珠 / 武器 / 防具 / 护符 / 道具 5 类，并带来源名字与"共几处出现" |
| `legacy-conv.json` | `tools/build_markers.py` | 地图坐标换算缓存 |
| `pieces.json` | `tools/extract_pieces.py` | Reforged 卢恩/余烬碎片（仅装了该模组时有） |
| `tips.json` | `tools/fetch_tips.py` | 路线说明，抓自 Fextralife wiki，仅供本机自用 |

这些文件里是**游戏的名字与坐标**，属于 FromSoftware 的文本与数据，
所以 `.gitignore` 挡着它们；`Setup.bat` 会在你自己的机器上重新生成。

## 3. 你自己的进度 —— 不要提交

`user-state.json`（勾选状态）、`timeline.jsonl`（实时模式的时间线）。
