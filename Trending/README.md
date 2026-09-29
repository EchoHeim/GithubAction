# GitHub 热榜周报自动化

**每周六 06:00（北京时间）跑一次**：抓 GitHub 近一周热度最高的项目 → 拉 README →
DeepSeek 写成 1500~2000 字的公众号推文 → 以 **.md 源文件**发到飞书。

> **不落盘到仓库，而且发的是源文件。** 飞书是唯一出口，推送失败时脚本以退出码 1 结束、
> Actions 标红——这样"跑了但什么都没产出"不会被静默吞掉。
>
> 为什么发源文件而不是卡片：拿到的就是**原件**，标题、表格、代码块都是原生 Markdown，
> 直接丢进公众号排版工具即可。卡片里的 markdown 是被降级过的（标题压成加粗、表格拆成圆点），
> 拿去排版会丢格式——这正是要发文件的原因。

```
cron 周五 22:00 UTC（= 周六 06:00 北京）
  ↓
trending_article.py
  ├─[1] 抓 https://github.com/trending?since=weekly（失败自动回退 Search API）
  ├─[2] 从候选池里由模型自主选题（默认前 12 名），再取该仓库的元信息 + README
  ├─[3] 调 DeepSeek（默认 deepseek-flash，思考模式）消化资料，写成 1500~2000 字的推文
  ├─[4] 质检：格式清洗 → finish_reason 截断检查 → 正文字数兜底
  └─[5] 发飞书：应用机器人直接发 .md 源文件；没配应用则退回 webhook 卡片
```

## 时间与周期

| 项 | 值 |
|---|---|
| 触发 | `cron: "0 22 * * 5"` —— **周五 22:00 UTC = 周六 06:00 北京时间** |
| 榜单口径 | `since=weekly`，GitHub 官方"近一周涨星最多" |
| 统计区间 | 运行日往前推 7 天，如 `2026-09-22 ~ 2026-09-28（2026 年第 40 周）` |
| 产出 | 飞书里的一个 `.md` 源文件（形如 `2026-W40_项目名.md`）；仓库里不产生文件 |

> cron **一律按 UTC 计算**，改本地时区不会生效；GitHub 高峰期可能晚几分钟到十几分钟。
> 想改时段用 <https://crontab.guru/> 换算，注意 `0 22 * * 5` 里的 `5` = 周五（UTC）。

## 一次性配置

### 1. DeepSeek Key

<https://platform.deepseek.com> → API Keys → 创建，立即复制。

### 2. 飞书：两个通道选一个

| | 自建应用机器人（推荐） | 自定义机器人 webhook |
|---|---|---|
| 配置成本 | 稍高：建应用、开权限、发布、拿 chat_id | 低：复制一个 URL 就行 |
| 稳定性 | 高，不看关键词/白名单脸色 | 受签名、关键词、IP 白名单限制 |
| 能否私聊 | 能（open_id / email） | 只能发群 |
| **能否发源文件** | **能——这是本项目的主路径** | **不能**，webhook 只支持文本/卡片/图片，会降级成卡片 |

脚本**优先走自建应用**，三项凭证没配齐才回退到 webhook。

#### 方案 A：自建应用机器人（推荐）

1. **建应用**：<https://open.feishu.cn/app> → 创建企业自建应用，记下 App ID 与 App Secret。
2. **加机器人能力**：左侧「添加应用能力」→ 添加**机器人**。
3. **开权限**：左侧「权限管理」→ 搜索并开通：
   - `im:message`（获取与发送单聊、群组消息）**或** `im:message:send_as_bot`（以应用的身份发消息）
     —— 发消息必需，**二选一即可**
   - `im:resource`（获取与上传图片或文件资源）—— **发 .md 源文件必需**，
     少了它只能在群里发文本，文件传不上去
   - `im:chat:readonly`（获取群列表）—— 可选，开了才能用 `--ping` 自动列出 chat_id
