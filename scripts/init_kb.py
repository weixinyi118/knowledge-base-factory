#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb-factory / init_kb.py — 3 秒拉起一套可交付的知识库骨架。

生成的东西:
    目录结构 / 00_总目录 / 每个分类的 _分类索引 /
    _内容标准 / _交付说明 / _验收单 / _篇目清单.csv 表头 /
    tools/check.py + tools/export.py（库自带体检与打包能力）/
    _示例篇目.md（一篇合格的样张，让人立刻看到标准长什么样）

不生成的东西:
    正文内容。内容按 _内容标准_去AI味与质检清单.md 逐篇生产。
    骨架负责"不会走歪"，内容负责"值得读"。

用法:
    python init_kb.py ../我的知识库
    python init_kb.py out --name "开元OPC知识库" --preset opc
    python init_kb.py out --preset content --no-cards
    python init_kb.py out --categories "01_市场:需求与竞争|02_产品:功能与定价"
"""

import argparse
import csv
import re
import shutil
import sys
import time
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
TODAY = date.today().isoformat()

# ---------------------------------------------------------------- 分类预设
PRESETS = {
    "opc": {
        "desc": "一人公司 / 个人创业",
        "cats": [
            ("01_一人公司商业思维", "商业模式、定价、现金流、杠杆选择、窄口战略"),
            ("02_AI工具与Agent落地", "模型能力边界、Agent 编排、RAG、提示词、成本控制"),
            ("03_算力与AI基建", "GPU 选型、显存测算、量化、部署与私有化"),
            ("04_IP与自媒体全栈", "平台机制、选题、内容复用、商单与知识付费"),
            ("05_出海与小而美", "跨境收款、选品、独立站、海外获客与合规"),
            ("06_资源与人脉协作", "社群设计、合作提案、分销、谈判筹码"),
            ("07_风险避坑", "股权、税务、合同、商标、开源协议、个人信息"),
            ("08_工作流与效率系统", "状态机、自动化、n8n、复盘机制、个人 CRM"),
        ],
    },
    "content": {
        "desc": "内容创作 / 自媒体",
        "cats": [
            ("01_平台机制", "各平台的分发逻辑、流量池、赛马与推荐规则"),
            ("02_选题与结构", "选题来源、标题、开头、叙事结构"),
            ("03_视觉与呈现", "封面、排版、镜头、剪辑节奏"),
            ("04_增长与分发", "冷启动、跨平台分发、搜索流量、私域承接"),
            ("05_变现与商单", "报价、广告、知识付费、会员与社群"),
            ("06_账号与合规", "封号风险、二创边界、肖像与音乐版权"),
        ],
    },
    "tech": {
        "desc": "技术 / 产品",
        "cats": [
            ("01_语言与工程基础", "语言特性、调试、测试、代码组织"),
            ("02_框架与架构", "框架选型、分层、边界与依赖管理"),
            ("03_数据与存储", "数据建模、索引、缓存、一致性"),
            ("04_部署与运维", "环境、CI/CD、日志、监控、回滚"),
            ("05_性能与优化", "瓶颈定位、压测、容量估算"),
            ("06_协作与交付", "需求拆解、评审、文档、交接"),
        ],
    },
}

REQUIRED_FIELDS = ["title", "category", "topic", "level", "words",
                   "updated", "tags", "copyright"]


# ---------------------------------------------------------------- 模板
T_TOTAL = """---
title: <<KB_NAME>> · 总目录
type: catalog
version: v1
updated: <<DATE>>
---

# <<KB_NAME>>

> 建库日期 <<DATE>> ｜ 分类 <<CAT_COUNT>> 个 ｜ 内容单元 0 个
>
> 这份总目录是唯一入口。所有分类索引、所有篇目都从这里可达。

## 一、怎么用这个库

三种读法，对应三种人：

