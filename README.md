# Elden Ring Live Map · 简体中文版

> **非官方汉化分支｜目前仍在测试与优化中｜因为游戏当中数据有些并非是一对一绑定的所有有些数据可能无法匹配则无法显示**
>
> 把你自己电脑上的《艾尔登法环》变成一张**可交互的实时地图**：
> 查看地图、筛选分类、追踪收集进度，并可在游戏运行时实时显示角色位置。
>
> 本项目基于 [egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap) 开发，
> 由 **MiyauchiRenge** 维护。本仓库与原作者、FromSoftware、Bandai Namco Entertainment
> 均无从属关系，也未获得官方授权。

---

## 项目简介

这是一个运行在**你自己电脑上的《艾尔登法环》本地互动地图**。

地图数据直接从你自己的游戏安装中生成，不需要上传游戏文件，也不需要注册账号。

你可以：

- 查看交界地、幽影之地及地下区域地图
- 按分类显示或隐藏地图标记
- 查看物品、赐福、Boss、据点、地标、地图碎片和商人
- 自动读取角色存档并同步收集进度
- 手动勾选或取消地图标记
- 搜索地图标记
- 查看物品自己的游戏内图标
- 使用游戏自带的简体中文名称
- 在实时模式下显示角色当前位置
- 支持多个角色选择
- 支持 Elden Ring Reforged 模组

**所有主要数据处理均在本机完成。**

地图引擎、游戏数据解析、存档同步、实时位置读取等**核心功能来自上游**
（下节逐条说明本分支改了什么）。

地图瓦片、游戏图标以及根据游戏数据生成的标记数据不会提交到本仓库，
而是在安装时从你自己的游戏中生成。

---

## 当前数据规模

目前从游戏数据中生成了 **4,798 个地图标记**。

> 数量可以直接在地图界面的进度面板中核对：上面一行「总计」是全部标记，
> 下面一行「本层」是当前图层（地图一次只画一个图层）。

| 类型 | 数量 | 说明 |
|---|---:|---|
| 道具拾取点 | **3,251** | 910 种物品；一个事件旗标对应一个拾取点，因此素材、卢恩这类占了近一半（素材 699、黄金卢恩系列约 300、消耗品 166、箭矢 69…） |
| 赐福 / Boss / 据点 / 地标 / 地图碎片 | **1,106** | 赐福 413、据点 294、Boss 208、地标 157、地图碎片 34 |
| 商人 | **21** | 包含游戏中的商人种类名及最近地名 |
| Boss 掉落 | **153** |
| 刷取点（敌人掉落） | **543** | 从杂兵身上随机掉的物品（防具 212 / 武器 121 / 道具 34 / 护符 2 / 战灰 1），标记在**那只怪站着的位置**，卡片写清「这种怪 / 它的掉落表」；不计进度 |
| 一次性奖励（角色掉落 / 任务奖励） | **130** | 挂在敌人或角色身上的奖励，**按奖励本身的种类分 5 档**：角色铃珠 29、角色武器 19、角色防具 9、角色护符 3、角色道具 70。例：`梵雷的花束`←"白面具"梵雷、`王室巨剑`←"半狼"布莱泽、`咖列的铃珠`←"流浪商人"咖列（56 个有名字的给予者，74 个来自无名敌人） |
| **合计** | **5,204** | |

地图标记分布在三个地图层：

| 地图层 | 标记数量 |
|---|---:|
| 地面 | **3,185** |
| 幽影之地（DLC） | **1,180** |
| 地下 | **434** |
| **合计** | **4756** |

为了避免地图被大量小型物品标记覆盖，以下 4 个分类默认收起：

- 素材
- 消耗品
- 杂项
- 箭矢

共计 **1,007 个标记**。需要时可以直接在图例中点开。

---

## 本分支与上游有什么区别？