4. **发布版本**：左侧「版本管理与发布」→ 创建版本 → 发布。
   **权限改动必须重新发布才生效**，这步最容易被漏掉。
5. **把机器人拉进目标群**：飞书客户端 → 目标群 → 右上角 `…` → 群机器人 → 添加机器人 → 搜应用名。
   （机器人不在群里、或没有发言权限，都会发送失败。）
6. **拿 chat_id**：配好后跑一次 `--ping`，它会把应用所在的群连同 chat_id 直接列出来。
   （**要在本地跑**——在 Actions 里 `FEISHU_RECEIVE_ID` 是 Secret，日志里的 chat_id 会被自动打码成 `***`。）

> 想发给自己而不是群：把 `FEISHU_RECEIVE_ID_TYPE` 设成 `open_id`，`FEISHU_RECEIVE_ID` 填你的 open_id，
> 并把应用的「可用范围」设成包含自己。
> `chat_id` 形如 `oc_xxx`，`open_id` 形如 `ou_xxx` —— 类型和 ID 必须对得上，否则报 230034。

#### 方案 B：自定义机器人 webhook（兜底）

群设置 → 群机器人 → 添加**自定义机器人** → 复制 Webhook 地址。
（建议开启"签名校验"，把密钥也存下来。）

### 3. 仓库 Secrets

Settings → Secrets and variables → Actions

| 类型 | 名称 | 说明 |
|------|------|------|
| Secret | `DEEPSEEK_API_KEY` | 必填 |
| Secret | `FEISHU_GITHUB_ACTION_APP_ID` | 方案 A 必填（App ID） |
| Secret | `FEISHU_GITHUB_ACTION_APP_SECRET` | 方案 A 必填（App Secret，**属于密码，别外泄**） |
| Secret | `FEISHU_RECEIVE_ID` | 方案 A 必填，目标会话 ID |
| Variable | `FEISHU_RECEIVE_ID_TYPE` | 可选，默认 `chat_id`；也可 `open_id` / `user_id` / `email` |
| Secret | `FEISHU_WEBHOOK_URL` | 方案 B 用；两个方案都不配则无处可推 |
| Secret | `FEISHU_SIGN_KEY` | 方案 B 的机器人开了签名校验时必填 |
| Variable | `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |
| Variable | `DEEPSEEK_MODEL` | 可选，一般**不用设**（默认已锁定 `deepseek-flash`） |
| Variable | `DEEPSEEK_THINKING` | 可选，默认 `1`（开启思考模式） |

> 旧名字 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 也认（新名优先），已经配过老名字的不用改。

### 4. 权限

不再回写仓库，工作流里 `permissions: contents: read` 就够（不需要 Read and write）。

## 交付前的三道质检

推出去之前要过三关，避免半成品上桌：

| 关 | 做什么 |
|---|---|
| **格式清洗** `scrub_markdown()` | 剥掉模型多包的整段代码块围栏；围栏奇数个时补全（否则后面内容全被吞进代码块）；标题前补空行；清行尾空格与连续空行 |
| **截断检查**（`finish_reason`） | 读到 `length` 说明输出撞上了 token 上限，自动追加一轮"接着写"，而不是把半截文章当真品 |
| **字数兜底** `check_article_length()` | 去掉注释和代码块后统计正文，明显低于 prompt 要求的 1500~2000 字就告警 |

> 为什么单拎出「截断检查」：思考模式下思维链与正文共享 `max_tokens` 预算，预算耗尽时
> 模型返回的是**半截正文 + `finish_reason=length`**，而 HTTP 依然是 200、`content` 也非空。
> 不查这个字段，断章就会被一路推到群里。上限已给到 `LLM_MAX_TOKENS = 12000`，
> 真撞上了会先告警、再追加一轮续写。

## 选题：不是无脑取榜首

榜单第 1 名经常是"很酷但用不上"的东西（新模型权重、某大厂内部工具开源）。
本项目默认让 **模型从候选池里挑** 一个更适合公众号读者的：

候选池默认取榜单前 12 名，把它们的名字、描述、语言、本周星数一起交给模型，
由模型按四条标准打分选出一个：

| 标准 | 说明 |
|---|---|
| **大众可用** | 最好是普通人/普通开发者能装能跑，不是需要 8 卡 A100 的东西 |
| **技术新颖** | 有可讲的技术点，不是又一轮 CRUD 模板 |
| **工具属性** | 偏向能解决具体问题的工具/应用，而非纯理论库、数据集、教程合集 |
| **能落地** | 读者看完当天就能上手用上，而不是"等它成熟再说" |

选题同样跑在思考模式下——这题本质是**横向比较 + 权衡**，正是思维链擅长的。
模型返回 JSON（`index` / `score` / `reason`），脚本会校验 `index` 是否越界。

**选题有 4 条降级路径**，任何一步出问题都不会让流水线断掉：

| 情况 | 行为 |
|---|---|
| 模型正常返回 | 用模型选的那个，日志里记下评分和理由 |
| 返回不是合法 JSON / index 越界 | 降级取榜首 |
| 候选池只有 1 个 | 直接用它，不浪费一次调用 |
| 手动传了 `--top N` | 跳过选题，强制取第 N 名 |

## 推文是怎么写的

不是"把 README 翻译一遍"，而是**两段式**：

**第一步，先把资料消化透**（在 prompt 里要求模型先想清楚再做，不写出来）：
- 它到底解决什么具体问题？（不是"是一个 XX 工具"，而是"过去你得 A，现在直接 B"）
- 谁最痛？什么场景下会想装它？
- 它凭什么能做到？（关键技术点或设计取舍）
- 读完的人下一步该干什么？

**第二步，写成人能读下去的推文**：标题有钩子、开头建立"这跟我有关"、
技术点翻译成人话（不罗列 feature 列表，而是说"有了它你能干什么"）。

可读性硬要求也写进 prompt 了：段落不超过 4 行、多用小标题、用"你"称呼读者、
一段最多一处加粗、**禁止"炸裂/吊打/颠覆/神器/史上最强"这类营销感叹体**——
推广靠把价值讲清楚，不靠形容词。

## 用的是哪个模型

**默认固定 `deepseek-flash` = DeepSeek-V4.1-Flash**，开启思考模式。

跑之前会 `GET https://api.deepseek.com/models` 核一下这个默认名**当前是否仍然有效**：