| 你是谁 | 从哪进 | 怎么读 |
|---|---|---|
| 第一次来 | 下面第三节的分类地图 | 挑一个最疼的分类，读它索引里的「三篇先读」 |
| 带着问题来 | 全文搜索关键词 | 命中后看该篇的「避坑」与「动作清单」，正文可跳过 |
| 要把它用起来 | `_内容标准_去AI味与质检清单.md` | 按标准往库里补内容，别自由发挥 |

**不要按顺序通读。** 这个库是按「问题」组织的，不是按「课程」组织的。

## 二、目录结构

```
<<KB_NAME>>/
├── 00_总目录.md                      ← 你现在看的
├── _内容标准_去AI味与质检清单.md      ← 生产标准，补内容前必读
├── _交付说明.md                       ← 给开发/对接人看的字段映射
├── _验收单.md                         ← 交付时签字用
├── _篇目清单.csv                      ← 全库索引，Excel 直接开
├── _示例篇目.md                       ← 一篇合格样张
├── tools/
│   ├── check.py                       ← 全库体检（字段/双链/禁用词）
│   └── export.py                      ← 导出清单 + 打包
<<CAT_TREE>><<CARD_TREE>>```

## 三、分类地图

| 分类 | 覆盖什么 | 篇数 |
|---|---|---|
<<CAT_TABLE>>
点分类名进索引。每份索引里有「三篇先读」和「按目的导航」，不用从头翻。

## 四、命名与编号规范

| 对象 | 规则 | 例子 |
|---|---|---|
| 分类目录 | `NN_中文名`，两位数字，从 01 起 | `01_一人公司商业思维` |
| 篇目文件 | `NN-短名.md`，短名 ≤ 18 字，不带标点 | `07-一个人的三张表长什么样.md` |
| 编号 | 分类内连续，不复用、不跳号 | 删了 05，不把 06 改成 05 |
| 短名 vs 标题 | 文件名短、`title` 长（可带具体案例） | 短名做双链，标题做上架文案 |
| 索引文件 | 固定 `_分类索引.md` | 下划线开头，不进内容区 |

**为什么文件名要短：** 双链在 Obsidian 里显示的就是文件名，长了会撑破侧边栏。
**为什么编号不复用：** 编号是稳定 ID，复用会让旧链接指向新内容。

## 五、元数据（每篇都必须有）

```yaml
---
title: 完整标题，可带具体案例
category: 01_一人公司商业思维      # 必须与所在目录同名
topic: 定价
level: 深度篇 | 标准篇
words: 1900
updated: 2026-10-29
tags:
  - 定价
  - 现金流
copyright: 可直接入库 | 仅内部参考
companion: 速查卡-XXX              # 可选，有卡才写
---
```

八字段缺一不可。`tools/check.py` 会逐篇验证。

## 六、内容标准（摘要，全文见 _内容标准）

三条硬规矩，过不了就返修：

1. **开头必须是「事」，不是「理」。** 一个具体的人、时间、数字。不许用结论开场。
2. **每个判断必须挂证据。** 数字 / 时间点 / 当事人原话 / 一次带代价的失败 / 可当场演算的算式，五选一。挂不上就删。
3. **每篇要有一个「敢得罪人」的判断。** 四平八稳的内容不产生认知增量。

机器味黑名单（出现即改写）：本质是、核心在于、底层逻辑、赋能、抓手、形成闭环、要点一/二/三、随着 AI 的发展。

## 七、三种粒度

| 粒度 | 字数 | 用在哪 |
|---|---|---|
| 深度篇 | 1800–3000 | 主推内容，会员愿意花 5 分钟 |
| 标准篇 | 900–1500 | 库量主体，常规素材 |
| 速查卡 | 200–400 | 卡片流、社群日更、搜索命中 |

同一主题可以拆成「深度篇 + 速查卡」两个单元，卡不是摘要，是"只剩 30 秒该记住什么"。

## 八、质检与导出

```bash
python tools/check.py .          # 全库体检，有 P0 问题退出码非 0
python tools/check.py . --fix    # 能自动修的自动修（补字段默认值）
python tools/export.py .         # 生成 _篇目清单.csv 并打包 zip
```

体检覆盖：字段完整性、双链可解析、companion 空指向、禁用词、分类归属、索引覆盖、字数偏差。