本项目不是重新开发了一套地图程序，而是基于上游
[EldenRingMap](https://github.com/egormagurin/EldenRingMap)
进行中文本地化和功能扩展。

上游项目已经提供了地图引擎、游戏数据解析、存档同步、实时位置读取等核心功能。

本分支主要增加或修改了以下内容：

| # | 本分支改动 | 上游版本 |
|---|---|---|
| 1 | **物品图标管线**：从 `EquipParamGoods / Weapon / Protector / Accessory / Gem` 中读取图标编号，并提取 `MENU_ItemIcon`（843 个物品图标） | 物品标记使用分类图标 |
| 2 | **强化材料按等级 / 家族拆分**：锻造石、失色锻造石、卢恩、墓地铃兰、灵依墓地铃兰等按等级显示 | 分类粒度较粗 |
| 3 | **简体中文 UI + 游戏官方中文名称**（`i18n.js` 现在是 zh / en 两语；上游的 Русский 字典未保留） | English / Русский |
| 4 | **图例使用物品自己的游戏图标**，并删掉捆绑的分类图标 PNG | 使用 `web/icons/categories/*.png` |
| 5 | **增加商人标记**：从地图 MSB 的 NPC 部件读取商人位置，再通过 `NpcParam → NpcName` 获取名称 | 没有商人标记 |
| 6 | **增加 Boss 掉落**：击败奖励不在任何参数表里（`GameAreaParam` 只有魂量与旗标、也没有 lot 用 Boss 旗标），改从事件脚本里按 Boss 击败旗标定位奖励 lot，再用两条计数过滤去噪；追忆 / 大卢恩另按游戏自己的命名与 Boss 名精确匹配 | 完全没有 Boss 掉落 |
| 7 | **增加一次性奖励**：从 NPC 部件的 `NpcParam` 读 `itemLotId_map / itemLotId_enemy`，取带持久旗标的 lot，得到 130 个"角色掉落 / 任务奖励"，并在提示里写明来源 | 只覆盖地图上的宝箱与尸体 |
| 8 | **增加游戏地区名称**：使用 `WorldMapPlaceNameParam` 显示所在地区及最近地名 | 位置只显示 `The Lands Between` 这一级 |
| 9 | **社区格式文档改为安装时获取**，并在 `Setup.bat` 里真正调用 | 相关文档直接随仓库提供，且没有脚本去取 |
| 10 | **安装 / 启动脚本中英双语**，增加 Python 检测及开发脚本整理 | 英文提示 |

完整的逐文件差异及修改原因：

[docs/汉化说明.md](docs/汉化说明.md)

### 代码差异统计

本分支曾对仓库文件与上游 `main` 进行 Git blob 哈希比对：

- **24 个文件**：与上游逐字节一致
- **22 个文件**：存在修改
- **8 个文件**：本分支新增

上游 `main` 有 143 个文件，本仓库提交 54 个（其余 97 个未纳入，多为本分支用不到的
美术与数据文件）。具体结果及文件列表见
[docs/汉化说明.md](docs/汉化说明.md)。

> 因此这里不把项目描述成"重新开发"或"完全独立项目"。
> 地图核心功能和大量底层代码仍然来自上游，本分支主要负责中文本地化、数据提取扩展
> 和相关工具改动。

---

## 本分支最主要的几个改进

### 1. 游戏官方简体中文名称

地图标记名称不是人工逐条翻译，而是程序直接读取你自己游戏里的消息表：

```text
msg/zhocn/item.msgbnd.dcx        GoodsName / WeaponName / ProtectorName / AccessoryName / GemName
msg/zhocn/item_dlc02.msgbnd.dcx  同上，DLC 新增部分
```

地点、赐福、商人等名称同样取自游戏自己的表（`PlaceName`、`NpcName`），
所以不存在"翻译与游戏对不上"的问题；界面可以在**简体中文 / English** 之间切换。

### 2. 物品图标管线：每个标记显示自己的图标

上游只提取**地图图标**（`MENU_MAP_*`），物品标记统一使用分类图标。
本分支从 `regulation.bin` 的五张 `EquipParam*` 表读出每个物品的图标编号
（`EquipParamGoods +0x030`、`EquipParamWeapon +0x0BE`、`EquipParamProtector +0x0A8`、
`EquipParamAccessory +0x026`、`EquipParamGem +0x004`，均为实测偏移），
再从 `MENU_ItemIcon` 提取出 **843 个物品图标**；3,347 个道具标记**全部**带上了自己的图标，
所以"这是哪一把剑、哪一级锻造石"一眼可辨。图例也跟着改用物品自身图标，
捆绑的 `web/icons/categories/*.png` 因此可以删除。

### 3. 图例图标：分类行可以钉在某个物品的图标上

每个标记显示自己的图标（`iconId` 由 `tools/extract_items.py` 从游戏参数表读出）；
**分类行**（侧栏图例）用的图标则是「该分类下标记最常带的那个」推断出来的，个别分类在
`web/js/app.js` 的 `CAT_ICON` 里手工指定。按需求钉了四行：

| 分类行 | 图标 | iconId |
|---|---|---|
| 角色掉落·武器 | 暗月大剑 | 10089 |
| 角色掉落·防具 | 雪魔女尖帽 | 14740 |
| 角色掉落·护符 | 观星少女的传说 | 18090 |
| Boss 掉落 | 追忆 | 163 |

物品图标是**按需**从游戏里抽的（只抽标记真正用到的 iconId），而这四件物品没有任何标记
引用（脚本奖励 / 帽子 / 护符 / 追忆），所以 `tools/extract_icons.py` 里列了一份
`LEGEND_ICON_IDS`，把这四个 id 一并抽出来。图片本身是游戏素材，`web/icons/*` 已被
.gitignore 排除，仓库里只有这几个数字。

### 4. 强化材料按等级 / 家族拆行

上游把锻造石分成"低 / 中 / 稀有"三档，铃兰只有一行。本分支按等级拆开：
锻造石与失色锻造石各 1–9 级、墓地铃兰与灵依墓地铃兰各 1–9 级加大朵，
一眼看出缺哪一级。

- 有 7 个等级（墓地【2】-【4】、灵依【1】-【4】）**地图上没有放置点**，所以图例里没有它们的位置。
  但它们并非只能买：`ItemLotParam_enemy` 里都有它们，也就是**可以从敌人身上刷到**，
  同时 `ShopLineupParam` 里也有售（1200-3600 卢恩）。
- 全局 18 个铃兰等级中，地图上呈现 13 行。

### 5. 商人位置与名字

游戏自带的地图数据里没有商人点（`WorldMapPointParam` 只有"隐居/遁世商人的破屋"，
`BonfireWarpParam` 只有对应赐福），所以商人位置从各张地图 MSB 的 NPC 部件里读：

- 模型 `c3200` = Nomad Trader、`c3210` = Nomad Mule（社区 chr 表）；在三个破屋地图里
  各有一个 c3200 且各有一个 c3210，两条证据互相印证，只标商人、不标驮驴。
- 名字：`PARTS_PARAM_ST +0x2AC` 是 `NpcParam` 行号，再跟 `NpcParam.nameId` 查
  `NpcName` 得到**游戏自己的种类名**，并配上最近的官方地名，
  例如 `「流浪商人」咖列（艾雷教堂）`、`流浪民族的商人（圣人桥）`、`遁世商人（安瑟尔河下游）`。
- 游戏里 8 处无名的 `DummyEnemy` 占位（`NpcName` 是开发者占位串、身边也没有驮驴）
  不标记，因此最终是 **21 个**商人。

### 6. 一次性奖励：角色掉落与任务奖励

游戏把"世界上放着的东西"记成 treasure 事件，所以拾取点提取**只能覆盖宝箱与尸体**；
敌人打死后掉的东西、角色交给你的东西都不在其列。它们挂在角色的 `NpcParam` 行上：

- `itemLotId_map` = 脚本 / 任务奖励，`itemLotId_enemy` = 击杀掉落；
- 角色的行号就在我们已经遍历的 MSB 部件里（`+0x2AC`，与商人用的是同一个字段），
  所以这是同一趟扫描里多读一张表，安装时间几乎不变；
- **判据只有一条**：lot 带持久 `getItemFlagId`（可反复刷的掉落是 0）。全量数据下这过滤掉
  27,427 个可刷 lot，留下 **130 个一次性奖励**。

结果形如 `梵雷的花束`（来源：`"白面具"梵雷`）、`王室巨剑`（来源：`"半狼"布莱泽`）、
`咖列的铃珠`（来源：`"流浪商人"咖列`）、`风暴鹰斧`（来源：`战士涅斐丽·露（13 处出现）`）。
74 个奖励来自游戏自己都没命名的敌人（`NpcName` 是开发者占位串），那时只显示物品本身，
不编造名字。物品保留自己的名字与图标，提示气泡多一行"来源"。

奖励再**按它本身是什么分 5 档**（铃珠不是武器，玩家找的是种类）：
**角色铃珠 29**（咖列 / 帕奇 / 葛托克 / 瑟濂 / Ｄ / 柯林 / 米利耶 / 贝纳尔 / 托普斯 / 穆尔，
以及流浪、隐居、遁世、见弃、受囚商人的铃珠【1-10】）、**角色武器 19**（王室巨剑、风暴鹰斧、
灭洛斯剑、紧密孪生剑、霍斯劳花瓣鞭、梵雷的花束、弗蕾亚的大剑、埃贡的大弓…）、
**角色防具 9**（铁笠帽、苍银风帽、卢瑟特／亚兹勒辉石头冠、猎犬骑士头盔…）、
**角色护符 3**（米莉森的义手、战士壶碎片、狄蒂卡之祸）、**角色道具 70**（伊蕾娜的信、
菈雅的项链、野兽眼眸、埃贡的勾指、纯净金针、黄金种子、圣树秘密符节…）。

铃珠**按"它解锁什么"归档，而不是按谁掉的**：锻造石矿工、失色石矿工、铃兰摘采工、
灵依摘采工的铃珠各自进已有的锻造石 / 失色石 / 铃兰 / 灵依铃兰行（判据复用拾取点的
同一个分类器，将来若出现角色掉落的锻造石铃珠会自动落到那一行）；其余商人 / 角色铃珠
留在「角色铃珠」。本作 29 个角色铃珠恰好**没有一个是锻造石 / 铃兰系**。

### 7. Boss 掉落

击败 Boss 得到的东西**不在任何参数表里**：`GameAreaParam`（我们用它做 Boss 标记）只有
魂量与旗标，也没有任何 `ItemLotParam` 行把 Boss 的击败旗标当作自己的 `getItemFlagId`
（两条都实测过）。奖励是**事件脚本**在 Boss 死亡时发的。

反编译 EMEVD 是另一个量级的工程，所以这里复用 `build_markers.py` 找 Boss **名字**时
用的同一招：击败旗标是精确已知的值，就在该 Boss 自己的 `.emevd` 里搜它，并在附近找
"是真实 `ItemLotParam_map` 行、且带持久旗标"的字。单靠这个噪声太大——
`lot10000`（护符皮袋）与 `lot20000`（"无头骑士"露缇尔）在 60 多个 Boss 附近都出现，
因为是共享脚本代码——于是用两条**纯计数**的过滤压掉：

* 该 lot 只能出现在**一个** Boss 附近；
* 该 lot 只能出现在**一个** `.emevd` 文件里。

剩下的正是经典 Boss 掉落表：大树守卫→黄金戟、黑刀刺客→黑刀、神皮使徒→神皮剥制剑、
老将欧尼尔→老将的军旗、龙装大树守卫→大龙爪、飞龙→龙心脏、黄金树的化身→结晶露滴、
提比亚的唤声船→死根……共 **136 个**。它的判据是"脚本邻近 + 计数过滤"，因此是**高置信、
但非零误差**：已知一处可疑——`贝勒的心脏`落在了「鲜血君王」蒙格名下（该物品属 DLC）。

**追忆 / 大卢恩另走一条精确路径**（31 个）：它们由共享脚本发放，脚本扫描抓不到，
但游戏是**按 Boss 命名**它们的，所以"接肢的追忆"直接匹配到「接肢」葛瑞克
（先比名号本身，再比称号；同日名时优先本体而非 DLC；歧义或无匹配的一律不标）。
这条规则还纠正了脚本扫描的一处误判（拉塔恩的大卢恩曾落在神皮使徒名下）。

### 8. Boss 掉落的人工核定归属

Boss 击杀奖励常由 EMEVD 直接按 lot 发放，脚本里看不出"是哪个 Boss 给的"，自动流程只能
放弃（`剑骸大剑` 就是这种：武器 id 4100000 只出现在 map lot **10800**、旗标 510800，
且**没有任何 NpcParam 指向它**——所以它不是怪身上的掉落）。这类归属集中放在
`data/boss-drop-overrides.json`，每条都写明来源，便于复核与删除：

* lot 与旗标来自游戏文件（已核实）；**只有"归哪个 Boss"是人工条目**；
* 标记仍然落在**那个 Boss 的坐标**上（`狮子混种` (3936, 8854) M00），卡片与图鉴里
  都标 `via: curated`，来源写在 `note` 里；
* 目前 1 条：`剑骸大剑` ← `狮子混种`（啜泣半岛·摩恩城 Boss）。来源为 wiki 线索；Game8 /
  Eurogamer / 17173 等站点拒绝自动抓取，故未引用正文；
* 本项目默认**不猜**：没有这条目时，它只会在图鉴里显示为"脚本发放（无位置）"。

### 9. 位置说明使用游戏自己的地区名

提示气泡与搜索结果里原来只写地图层名（`The Lands Between` / `交界地`），
等于没说——三千多个道具全在"交界地"。

本分支读 `WorldMapPlaceNameParam`（大地图上那 9 块地区名的来源）生成
`data/regions.json`，界面上改显示 **地区 + 最近地名**：

```text
道具 · 湖之利耶尼亚（彼鲁姆教堂）
商人 · 湖之利耶尼亚（彼鲁姆教堂）
```

地区共 9 个：宁姆格福 / 湖之利耶尼亚 / 亚坛高原 / 盖利德 / 巨人山顶 /
安瑟尔河 / 希芙拉河 / 深根底层 / 幽影之地。最近地名取自游戏赐福与据点名，
并限定在同一地图层（地下与地面共用主图坐标，否则希芙拉河的商人会被标上地面的地名）。

### 10. 同一点位上的多个标记都能点到

Boss 与它的掉落、叠在一起的采集物**坐标完全相同**（实测 3 像素内 321 组重叠，
完全同一坐标的 258 组、667 个标记），而点击只会返回最近的那一个——叠在下面的根本点不到。

现在：

- 卡片里多一行 **“此处还有”**，列出该点的**全部**标记：顺序固定不变，正在看的那一项用**方框**标出
  （而不是从列表里消失——列表一重排人就跟丢位置了）；点任意一项即可切换。条目多时列表内部滚动。
  同点标记在任何缩放下距离差都是 0，因此永远在同一组里。
- 同名同点的重复也会合并：游戏里 `葛瑞克的大卢恩` 同时是道具 8148 与 191，两个 lot
  挂在同一个 Boss 上，导出时会去掉重复的一条（共合并 15 个）。

参考项目 ChenxiLiu-code/EldenRingTool（LGPL-3.0，只借鉴做法、未复制代码）用世界坐标 +
屏幕像素预算聚合，并豁免 Boss；但它的掉落标记同样落在敌人坐标上、界面里也没有同点列表，
所以它并没有解决“同一点点不到”。
### 11. 采集点单列，且不进收集进度

游戏数据**分不出**"地里采的"和"箱子里拿的"：两者都是 `EVENT_TYPE_TREASURE = 4` 事件，
挂载的部件模型也完全重叠（实测采集类与黄金卢恩类共用 `AEG099_610_9000/9001/9002`）。
所以"采集点"只能**按物品**定义——用 Map-for-Goblins 分类表里那份制作材料清单。

- 它们单列成一类 **`gathering`（采集点）**，共 **603** 个标记；
- **同名同点合并**：一处灌木上可以有十几个坐标完全相同的事件，合并成一个标记并记下
  `nodes`（共 699 个采集事件，603 个标记），卡片里显示"此处节点：N 个采集点"；
- **不带旗标**、**不计入进度总计**：这些节点休息一次就重生，勾掉没有意义，
  进度条把它算进去会永远到不了 100%%，农场一次还会倒退。图例那一行改显示"N 处"而不是"已得/总数"；
  想手动勾的仍然可以在卡片里勾（没有旗标的标记本来就只能手勾）。

因此**进度口径**是 **4,058**，而地图上的标记总数是 **5,204**（两者相差的就是采集点与刷取点）。

### 12. 可刷点：把敌人掉落标到地图上（参考项目没做）

采集点解决的是"地里长的"，这一节解决"敌人身上的"。敌人掉落的 lot（`ItemLotParam_enemy`）
**没有自己的坐标**——它挂在 `NpcParam` 上，也就是挂在**角色**上。参考项目
（ChenxiLiu-code/EldenRingTool）到此为止：它的 `enemy_drop` 来源只有 lot 号、没有位置。

本分支把剩下的链条走完：MSB 部件 → `+0x2AC`（`PART_NPC_PARAM_ID`）→ `NpcParam` →
`itemLotId_enemy`，于是"这东西去哪刷"在地图上有答案：

* 工具 `tools/extract_farm_nodes.py` → `data/farm.json`，**138 个刷取点**；
* 只处理**地图上没有放置点**的等级（墓地【2】-【4】、灵依【1】-【4】），否则常见杂兵会把
  地图淹掉；每个 lot 最多留 60 处（`--per-lot`），标记里带 `sites` 记录全图处数；
* 刷取点**不计进度**（敌人会重生）；

  `itemLotId_enemy` lot 里的全部物品，不只你查的那一件），最后才写"刷取点：这里的敌人会
  掉落此物 · 全图共 N 处"。游戏几乎没有给敌人起名（`NpcName` 表里这些行是空的），所以

参与这 3 个等级的怪共 4 种：`c4180` 91 处、`c5880` 29 处、`c5870` 15 处、`c5513` 3 处；
每个 enemy lot 里只有那一件铃兰（所以"它的掉落表"通常就一行，这是数据本身的样子）。
另外 `--items "名字"` 可以对任意物品做同样的查询，不必局限于铃兰阶梯。

查证结果：7 个等级里有 3 个能找到刷取点（墓地【2】49 处、墓地【4】57 处、灵依【4】32 处）；
另外 4 个（墓地【3】、灵依【1】【2】【3】）**扫描全部 1,248 个 MSB 后一个部件都没找到**，
所以"去哪刷"在这些数据里没有答案，和参考项目一样只能列在来源里（为什么没有，本项目没有
进一步查证，只如实记下这个否定结果）。

另外新增 `--all-unmarked`：**自己挑目标** —— 扫 `ItemLotParam_enemy`，把所有「能从敌人身上
刷到、但地图上一处都没标」的物品找出来，逐一标出该敌人的出现位置。实测这一批是 **370 种**
（防具 212 / 武器 121 / 道具 34 / 护符 2 / 战灰 1），落在**405 个标记**上（每 lot 上限 60 处），
加上铃兰阶梯的 138 个，`farm.json` 共 543 个。能对上铃兰阶梯的物品仍归各自的等级行（图例
阶梯保持完整），其余统一进新分类 **`farm_spots`（刷取点（敌人掉落））** —— 标记本身带物品名
和物品图标，所以一个分类就够，不必每件物品一行。它们同样**不计进度**。

**这一批完全不需要 wiki**：归属来自 `NpcParam.itemLotId_enemy`（是哪只怪），坐标来自 MSB 部件
（它站在哪）。wiki 只能用来核对，不能作为数据来源。

### 13. 两种启动方式，以及"关掉网页就停服"

* **`Start Map.vbs`** —— 双击即用，**不显示任何命令行窗口**（窗口样式 0 隐藏），
  所有输出写进 `logs\map-server.log`；参数与 .bat 完全相同（`--live` / `--lan` …）。
* **`Start Map.bat`** —— 保留给需要看日志或看启动报错的时候（它是有窗口的那个）。

隐藏窗口带来一个必须一起解决的问题：**看不见的进程不能一直留着**。所以服务会在页面全部
离开后自己退出：

* 页面每 5 秒发一次心跳（`GET /api/ping`），服务端据此刷新"最后活动时间"；
* `pagehide` 时用 `sendBeacon` 发 `POST /api/bye`，服务端**等 8 秒宽限**再退出——刷新页面
  也会触发 `pagehide`，而刷新后的页面一秒内就会重新心跳，所以刷新不会误杀服务；
* 兜底：完全没有任何请求达到 `--idle-exit`（默认 150 秒）就退出（浏览器会把后台标签页的
  定时器降频，所以这个值给得宽）；
* `--idle-exit <ms>` 可调，`--no-idle-exit` 可关闭（想在页面关掉后继续留着服务时用）；
* `/api/bye` 只接受来自 localhost/127.0.0.1 的 Origin，别的网站无法用它关掉你的服务；
* 界面里原有的"退出服务"按钮仍然有效，并且 `--lan` 模式下只有它和空闲超时能停服务。

### 14. 社区格式文档改为安装时获取（并真正接进 Setup）

Paramdex 的参数定义、ER-Save-Lib 的旗标表、Map for Goblins 的 id 分类表
都不属于本项目，因此**不随仓库提交**，改由 `tools/fetch_docs.py` 在安装时取一次
（`Setup.bat` 的 `[2/9]` 步，在读取任何参数表之前）。其中两个定义上游没有、
从 Paramdex 取：`NpcParam.xml`（商人名字）与 `WorldMapPlaceNameParam.xml`（地区名）。

---

## 快速开始

前置：**正版游戏**（用来提取底图与数据）、**Node.js ≥ 18**、**Python ≥ 3.9**。

### Windows

1. 双击 **`Setup.bat`**（几分钟：装 Python 依赖 → **获取社区格式文档** → 提取瓦片 →
   生成标记数据与地区表 → 提取道具与商人位置 → 提取图标）。找不到游戏时，按脚本顶部的
   注释把 `GAMEDIR` 填成含 `eldenring.exe` 的目录再运行。
2. 双击 **`Start Map.bat`**，浏览器打开地图。

> ⚠️ 服务器在**启动时**读一次数据文件。跑完 Setup（或重新生成了 `data/` 下的文件）之后，
> 要**重启** `Start Map.bat`，并在浏览器里 **Ctrl+F5** 强制刷新，才能看到新增的标记。

### Linux

```bash
./setup-linux.sh      # 同上，另外会本地编译 linoodle 用于解压游戏归档
./start-map.sh
```

### 实时模式

游戏运行中、并且**已经读取了一个角色**（不是标题画面）时：

- 双击 **`Check Live Mode.bat`**（会请求管理员权限）做一次性自检，确认能挂上游戏、
  且本版本的字节签名仍然匹配，日志写在 `cache\live-probe.log`；
- 自检通过后启动 `tools/live_memory.py`（`Start Map` 的实时模式会用它），
  地图上会出现随时间平滑移动的玩家光点。

读取方式是**只读**的：只以 `PROCESS_VM_READ` 打开进程，不写游戏内存，
也完全不碰你的存档。需要管理员权限，因为游戏本身通常以管理员身份运行。

---

## 目录结构

```
Setup.bat / setup-linux.sh     一键安装：取社区文档 + 提取 + 生成
Start Map.bat / start-map.sh   启动本地服务器与界面
Check Live Mode.bat            实时模式自检

server/                        Node 静态服务器 + 存档解析 + 实时内存读取
web/                           前端：index.html、css/、js/（map.js 画布、app.js 界面、i18n.js 文案）
tools/                         全部 Python 工具
  extract_tiles.py             从游戏提取地图瓦片      -> web/tiles/          [上游]
  extract_icons.py             提取地图图标与物品图标  -> web/icons/          [上游 + 本分支]
  build_markers.py             生成世界标记与地区表    -> data/markers.json、data/regions.json [上游 + 本分支]
  extract_items.py             生成道具标记与商人      -> data/items.json、data/npcs.json
  extract_pieces.py            Reforged 碎片（可选）   -> data/pieces.json
  fetch_docs.py                取社区格式文档          -> data/paramdefs/、data/mfg/…
  fetch_tips.py               抓取路线说明（可选）    -> data/tips.json
  erlib/                       读游戏归档、参数表、MSB/FMG 的底层库
  dev/                         开发与调试脚本
data/                          数据集与格式文档，见 data/README.md
docs/汉化说明.md               本分支改了什么、为什么（含与上游的逐文件差异）
```

`web/`、`data/` 下的实际内容由 `Setup.bat` 生成，仓库里为空或只有说明文件。

---

## 授权与来源

| 部分 | 说明 |
|---|---|
| 本分支新增与修改的代码 | **MIT**，见 [LICENSE](LICENSE) 第一部分 |
| 上游 [egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap) | 上游**未附 LICENSE**，代码默认保留所有权利；本分支的 MIT **不覆盖**它，见 LICENSE 第二部分 |
| 游戏素材（瓦片、图标、名称、坐标） | 版权属 **FromSoftware / Bandai Namco**；本仓库不含，也不授权 |
| 社区格式文档 | [Paramdex](https://github.com/soulsmods/Paramdex)（参数定义）、[ER-Save-Lib](https://github.com/ClayAmore/ER-Save-Lib)（旗标表）、[Map for Goblins](https://github.com/VirusAlex/ERR-MapForGoblins-DLL)（物品 id 分类表）——按各自条款分发，安装时获取，不随仓库提交 |
| 路线说明 | Fextralife wiki 的写作成果，其条款要求不得自动抓取、不得转载；工具只在你本机保存 |

本项目与 FromSoftware、Bandai Namco 无任何关联，未获其授权或认可。

---

## English

**Elden Ring Live Map, Simplified Chinese edition** — an **unofficial** fork of
[egormagurin/EldenRingMap](https://github.com/egormagurin/EldenRingMap), maintained by
**MiyauchiRenge** and not affiliated with its author. Upstream ships no LICENSE file, so
its code is all rights reserved; this repository licenses only its own additions — see
[LICENSE](LICENSE) and [docs/汉化说明.md](docs/汉化说明.md).

**What is upstream's and what is this fork's.** The bulk of the project — the game
archive/param/MSB/FMG readers, tile extraction, world markers, item pickup extraction,
save parsing and progress ticking, live mode, route-description fetching, mod support,
and the whole web UI — is upstream's. This fork added: the **item-icon pipeline** (upstream
extracts only map icons), **per-level/per-family splitting** of upgrade materials and
gloveworts, the **Simplified Chinese UI with the game's own Chinese marker names**, the
legend drawn from each item's own sprite, **merchant markers with their own names**
(21, read from `c3200` NPC parts, named through `NpcParam` -> `NpcName`), **region names
from the game** (`WorldMapPlaceNameParam`) in the popup and the search results,
community format docs fetched at setup time instead of committed, and
bilingual setup/launcher scripts.

Point it at your own installation and it builds an interactive map of 5,204 markers:
3,251 item pickups (910 distinct items), 1,106 graces / bosses / points of interest /
map fragments, 21 named merchants, 130 one-time rewards that hang off a character
(Patches' Bell Bearing, Nepheli's Stormhawk Axe, the Nomadic Merchants' Bell Bearings)
and 152 boss rewards (Tree Sentinel -> Golden Halberd, Black Knife Assassin -> Black
Knife, plus 31 Remembrances and Great Runes matched by the game's own naming),
spread over three map layers (surface 3102, Realm of Shadow 1133, underground 425).
Sources are tracked per
character from your save file, and a live mode follows the player while the game runs
(read-only, and it needs administrator rights because the game itself runs elevated).

**This repository is code only.** Map tiles, the game's icons and the generated
datasets are FromSoftware's artwork and text: they are produced from *your* copy of
the game by `Setup.bat` (or `./setup-linux.sh`) and are not committed here. Community
format documentation (Paramdex, ER-Save-Lib, Map for Goblins) is fetched by
`tools/fetch_docs.py` for the same reason. See [LICENSE](LICENSE).

Requires the game, Node.js 18+ and Python 3.9+. Run `Setup.bat` then `Start Map.bat`
on Windows, or `./setup-linux.sh` then `./start-map.sh` on Linux.