| 情况 | 行为 |
|---|---|
| 默认名在可用列表里 | 直接用 `deepseek-flash`（正常路径） |
| 默认名没了，但有其它 Flash 级 | 回退到 `deepseek-v4-flash`，并打日志 |
| 只剩 Pro 级 | **不自动升档**，保持默认名交给调用阶段报错（Pro 单价是 Flash 的 4.5 倍，不能悄悄换） |
| `/models` 探测失败 | 保持默认名，照常调用 |

检测到默认名失效会打印警告而不是静默切换，这样你能及时发现并在有空时更新脚本。

**为什么不写死 `deepseek-chat`**：那个老别名早已退场。DeepSeek 改过三次模型名
（`deepseek-chat` / `deepseek-reasoner` → `deepseek-v4-flash` → `deepseek-flash`），
写死任何字符串都会在某天静默失效。

### 思考模式：默认开启

**这个任务需要思维链，所以开着。** 三条理由：

1. **选题本身是推理任务** —— 要在 12 个项目里横向比较、权衡"热度"与"读者能不能用上"，
   这正是思维链擅长的；关掉之后选题质量明显下滑（倾向直接选 star 最多的）。
2. **"消化"比"摘要"难** —— prompt 要求先把技术点翻译成读者收益（"以前你得 A，现在直接 B"），
   再做取舍和编排。这已经不是简单抽取，需要推理。
3. **成本可忽略** —— 周六早 6 点是 DeepSeek 空闲时段（半价），单次约几分钱。