**建议每次批量补完内容都跑一遍。** 人眼发现不了断链，脚本一秒就报。

## 九、进度看板

| 分类 | 目标篇数 | 已完成 | 配卡数 |
|---|---|---|---|
<<PROGRESS_TABLE>>
填了目标就按表推进，别凭感觉。

## 十、变更记录

- **v1（<<DATE>>）**：由 kb-factory 生成骨架，<<CAT_COUNT>> 个分类，0 篇内容。
"""

T_INDEX = """---
title: <<CAT_NAME>> · 分类索引
type: index
category: <<CAT_NAME>>
updated: <<DATE>>
---

# <<CAT_NAME>>

> <<CAT_DESC>>

## 篇目

| # | 标题 | 级别 | 一句话价值 |
|---|---|---|---|
| — | 待生产。按 `_内容标准_去AI味与质检清单.md` 写第一篇 | — | — |

## 三篇先读

生产满 3 篇后填这里。写法：一篇一行，`[[短名]]` 加一句"为什么先读它"。

- 待填
- 待填
- 待填

## 阅读导航（按目的）

| 你现在的问题 | 读这几篇 |
|---|---|
| 待填 | 待填 |

## 配套速查卡

待填。

## 一个总的判断

这个分类下最反常识、最想让人记住的那一句。填不出来，说明这个分类还没想清楚。
"""

T_STANDARD = """---
title: 内容标准 · 去AI味与质检清单
type: standard
version: v1
updated: <<DATE>>
---

# 内容标准：让人愿意读完，并且读完能动手

> 这不是审美偏好，是可验证的验收条件。写完自查，每条都要能回答"是/否"。

## 一、三条硬规矩

### 规矩一：开头必须是「事」，不是「理」

- ❌ 定价不是成本的加法，是价值的锚点。
- ✅ 2023 年 2 月，一个荷兰人上线了个给自拍生成写真的网站。第一周收入 5400 美元，五个月后单月 61800。他没投一分钱广告，网站是一个 PHP 单文件。

第一段只干一件事：让读者想知道"然后呢"。

### 规矩二：每个判断后面必须挂证据，挂不上就删

证据只有五种，任选其一：

- 一个数字（金额、时间、比例、次数）
- 一个时间点（某年某月发生了什么）
- 当事人的原话（转述也行，标注"大意"）
- 一次具体的失败，带代价
- 一个可以当场演算的算式

**没有证据的句子，一律视为水词。**

### 规矩三：每篇必须有一个「敢得罪人」的判断

不是"要重视定价"，而是"低价获客是给自己判了三年有期徒刑，因为你锁死了涨价的可能"。
有争议没关系，前提是有证据撑着。四平八稳的内容不产生认知增量，只产生阅读量。

## 二、机器味黑名单（出现即改写）

| 禁用 | 换成 |
|---|---|
| 本质是 / 核心在于 / 底层逻辑 | 直接说它是什么、怎么发生的 |
| 不仅…而且… / 既是…也是… | 拆成两句，只留一句 |
| 赋能 / 抓手 / 闭环 / 生态位 | 具体动作：谁在什么时候做了什么 |
| 要点一、要点二 | 用小标题写"事"，或者干脆不编号 |
| 首先/其次/最后 三段式排比 | 允许长短句混排，允许一句话成段 |
| "在当今时代""随着AI的发展" | 删掉，直接从具体时间地点开始 |
| 满屏表格 | 一篇最多 1 个表，只放可比数字 |

另外：**段落长度必须参差。** 连续三段都是四行，读起来就像 PPT。

## 三、三种粒度

| 粒度 | 字数 | 用途 | 要求 |
|---|---|---|---|
| 深度篇 | 1800–3000 | 主推内容 | 至少 2 个真实案例、1 个反常识判断、1 个失败样本、可执行动作清单 |
| 标准篇 | 900–1500 | 常规素材，占库量主体 | 至少 1 个真实案例、1 个反常识判断、3 条动作 |
| 速查卡 | 200–400 | 卡片流、社群日更 | 一个场景 + 三个判断 + 一句结论，不展开案例 |

