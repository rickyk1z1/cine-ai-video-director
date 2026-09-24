# 按需找动态参考

在工作台“找画面参考”入口写出当前要解决的视觉问题。任何制作阶段，只要创意仍含糊、用户反复表示画面不对或双方对动态效果理解不一致，助手应适时提醒并直接启动一轮参考查找，不再额外问一次是否要找。需求已经具体、双方理解一致时不机械插入这一环节。

## 查哪里，何时停止

仅使用 `assets/reference-sources.json` 的五站。Eyecandy 优先；动态图形／动画／VFX 可用 Stash，剪辑与运镜可补 Frame Set，风格与动画类型可补 Good Moves；Motion Design Awards 低频用于优秀整片比较。每次按需求选择补充站，不要求跑完五站。Flim 不纳入，自媒体平台不在默认来源范围。

助手调用已有搜索或浏览器，不写爬虫、不接入新搜索后端、不预下载建库。搜索结果也必须限制在五站来源页面；搜索引擎只负责找到这些页面，不能从不足三个结果自动扩展到全网。

- 请求先进入 `request`，真正开始检索时才 `begin` 并计时，软上限 240 秒。助手应主动注意预算；脚本限制新的检索意图，不会取消已运行的外部工具，也不能核实外部工具实际何时开始，不能声称精确到秒的强制超时。
- 找到三个**实际看过且真正贴近目标**的案例即停。线索、静态缩略图、标题相似和未播放成功的页面不能充数。少于三个甚至零个都可结束，说明找到的内容和限制即可。
- 超时或受阻后停止找新候选，可以整理已发现的线索、补看已打开的片段并记录已有观察。用户明确要求“换一组”并给出反馈时，才开启同一需求的新轮；翻页、刷新、重复读取工作台不重启计时或搜索。
- 会员受限时列出平台、受限能力、可能值得考虑的用途。不要购买、开试用、续费，不为登录排障拖延制作。用户当前授权与权限在本轮按实际情况处理，不把个人试用写成通用能力。

超时后，助手用显式 `record_existing=true` 收尾登记已经取得或正在处理的候选，不得借此发起新搜索。若没有准确观察时间，保留 `observed_at=null`，记录真实 `recorded_at` 与 `late_completion=true`；这说明结果延后入账、观察时间不确定，不证明预算内已完成。不得补造截止时刻。若有真实 `observed_at`，继续核验它不早于本轮开始、不晚于截止。收尾不重启预算，累计已有三个有效案例后仍停止。

## 怎样比较，怎样采用

每个参考记录标题、原站页面、实际看的片段或同页示例位置、为什么贴近、重要差异和可借鉴效果。工作台展示本轮内容与这些比较文字；直接打开原站可接受。只有实际观察得到的 HTTPS 图片／GIF／视频地址才可作为可选预览，地址不能代替原站来源；不猜 CDN 路径、不为内联显示专门下载媒体。

`observation=viewed` 表示助手实际观看动态过程后记账，`unverified` 表示尚未观看成功的线索。两者必须在展示上区分。`observation_note` 写实际看到了什么；有关摄影器材、制作软件、合成流程等推测，需明确写为推测，不能用网站标题或模型解释冒充直接观察。程序只能检查记录结构，不能证明助手真的看过，也不能代替相似度判断。

用户选中参考时，记录明确采用哪些特征，例如“前景遮挡后保持前进方向，进入新空间”，不要把“选中影片”解释为照搬原片。原文、人物身份、造型、场景、空间、动作、镜头目的和已有提示词约束继续有效；原片人物身份、构图和动作模板不随选择自动转移。助手只把采用特征改写为当前任务适用的视觉说明，再沿当前制作流程继续。

用户可以在原站自行观看后直接选择本轮匹配候选，无需助手补看或再次确认。此时 `selection_by=user`，助手尚未观看的候选仍保留 `observation=unverified`，不计入助手已观看的三个案例，也不声称助手验证过。选择即停止继续寻找；助手主动代选则必须有实际观看记录。

## 轻量记录 API