**代价要知道**：思考模式下 `temperature` 会被静默忽略（官方原话：设置参数不会报错，
但也不会生效），所以脚本在开启时**不传 `temperature`**，而不是传了假装有效。
另外思维链会占用 `max_tokens` 预算——这正是正文被截断的根源，所以上限给到了 12000。

| 变量 | 效果 |
|---|---|
| 不设 / `DEEPSEEK_THINKING=1`（默认） | 开启思考，`reasoning_effort=high`，不传 `temperature` |
| `DEEPSEEK_THINKING=0` | 关闭思考，`temperature=0.7` 生效，更快更省但质量下降 |

> 想省钱调试时可以临时设 `DEEPSEEK_THINKING=0`；正式出稿建议保持开启。

### 真实性的硬约束

推文内容**只允许来自抓到的资料**，prompt 里写了具体的禁止清单：

- 编造性能数据（提速多少倍、省多少内存）
- 编造背景故事（融资、团队来历、作者动机）
- 编造使用体验（"实测""亲测"——脚本没跑过该项目，一律不许写）
- 编造 API / 函数 / 命令行参数（README 里没有的接口名一个都不能出现）
- 编造对比结论（不断言比竞品好，除非资料里写了）

资料不够撑起某个小节时，允许**如实说明"README 未提供"并让该小节变短**，
而不是靠想象填满。描述亮点用"README 里写到"区分"项目自己的说法"和"验证过的结论"。

配套的两处工程保障：

- 仓库没填 description 时，prompt 里显式写"未填写，不要自行编造一句话简介"
- README 没抓到 / 被截断时，prompt 里显式说明"截断处之后不要推测"
- **兜底文章只直出原始字段**，不做润色补全；降级路径更要保证真实

### 计费参考（官方价，百万 token）

| | 输入（缓存未命中） | 输出 |
|---|---|---|
| flash 空闲时段 | 1 元 | 4 元 |
| flash 高峰时段 | 2 元 | 8 元 |

**高峰时段 = 工作日 9:00-12:00、14:00-18:00**，周末与法定节假日全天算空闲。
周六早 6 点跑正好是空闲时段，半价。开启思考模式下每次跑**两次调用**（选题 + 写作），
候选池越大选题那次输入越长——按 12 个候选估算，一次约几分到一角钱。

> `max_tokens=12000` 只是**上限**，按实际生成量计费；正常一篇 1500~2000 字用不到那么多。

## 配完先自检（强烈建议）

**一条命令同时验飞书和 DeepSeek**，不抓榜单、不调模型、几乎不花 token：

```bash
DEEPSEEK_API_KEY=sk-xxx \
FEISHU_GITHUB_ACTION_APP_ID=cli_xxx \
FEISHU_GITHUB_ACTION_APP_SECRET=xxx \
FEISHU_RECEIVE_ID=oc_xxx \
  python Trending/trending_article.py --ping
```

Actions 页面 → Run workflow → 勾 **ping** = true 同样可以。输出长这样：

```
=== 自检模式（不抓榜单、不调模型、只验通道）===
[ping] 飞书通道：自建应用机器人
[ping] 应用已在 2 个群里，chat_id 直接抄下面这列：
       oc_84983ff6516d731e5b5f68d4ea2e1da5  GithubAction 告警群
       oc_a1b2c3d4e5f60718293a4b5c6d7e8f90  摸鱼派技术交流
[ping] 发送连通性测试消息 ...
[ping] 飞书推送成功（应用机器人，报文 207 字节）
[ping] 目标会话里应该已经收到测试消息，可以正式跑了
[ping] DeepSeek 自检 base=https://api.deepseek.com
[ping] /models 返回 2 个：deepseek-flash, deepseek-v4-pro
      模型：deepseek-flash（默认，= DeepSeek-V4.1-Flash）
      思考模式：开启（effort=high）；注意 temperature 将被忽略，选题耗时与费用都会上升
[ping] DeepSeek 调用成功　模型=deepseek-flash　返回='收到'
=== 自检结果：飞书 OK　DeepSeek OK ===
```