## 四、深度篇骨架（不必逐条对齐）

```
1. 场景开场（100–200字）：一个具体的人、一个具体时间、一个具体数字
2. 案例前半段（300–500字）：他做了什么，发生了什么，别急着解释
3. 拆解（500–700字）：为什么会这样，机制是什么，这里才是干货
4. 反常识判断（150–250字）：和主流说法相反的那一句，敢下结论
5. 动作清单（400–600字）：3–5 步，每步带数字或判据，做到"今晚就能开始"
6. 失败样本（200–300字）：另一种做法的代价，最好带金额
7. 避坑（150–250字）：5 条以内，每条一句话，能直接对照
8. 金句卡（1–3 条，每条 ≤40 字）
9. 来源与版权
```

## 五、交稿前自检（三层追问，过不了就返修）

1. **为什么？** 读者会问"凭什么这么说"——文中有没有数字/时间/当事人？
2. **怎么做？** 读者会问"那我今晚干什么"——动作是否具体到"写哪句话、收多少钱、发在哪个平台"？
3. **没用怎么办？** 读者会问"我照做了但没效果"——有没有失败样本和判据？

三层都答得上，才算"服务"，否则只是"报告"。

## 六、合规红线

- 只取观点与框架，自己重写，不搬运原文段落；
- 每篇末尾：来源链接 + 版权标签（`可直接入库` / `仅内部参考`）；
- 第三方营收、用户数一律标注「自报 / 媒体二次整理 / 未经审计」；
- 不确定版权 → 直接标 `仅内部参考`，不进对外库；
- 涉及法律、税务、医疗的判断，篇首加"不构成专业意见"提示。

## 七、一篇写完，怎么判断合格

把作者名抹掉，如果这段文字放到任何一篇公众号里都不违和，它就是废的。
"""

T_DELIVERY = """---
title: 交付说明
type: manual
version: v1
updated: <<DATE>>
---

# 交付说明

这份文件是给**对接方**看的：开发、运营、编辑。他们不关心内容怎么写的，只关心怎么导入、字段怎么映射、合格标准是什么。

## 一、交付物清点

| 项目 | 数量 |
|---|---|
| 分类 | <<CAT_COUNT>> |
| 正文篇目 | 0 |
| 速查卡 | 0 |
| 合计内容单元 | **0** |
| 辅助文档 | 总目录 / 内容标准 / 本说明 / 验收单 / 示例篇目 |

## 二、导入方式

### Obsidian

1. 把整个文件夹放进 vault（或作为 vault 打开）。
2. 打开 `00_总目录.md`，所有 `[[双链]]` 可直接跳转。
3. 双链用的是文件名（短名），不是标题，改名会断链——改名请用 Obsidian 自带的重命名，它会自动更新引用。

### 通用 / APP 后台

按文件导入即可。切分逻辑通常按标题层级，本库每篇是"一级标题 + 若干二级标题"，切出来的块是完整语义单元。

若要切得更细，建议按二级标题切，块大小 256–512 token，重叠 10%–20%，块头带上分类路径（如 `01/定价/涨价`），这样检索命中后模型能知道上下文在哪。

## 三、字段映射

每篇头部是 YAML frontmatter，八个必填字段：

| 字段 | 类型 | 说明 | 建议映射 |
|---|---|---|---|
| `title` | string | 完整标题，可带案例 | 列表页标题 / 详情页 H1 |
| `category` | string | 与所在目录同名 | 一级分类筛选 |
| `topic` | string | 子主题，比 category 细一层 | 二级标签 |
| `level` | enum | `深度篇` / `标准篇` | 阅读时长、推荐位 |
| `words` | int | 中文字数 | 阅读时长 = words / 400 分钟 |
| `updated` | date | 最后修订 | 排序、过期提醒 |
| `tags` | list | 检索用 | 全文检索加权 |
| `copyright` | enum | `可直接入库` / `仅内部参考` | 权限过滤 |