模块为 `scripts/reference_search.py`，数据放在 `doc.workspace.reference_sessions` 列表。函数不访问网络、不写文件、不修改输入；调用方在既有修订／锁机制中持久化新列表。`ValueError` 表示命令不能应用，调用方保留原数据并显示具体原因。

```python
sessions = reference_search.request(sessions, query, scope=None, now=None)
sessions = reference_search.apply(sessions, command, now=None)
derived = reference_search.view(sessions, now=None)
reference_search.validate(sessions)  # 合法返回 None，否则抛 ValueError
```

`now` 可省略使用实际系统时间，也可注入有限 Unix 秒、带时区 ISO 字符串或带时区 datetime。`scope` 为范围对象或文字，例如 `{"section_ids":["section-a"],"shot_ids":["s1"]}`。重复请求当前相同需求与范围是幂等的；不同需求在前一轮结束后可建立独立轮次，不能借改写需求绕过同一问题的预算。

`view` 返回 `sessions/current/sources/limit_seconds/max_matches/elapsed_seconds/remaining_seconds/valid_count/can_search/needs_search/limits`。没有轮次时 `current=null`。`current` 状态为 `request/searching/ready/exhausted`，含 query、scope、candidates、restrictions、chosen_candidate_id、adoption_note、feedback 等字段；`ready` 表示已找齐三例或用户已选择，`exhausted` 仍可展示和选择已有有效参考，不代表本轮没有价值。`view` 的超时状态是派生结果，不会暗中写回工作区。

| `command.action` | 字段及行为 |
|---|---|
| `request` | `query`、可选 `scope`；等同独立 request 函数。 |
| `begin` | 启动实际检索；重复 begin 不重置开始时间。 |
| `add_candidate` | `candidate`；仅检索中接收新结果。超时后只允许显式 `record_existing=true` 收尾登记已经取得或正在处理的结果；有实际 `observed_at` 则核验在本轮开始至停止／240秒截止之间，没有准确时间则保存 null、真实 recorded_at 与 late_completion=true，不伪造预算内观察证据。满三例后不再新增。 |
| `observe` | `candidate_id`、`observation_note`、可选 `matched`；只补看已登记的 unverified 线索，不新增来源或重启检索。满三例后不继续。 |
| `record_restriction` | `source_id`、`capability`、`reason`、`value`；只记录访问限制及可考虑价值，不产生任何账户操作。 |
| `stop` | 可选 `reason`；允许零结果、部分结果或未开始时结束。 |
| `choose` | `candidate_id`、`adoption_note`、可选 `selection_by=user|assistant`（默认 user）；用户可选本轮匹配候选，助手代选还须 viewed。保留实际观察状态，记录采用特征并停止检索。 |
| `reject` | 必需 `feedback`，可选修正后的 `query/scope`；保留旧轮和反馈，新建 request，不立即计时。仅用于用户明确换一组。 |

各操作可带 `session_id`，只允许修改最新轮次，旧页面命令应报轮次已变化。调用方仍应使用项目原有修订号保护并行修改。

候选必填 `title/source_url/match_reason/difference/reuse_note/observation`；`matched` 为布尔值，默认 true，只有它为 true 且 observation 为 viewed 才计入三个有效参考。可选 `watch_range` 为时间段或同页示例定位，`observation_note` 为实际观察；`preview_url` 必须 HTTPS，配 `preview_kind=image|gif|video`，没有媒体时类型为 `none`。候选 ID 由模块生成，预览媒体允许来自实际观察到的外部 CDN，来源页面仍须属于五站。相同页面相同片段不可重复入账，同页多个不同案例须用 watch_range 区分。

记账不代表视频已生成、资料已完整、分镜已采用或任何制作阶段已获授权。

实际落盘使用[工作台workspace接口](workbench.md#工作安排参考请求与时长校准)：`{"area":"references","command":{...}}`。页面入口与对话要求进入同一轮次；助手收到对话需求后可直接request、begin并检索，不把回到页面点击当作前置。

换组原因是可选补充；用户只说“这组都不合适”或点击换组按钮，也足以构成明确反馈，不再要求写一遍理由。下一轮读取上一轮候选与反馈，避开已否定的相同片段；用户主动要求回看旧例时按其要求处理。