**`chat_id` 不用去后台翻**——`--ping` 会把应用所在的群直接列出来，复制填进 `FEISHU_RECEIVE_ID` 即可。
（这依赖 `im:chat:readonly` 权限；没开也不影响发消息，只是列不出来。）

> ⚠️ 上面这段要在**本地终端**跑才能看到 chat_id 明文。在 GitHub Actions 里，
> 因为 `FEISHU_RECEIVE_ID` 存成 Secret，凡是出现在日志里的同值字符串都会被自动替换成 `***`，
> 你会看到 `***  信息推送` 这样的行——**这是正常的打码，不是脚本没取到值**。

两边都 OK 再跑正式流程，能省掉大部分"首跑才发现配错"的来回。

### 报错怎么读

**自建应用通道**（码值取自飞书《发送消息》与《上传文件》接口文档）：

| 错误码 | 原因 | 怎么办 |
|---|---|---|
| 230025 | 消息体超长 | 卡片上限 30KB、文本 150KB，调小 `FEISHU_MD_LIMIT` |
| 230027 | 缺权限 / 没开机器人能力 | 权限管理加 `im:message`（或 `im:message:send_as_bot`）和 `im:resource`；「添加应用能力」加机器人；**重新发布版本** |
| 230034 | `receive_id` 无效 | 核对 ID 与 `FEISHU_RECEIVE_ID_TYPE` 是否匹配（`oc_xxx` 对 `chat_id`，`ou_xxx` 对 `open_id`） |
| 230035 | 没有发言权限 | 群是否禁言、机器人是否被屏蔽 |
| 232009 | 群已解散 | 换一个 chat_id |
| 234001 | 上传：请求参数无效 | 检查 file_type / file_name |
| 234006 | 上传：文件超过 30MB | 单文件上限 30MB |
| 234007 | 上传：应用没启用机器人能力 | 「添加应用能力」→ 机器人，再重新发布版本 |
| 10003 / 10014 | 换取 `tenant_access_token` 失败 | App ID / App Secret 不对，或应用还没发布 |

**自定义机器人 webhook 通道**：

| 错误码 | 原因 | 怎么办 |
|---|---|---|
| 19001 | webhook 地址无效 | 检查 `FEISHU_WEBHOOK_URL`，`/open-apis/bot/v2/hook/` 这段不能少 |
| 19021 | 签名校验失败 | 机器人开了「签名校验」，把密钥存成 `FEISHU_SIGN_KEY`；也可能是服务器时间偏差 > 1 小时 |
| 19022 | IP 白名单校验失败 | **GitHub Actions 出口 IP 是动态的，白名单这条路走不通**，改用签名校验或自定义关键词 |
| 19024 | 自定义关键词未命中 | 关键词只匹配 text/title，建议写进推文标题 |
| 9499 | 报文格式错或超 20KB | 调小 `FEISHU_MD_LIMIT` |
| 11232 | 被限流 | 单机器人 100 次/分、5 次/秒，下次跑就好 |

**通用**：换取 `tenant_access_token` 失败会单独提示（App ID/Secret 错，或应用没发布）。
DeepSeek 失败时会区分：`401` Key 无效 / `402` 余额不足 / `400 + model` 模型名不对。

## 本地跑

```bash
# 只验证抓取/解析，并打印卡片预览，不调模型不推送（默认就是 weekly）
python Trending/trending_article.py --dry-run

# 完整跑（临时传 Key 即可，别写进文件）
DEEPSEEK_API_KEY=sk-xxx \
FEISHU_GITHUB_ACTION_APP_ID=cli_xxx \
FEISHU_GITHUB_ACTION_APP_SECRET=xxx \
FEISHU_RECEIVE_ID=oc_xxx \
  python Trending/trending_article.py

# 换成日榜、取第 3 名、不推送
python Trending/trending_article.py --since daily --top 3 --no-push

# 默认行为：从榜单前 12 名里由模型自主选题（--top 0 与不传等价）
python Trending/trending_article.py --candidates 20
```