速查卡另有 `type: 速查卡` 与可选 `parent`（指向母篇）。

**建议索引**：`category + level`（列表页）、`tags`（搜索）、`copyright`（权限）、`updated`（增量同步）。

## 四、质检结果

见 `tools/check.py` 输出。当前基线：

| 检查项 | 结果 |
|---|---|
| frontmatter 八字段 | 待补内容后复查 |
| 双链可解析 | 待补内容后复查 |
| companion 指向 | 待补内容后复查 |
| 禁用词 | 待补内容后复查 |

## 五、已知局限（提前说清，免得验收时扯皮）

1. **行业区间数据是经验归纳，不是统计结论。** 文中标注"经验归纳"的区间，来源是多位从业者的口述交叉，没有抽样框。
2. **平台规则与政策有保鲜期。** 涉及平台算法、税率、法规的篇目，`updated` 字段就是保质期起点，超过 12 个月应复核。
3. **不是所有篇目都配速查卡。** 卡是独立内容单元，不是每篇的必需品；缺卡不算缺陷。
4. **不构成法律、税务、投资意见。** 相关篇目只做"该问什么"的提示，不做结论。

## 六、验收标准

见 `_验收单.md`。五条打勾即可，不需要通读全库。
"""

T_ACCEPT = """---
title: 验收单
type: checklist
version: v1
updated: <<DATE>>
---

# 验收单 · <<KB_NAME>>

给对接人签字用。五条打勾即可，**不需要通读全库**。

## 一、清点

| 项目 | 应有 | 实有 | ✓ |
|---|---|---|---|
| 分类目录 | <<CAT_COUNT>> | | |
| 正文篇目 | | | |
| 速查卡 | | | |
| 总目录 / 内容标准 / 交付说明 / 验收单 | 4 | | |
| `_篇目清单.csv` 行数 = 正文 + 卡 | | | |

## 二、五条验收标准

- [ ] **1. 结构完整。** 打开总目录，每个分类都能点进去，索引里能看到篇目表。
- [ ] **2. 字段齐全。** 跑 `python tools/check.py .`，P0 问题为 0。
- [ ] **3. 链接可达。** 同一份体检报告里，断链为 0。
- [ ] **4. 清单可对账。** CSV 行数与实际文件数一致，版权列无空值。
- [ ] **5. 内容像人写的。** 随机抽 3 篇，只读开头两段，看是不是"具体的人 + 时间 + 数字"，还是"结论 + 道理"。

第 5 条是唯一需要人判断的，其余四条脚本给答案。

## 三、以下情况不算缺陷

- 部分篇目没有配套速查卡（卡是独立内容单元，不是必需品）
- 行业数据标注为"经验归纳"而非统计数字（已在正文标注）
- 平台规则类内容有保鲜期（`updated` 字段已标注修订日）
- 分类篇数不均衡（按主题真实厚度分配，不为了好看凑数）

## 四、三方各拿什么

| 角色 | 拿什么 | 干什么 |
|---|---|---|
| 内容负责人 | 全库 | 按 `_内容标准` 继续补产 |
| 开发 | `_交付说明.md` + `_篇目清单.csv` | 建表、导入、做检索 |
| 运营 | `_篇目清单.csv` + 速查卡目录 | 排期、日更、推荐位 |

## 五、签字

| 角色 | 姓名 | 日期 | 结论 |
|---|---|---|---|
| 内容 | | | 通过 / 返修 |
| 开发 | | | 通过 / 返修 |
| 运营 | | | 通过 / 返修 |

返修项写在下面，注明篇名与问题：

```
（待填）
```
"""

T_SAMPLE = """---
title: 为什么你的知识库第三周就死了
category: _示例
topic: 知识库建设
level: 标准篇
words: 950
updated: <<DATE>>
copyright: 可直接入库
tags:
  - 知识管理
  - 示例
---

# 为什么你的知识库第三周就死了

> 这是一篇**样张**，用来示范本库的写作标准。它本身不是正式篇目（`category` 是 `_示例`，不进任何分类），
> 补内容前先读它，比读十条规矩管用。

2024 年 3 月，一个做跨境电商的朋友给我看他自建的知识库。Notion 里 400 多个页面，标题规整，标签打得也全。我问他上周往里面加了几条，他说零。再问他上一次真的打开它是哪天，他翻了半天，说"好像是二月，找一份供应商报价"。

他的库建了七个月，前两周每天往里塞东西，第三周开始隔天，第五周停了。现在它是一个 400 页的墓碑。

## 死因不是"没时间"，是"只进不出"

绝大多数人建知识库的动线是：看到好东西 → 存进来 → 结束。

这条动线有个致命问题：**存的时候没有"取"的场景，取的时候找不到存的东西。** 两端不通，中间就是一个黑洞。

那位朋友的 400 个页面里，我抽查了 20 个，有 14 个他完全不记得存过。这不是记性问题，是分类方式的问题——他按"来源"分（公众号、播客、书），而他找东西时是按"我要解决什么问题"想的。**存的时候用一套逻辑，取的时候用另一套，必然对不上。**

## 改法：反过来，先定"取"再定"存"

具体三步，一步比一步具体：

**第一步，先写下你最近一个月真实问过的 10 个问题。** 不是"我想学什么"，是"我当时卡在哪"。比如"客户砍价到 60% 该不该接""发票开错了怎么红冲"。这 10 条就是你知识库的第一版目录，比任何分类法都准。

**第二步，按问题建文件夹，而不是按来源。** 一个文件夹对应一类问题，文件夹名就是那句问话的缩短版。存新东西时先问"它回答的是哪条问题"，答不上来就别存——这一条能砍掉你 80% 的收藏冲动。

**第三步，每周留 20 分钟做"取"的演练。** 随机抽 3 条问题，只用你的库去找答案，限时 2 分钟。找不到，说明那条路径断了，当场修。

## 一个反常识：写得越多，库死得越快

听上去违背直觉，但那位朋友的库就是这么死的——400 页里他能用的不到 30 页。**信息密度低到一定程度，检索成本会超过重建成本**，这时候人就不查了，直接去问人、去搜。

所以第一版知识库的目标不是"全"，是"每一页都能被一个问题叫出来"。宁可 30 篇篇篇有用，不要 400 篇等着被整理。

## 避坑三条

- 别一上来就设计标签体系。标签是长出来的，不是设计出来的，先用文件夹跑一个月，看哪些词反复出现。
- 别把"收藏"当"学会"。存进来只是登记，写一句"它回答了什么"才算入库。
- 别追求工具。Notion、Obsidian、飞书都能用，卡住你的从来不是工具。

## 金句卡

> 存的时候用一套逻辑，取的时候用另一套，必然对不上。
>
> 第一版知识库的目标不是"全"，是"每一页都能被一个问题叫出来"。

---

## 来源与版权

- 案例来源：作者 2024 年 3 月的真实访谈记录，人物信息已做匿名处理。
- 方法来源：作者在多个知识管理项目中的实践归纳，非学术结论。
- 本文原创撰写，无外部文本搬运。
- 版权标签：**可直接入库**
"""

T_CARD_SAMPLE = """---
title: 知识库自查三问
type: 速查卡
category: _示例
parent: 为什么你的知识库第三周就死了
updated: <<DATE>>
tags:
  - 知识管理
copyright: 可直接入库
---

# 知识库自查三问

**用的时候：** 觉得自己的库"建了但没用起来"。

**三问：**

1. 最近一个月，我真的从库里取到过东西吗？一次都没有，就是黑洞。
2. 我的文件夹是按"我要解决什么问题"分的，还是按"东西从哪来"分的？后者必死。
3. 随便抽一个问题，我能在 2 分钟内用库答上吗？答不上，路径断了。

**一句结论：** 库的价值不在装了多少，在能被多少个问题叫出来。

---

## 来源与版权

- 配套母篇：`为什么你的知识库第三周就死了`
- 版权标签：**可直接入库**
"""

T_README = """# <<KB_NAME>>

<<KB_DESC>>