> 脚本**只用 Python 标准库**（`urllib`），不需要 `pip install` 任何东西。

Actions 页面也支持手动触发（Run workflow），带 `ping` / `dry_run` / `top` / `candidates` / `since` 五个入参。

## 参数

| 参数 | 作用 |
|------|------|
| `--ping` | 自检飞书通道 + DeepSeek 模型/Key，不抓榜单；应用通道会顺带列出可用 chat_id |
| `--since weekly\|daily\|monthly` | 榜单周期，**默认 weekly** |
| `--top N` | 强制取榜单第 N 名；**`0`（默认）= 由模型自主选题** |
| `--candidates N` | 候选池大小，默认 12（仅自主选题时生效） |
| `--dry-run` | 跳过模型调用与推送，取榜首并用兜底模板，打印卡片预览 |
| `--no-push` | 正常生成但不推飞书 |

## 已知边界（都是实测踩到的）

- **不落盘到仓库，飞书推不出去就等于白跑。** 推送失败时脚本退出码为 1，Actions 会标红；
  想看效果又不打扰群里，用 `--dry-run` 在本地跑（它会打印源文件预览，不发任何网络请求）。
- **源文件只能走应用通道。** 自定义机器人 webhook 不支持 file 消息，只配了 webhook 时
  会自动降级成卡片，并在日志里说明；此时拿到的是降级版 markdown（标题被压成加粗）。
- **DeepSeek 的模型名会变。** `deepseek-chat` / `deepseek-reasoner` 已退场，
  现在在售的是 `deepseek-flash`（本项目默认）和 `deepseek-v4-pro`。脚本每次跑会核对
  默认名是否有效，失效会告警并回退到 Flash 级候选，**不会自动换成 4.5 倍价的 Pro**。
- **思考模式默认开启**，`temperature` 会被静默忽略（不报错、不生效），
  所以脚本在开启分支里干脆不传这个参数；同时思维链会挤占 `max_tokens`，
  这是正文被截断的根因，上限已提到 12000，并会检查 `finish_reason` 兜底续写。
- **真实性靠 prompt 约束，不是靠模型自觉**。约束写在 prompt 里（禁止编造性能数据、
  背景故事、使用体验、API 名、对比结论），另外对"没 description""README 缺失/截断"
  这两种常见情况做了显式提示。明确划了界线：**允许翻译和重组表达，不允许新增资料里不存在的信息**。
  但**仍建议首跑后人工扫一眼**，模型偶尔会在细节上越界。
- **飞书卡片 markdown 只认**加粗/斜体/删除线/链接/换行/代码块，**不认标题、表格、
  行内代码、图片**（这条只在 webhook 降级路径上才用得到）。`to_lark_md()` 已自动降级
  （`#` → 加粗、表格 → `·` 分隔文本、行内代码去反引号），正文超过 4500 字符会截断并提示。
- **周榜的星数文案是 `stars this week`，不是 `stars today`。** 只匹配 `stars today`
  会让每周跑出来的"本周涨星"全是 0。解析已同时兼容 today / this week / this month。
- **Trending 页面是抓 HTML 解析的**，GitHub 改结构就会失效。脚本做了
  「页面抓取（3 次重试）→ Search API 兜底」两级降级，但 Search API 的语义是
  "新建即高星"，不等于真实增速榜。描述字段的 class 是
  `col-9 color-fg-muted my-1 tmp-pr-4`，中间那个 `tmp-` 是动态加的，正则必须容错。
- **模型调用失败不会中断流程**，会降级成模板推文照常推送。
- **应用机器人的两条硬约束**：机器人必须在目标群里、且有发言权限；权限或能力改完
  **必须重新发布版本**才生效（很多人卡在这一步）。
- **已知限制**：周榜榜首偶尔是没写 description 的仓库，推文里该项会显示 `—`。
- 费用：公开仓库的 Actions 分钟数不计量，DeepSeek 按 token 计费（一周一次可忽略）。