一套按"问题"组织、可检索、可交付的知识库。骨架由 [kb-factory](https://github.com/<<GH_USER>>/kb-factory) 生成。

## 从哪开始

1. 打开 `00_总目录.md`——唯一入口，所有分类从这可达。
2. 想补内容，先读 `_内容标准_去AI味与质检清单.md`。
3. 想验证质量，跑 `python tools/check.py .`。

## 结构

```
00_总目录.md                  总入口
_内容标准_去AI味与质检清单.md   生产标准
_交付说明.md                  字段映射（给开发）
_验收单.md                    交付签字用
_篇目清单.csv                 全库索引
_示例篇目.md                  一篇合格样张
tools/check.py                全库体检
tools/export.py               导出清单 + 打包
<<CAT_COUNT>> 个分类目录 + 速查卡/
```

## 约定

- 正文文件名 `NN-短名.md`，编号分类内连续、不复用。
- 每篇头部八个 YAML 字段，缺一不可。
- 一篇最多一个表格。
- 每篇末尾标注来源与版权标签。

## 状态

建库日期 <<DATE>>，当前 <<ARTICLES>> 篇正文、<<CARDS>> 张速查卡。
"""

T_GITIGNORE = """# 系统
.DS_Store
Thumbs.db
desktop.ini

# 导出产物（按需保留）
*.zip

# Python
__pycache__/
*.pyc

# 编辑器
.vscode/
.idea/
"""

T_CSV_HEADER = ["类型", "分类", "序号", "简称", "标题", "级别",
                "字数", "主题", "标签", "版权", "配套卡", "路径"]


# ---------------------------------------------------------------- 生成逻辑
def parse_categories(spec):
    """01_市场:需求与竞争|02_产品:功能与定价 -> [(目录名, 描述)]"""
    cats = []
    for item in spec.split("|"):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            name, desc = item.split(":", 1)
        elif "：" in item:
            name, desc = item.split("：", 1)
        else:
            name, desc = item, "待补充定位"
        cats.append((name.strip(), desc.strip()))
    return cats


def cat_tree(cats, cards):
    lines = []
    for name, _ in cats:
        lines.append(f"├── {name}/\n│   └── _分类索引.md\n")
    if cards:
        lines.append("└── 速查卡/                            ← 独立内容单元，可单发\n")
    else:
        lines[-1] = lines[-1].replace("├──", "└──").replace("│   └──", "    └──")
    return "".join(lines)


def cat_table(cats):
    return "".join(
        f"| [[{name}/_分类索引\\|{name}]] | {desc} | — |\n"
        for name, desc in cats)


def progress_table(cats):
    return "".join(f"| {name} | — | 0 | 0 |\n" for name, _ in cats)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def init(target, name, desc, cats, cards=True, force=False, gh_user="you"):
    t0 = time.time()

    if target.exists() and any(target.iterdir()) and not force:
        print(f"[x] 目标目录非空: {target}")
        print("    换一个目录，或加 --force 覆盖（会保留已有文件，只补缺失的骨架）。")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    created = []

    # 1. 分类目录 + 索引
    for cname, cdesc in cats:
        p = write(target / cname / "_分类索引.md",
                  T_INDEX.replace("<<CAT_NAME>>", cname)
                         .replace("<<CAT_DESC>>", cdesc)
                         .replace("<<DATE>>", TODAY))
        created.append(p)

    # 2. 速查卡目录
    if cards:
        card_dir = target / "速查卡"
        card_dir.mkdir(exist_ok=True)
        p = write(card_dir / "_示例卡.md", T_CARD_SAMPLE.replace("<<DATE>>", TODAY))
        created.append(p)

    # 3. 根文件
    total = (T_TOTAL
             .replace("<<KB_NAME>>", name)
             .replace("<<DATE>>", TODAY)
             .replace("<<CAT_COUNT>>", str(len(cats)))
             .replace("<<CAT_TREE>>", cat_tree(cats, cards))
             .replace("<<CARD_TREE>>", "")
             .replace("<<CAT_TABLE>>", cat_table(cats))
             .replace("<<PROGRESS_TABLE>>", progress_table(cats)))
    created.append(write(target / "00_总目录.md", total))

    created.append(write(target / "_内容标准_去AI味与质检清单.md",
                         T_STANDARD.replace("<<DATE>>", TODAY)))
    created.append(write(target / "_交付说明.md",
                         T_DELIVERY.replace("<<DATE>>", TODAY)
                                   .replace("<<CAT_COUNT>>", str(len(cats)))))
    created.append(write(target / "_验收单.md",
                         T_ACCEPT.replace("<<DATE>>", TODAY)
                                 .replace("<<KB_NAME>>", name)
                                 .replace("<<CAT_COUNT>>", str(len(cats)))))
    created.append(write(target / "_示例篇目.md", T_SAMPLE.replace("<<DATE>>", TODAY)))
    created.append(write(target / "README.md",
                         T_README.replace("<<KB_NAME>>", name)
                                 .replace("<<KB_DESC>>", desc)
                                 .replace("<<DATE>>", TODAY)
                                 .replace("<<CAT_COUNT>>", str(len(cats)))
                                 .replace("<<ARTICLES>>", "0")
                                 .replace("<<CARDS>>", "0")
                                 .replace("<<GH_USER>>", gh_user)))
    created.append(write(target / ".gitignore", T_GITIGNORE))

    # 4. 空清单（只有表头，Excel 打开不报错）
    csv_path = target / "_篇目清单.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fp:
        csv.writer(fp).writerow(T_CSV_HEADER)
    created.append(csv_path)

    # 5. 库内工具
    tools = target / "tools"
    tools.mkdir(exist_ok=True)
    for src_name, dst_name in [("check_kb.py", "check.py"),
                               ("export_kb.py", "export.py")]:
        src = HERE / src_name
        if src.exists():
            shutil.copy2(src, tools / dst_name)
            created.append(tools / dst_name)

    cost = time.time() - t0
    print(f"\n[ok] {name}")
    print(f"     {target}")
    print(f"     分类 {len(cats)} 个 ｜ 文件 {len(created)} 个 ｜ 耗时 {cost:.2f}s")
    print()
    print("     下一步：")
    print("       1. 读 _内容标准_去AI味与质检清单.md（3 分钟，别跳）")
    print("       2. 读 _示例篇目.md，看一篇合格的长什么样")
    print("       3. 从最疼的那个分类写第一篇，写完跑 python tools/check.py .")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="3 秒拉起一套可交付的知识库骨架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例子:
  python init_kb.py ../我的知识库
  python init_kb.py out --name "开元OPC知识库" --preset opc
  python init_kb.py out --categories "01_市场:需求与竞争|02_产品:功能与定价"
""")
    ap.add_argument("target", help="目标目录")
    ap.add_argument("--name", help="库名，默认取目录名")
    ap.add_argument("--desc", default="", help="一句话定位")
    ap.add_argument("--preset", choices=list(PRESETS) + ["none"], default="opc",
                    help="分类预设，默认 opc")
    ap.add_argument("--categories", help='自定义分类，格式 "01_名:描述|02_名:描述"')
    ap.add_argument("--no-cards", action="store_true", help="不建速查卡层")
    ap.add_argument("--force", action="store_true", help="目录非空时也继续")
    ap.add_argument("--gh-user", default="you", help="GitHub 用户名，写进 README 链接")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    name = args.name or target.name
    desc = args.desc

    if args.categories:
        cats = parse_categories(args.categories)
    elif args.preset == "none":
        cats = []
    else:
        cats = PRESETS[args.preset]["cats"]
        desc = desc or f"围绕「{PRESETS[args.preset]['desc']}」整理的知识库"

    if not cats:
        print("[x] 没有分类。用 --preset 或 --categories 指定。")
        return 1

    return init(target, name, desc or f"{name} 的内容库", cats,
                cards=not args.no_cards, force=args.force,
                gh_user=args.gh_user)


if __name__ == "__main__":
    sys.exit(main())
