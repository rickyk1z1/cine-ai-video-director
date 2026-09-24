# 工作台与同一份制作数据

原生 HTML/CSS/JavaScript + Python 标准库本机服务。代码和模板只在 Skill，`storyboard.json`、图片及历史在任务目录。新任务建空数据，续做读取原目录；不为每次调用复制 HTML，不建立另一套项目历史。没有项目时采用用户给定输出目录，或本次任务的明确工作目录。

## 入口、启动与续接

```sh
python3 scripts/storyboard.py create --directory DIR --title 名称
python3 scripts/storyboard.py open --directory DIR
python3 scripts/storyboard.py current --directory DIR
python3 scripts/storyboard.py read --directory DIR --record-id ID
python3 scripts/storyboard.py read --directory DIR
python3 scripts/storyboard.py stop --directory DIR
```

`open` 复用属于这个目录且版本一致的服务；发现已登记旧版本时重启同一入口。服务把匹配的前端资源与后端一起加载，`/api/health` 给出运行与磁盘版本身份，不混用新界面和旧后端。`stop` 只关闭核实属于该目录的服务，数据保留。`serve --port PORT` 仍可用于前台运行和隔离验证。

现有旧版服务没有新登记文件时，用 `open` 建立当前入口并打开返回 URL；不能把旧端口还活着当成新版已运行。用户未保存草稿先保留，不能为了更新丢掉修改。新服务登记在任务目录 `.storyboard-server.json`，日志在 `过程记录/工作台服务.log`，不保存账户凭据。

续做默认用 `current`，已知段落可加 `--section-id ID`。它从同一制作数据派生当前文字、阶段、路线、图序、素材/决定/包索引及工作台请求，保留候选、需复核和未知状态；历史快照与记录的完整data不重复输出。跨段实际依赖也列入索引，已替代记录通常省略，仍被引用时以真实状态显示。概览中的记录标题与说明帮助定位，具体提示词、参考职责、平台节点或特殊决定字段用 `read --record-id ID` 按需取回，不能把概览当作完整生成输入。所有原数据仍可通过原有 `read` 读取。

`read --record-id ID` 返回当前修订、记录版本、状态和可编辑的完整 `record`，保留实际 `data/files/depends_on`，不复制记录历史。它适用于定位一个决定或读取现有包再修改；历史追溯仍使用完整读取。两种精简读取均不改项目数据或采用状态。

## 编辑、确认与整体操作

页面与 CLI 共用读写。稳定 `id` 负责引用，显示 `number` 和镜头排列独立。自动保存包含修订检查，未保存草稿留在本页浏览器；版本冲突时保留本地内容。页面携带读到的基稿，互不重叠的编辑可合并；同一字段或冲突结构不覆盖。普通 CLI `update` 仍严格检查 `--expected-revision`。

| 操作 | 用途 |
| --- | --- |
| `current [--section-id ID]` | 默认续做概览；当前内容、状态和相关记录索引，不复制历史与完整记录data。 |
| `read [--record-id ID]` | 按需取得一个记录的完整可编辑内容；不传ID时保持原完整读取。 |
| `update --input document.json --expected-revision N` | 更新文字稿，保留确认历史与制作记录；不冒充确认。 |
| `confirm --section-id ID --evidence 实际依据 --expected-revision N` | 记录用户确实确认的内容。对话确认可由助手记录，不让用户再点一次。 |
| `record --input record.json --expected-revision N` | 兼容单条记录接口；登记不等于调用生成、采用或新的授权。 |
| `transact --input change.json --expected-revision N` | 一次提交有关文字、确认与记录，失败不提交半套改动。 |
| `revise --input change.json --expected-revision N` | 图稿/视频阶段按用户反馈联动改文字、素材记录及新增镜头，保留当前阶段。 |
| `rehearse [--section-id ID]` | 导出实际采用图序、时长、接点和指纹，供本批一次整段预演审查。 |
| `prepare --input package.json --expected-revision N [--output NEW_DIR] [--compact]` | 首次准备完整包；校验、绑定、保存及导出沿同一接口。 |
| `prepare --record-id ID --input changes.json --expected-revision N [--compact]` | 更新现有包，只提交本次改动字段，仍执行全部原交接校验。 |
| `package --record-id ID [--output NEW_DIR]` | 读取已保存包的问题、提示和实际输入，或重试导出；不会生成媒体。 |
| `export` | 从当前数据导出阅读稿及历史，保护无法还原的人工改写。 |

`transact` 的最小输入为 `{document?:完整文字稿,records?:[记录],confirmations?:[{section_id,evidence}]}`。只提供本次需要的项，记录按实际依赖处理；用户决定、文件与采用依据不由工具编造。

`revise` 使用同一结构，再提供 `evidence`（本轮实际反馈）。默认从稿件与记录推导受影响段落；可提供 `section_ids`。增补新段落但仍属于同一作品时，`basis_section_ids` 指明承接的原制作范围。它自动登记本次修订与补镜范围，沿用明确的统一路线；混合路线的新镜头由助手更新具体分配，不重新要求整批选一次。它不伪造新文字确认或新图片采用，也不触发第二轮整段审查。

### 更新现有生成包

`prepare --record-id ID` 从指定的当前包继承未改字段，再处理 `changes.json`。对象递归合并，列表整体替换，`null` 是明确值；只能写原记录的可编辑字段，不能换ID或类型。修改正文必须同时提供针对新正文的 `data.prompt_review` 更新，至少使其 `prompt` 与新正文逐字一致；受影响的要求原句、参考职责和接点由助手实际复核更新，工具不编造通过。替换引用或改变范围时同步相关列表与依赖，接口不猜测应删除哪些创作依赖。

```json
{
  "data": {
    "prompt": "本轮实际完整正文",
    "prompt_review": {"prompt": "本轮实际完整正文", "requirements": []}
  }
}
```

这是字段形状示例；`requirements` 应为本轮真实保留及更新的条目，不能照抄空列表清除已定要求。未变的连续性说明、声音计划、参考及参数直接继承。入口保留原来的修订冲突检查、语义记录与实际输入一致性校验、文件检查、声音和镜头覆盖检查；任何错误均不保存修改。

常规 `prepare` 与 `package` 可加 `--compact`，返回同一检查结果、warnings、准确输入哈希、包版本及导出结果，仅省略重复的大段record和review_input。完整输入仍由本次文件、`read --record-id` 或原 `package` 取得；缩短回复不表示放宽校验。

## 工作安排、参考请求与时长校准

新接口复用同一JSON、修订检查和锁：

```sh
python3 scripts/storyboard.py workspace --directory DIR --input action.json --expected-revision N
```

HTTP等价入口为 `POST /api/workspace`，正文 `{command,expected_revision}`。操作数据位于 `doc.workspace`，普通文字 `update/transact` 不覆盖它，避免后台同步与前台编辑互相抹掉。没有这些数据的旧文档正常打开，默认单会话。

- 协作：`{"area":"coordination","command":{"op":"set_mode","mode":"coordinated"}}`。其他分工与回报操作见[项目协作](project-coordination.md)。界面选择模式或保存共用要求只是登记；助手读取后调用原生会话工具，按真实结果登记，不把按钮成功保存称为会话已启动。
- 创意参考：`{"area":"references","command":{"action":"request","query":"希望对齐的具体画面效果","scope":{"section_id":"实际段落ID"}}}`。真正联网前 `begin`，按[参考接口](creative-references.md)写回实际观察和候选；请求排队时间不消耗四分钟。显式换组会保留上一轮反馈，未回复不自动继续。
- 视觉定调：图鉴内“保存到当前工作台”保存 `workspace.style_choice` 的选择和 `project_notes`。这是本次用户选择依据；助手结合已有要求，将其落实到当前唯一 `kind:style` 约定，不把选择草稿当成另一份已采用风格文件。变化前的选择可回查，已有正式style和原始资料继续保留。
- 时长：`{"area":"pacing","plan":{"evidence":"本次校准依据","shots":[{"shot_id":"实际镜头ID","duration":4.5,"basis":"动作和运镜同步发生","changes":{"camera":"与动作同时靠近"}}]}}`。一次更新当前镜头与依据，派生建议/提示词及生成包按真实内容变化标为需同步，已提交任务历史不回写；不改变阶段与采用事实。

HTML只提供统一交互，联网搜索与会话创建由当前Codex会话执行，不嵌入API密钥、不另建调度器。用户从页面提交后显示真实的待处理状态；助手续做时直接处理已有请求，不重复询问。可以在对话中提出同样需求，助手记录并当轮执行，无需再点击页面按钮。

工作台选择的动态参考只保留当前候选、原站、观察与采用特征；可选HTTPS媒体能读到则预览，失败给原站入口。不猜媒体地址、不预下载整个库，静态封面不能证明动态效果。

## 制作记录

记录保留 `id,kind,title,body,section_ids,shot_ids,depends_on,files,data`。类型为 `style/asset/voice/grid/previs/package/task/result/decision`；ID稳定，版本与历史由工具维护。`files` 中每项为 `{path,role}`，程序计算真实字节哈希；不存在的未来文件不能登记成资产。

- `depends_on` 是实际内容依赖，不放入所有项目文件。跨任务引用具体素材或有明确版本的输入，不能把另一份不断变化的完整工作台当图片来源。
- `data.actual_inputs` 如实记录实际提交的路径、用途、当时状态和已知版本/哈希；没有证据保留未知，不从依赖或当前状态反推。
- `adoption_evidence` 只保存真实采用依据。`candidate/pending/revise/excluded` 不因同时有旧证据而成为已采用；明确 `supersedes` 排除旧选项，过期不等于弃用。
- 已选图旁存在另一个可选候选，不撤销已选方案。必需缺项由本次实际图序与制作需要判断，不能把“还有候选”当成整个镜头不可用。
- 新记录按实际影响绑定依赖。单改显示名称、顺序标签、图片无关的声音或时长，不应把同一图片判成重新生成；改变真实画面或实际输入时才标用途待核。旧版依赖继续可读，不伪造新的历史绑定。

首次图稿制作许可用 `decision_type: image_stage_entry`、`batch_id`、`selection_evidence` 和实际范围记录。路线用 `production_path`，详见[视频生产](video-production.md)。证据与范围是事实；程序不按“好”“继续”等孤立词句判断授权，助手须结合当前问题解释。内容版本变化不撤销同一范围许可。

## 同一工作台的制作视图

“项目与协作 / 视觉定调 / 创意参考 / 文字分镜 / 分镜所用资产 / 分镜预览”在同一工作台切换，保留编辑状态。视觉定调直接显示完整图库页面，随主页面滚动，不再使用iframe或固定高度的内嵌窗口；详情打开时只滚动详情、背景锁定，关闭恢复原位置。采用选择及本片补充保存回当前文档；已有工作台可直接读取旧数据，无需迁移或重开确认。原文 `source_text` 与需求说明分开；只有想法时不伪造原文。首稿用 `creative_direction` 决定的 `body` 写构建思路，`suggestions` 放确有价值的备选；当前方案已采用的理由不再变成一轮待批准建议。

镜头卡默认只展开内容与动作，约四行内滚动；其余字段独立折叠。段落与卡片层级、稳定镜号和排列编号清楚，保留轻量品牌样式与系统字体。

资产页分别展示实际用图、已采用资产与候选/待修改参考。预览按当前镜头顺序，每张状态图独立编号；同一文件作明确首尾状态可以分别定位。过期原图显示原因和历史采用状态，不因改稿变成空白，也不冒充当前可投产。

页面阶段由已有工作决定推导，不由“文字是否和旧快照相同”决定。已进入图稿/视频阶段，改稿、删镜与补镜仍在当前阶段；阶段可逆地编辑内容，已有进度与许可不重置。

## 整段预演、一次审查与活的生成建议

用户确认图稿后，助手按[整段图序预演](sequence-review.md)完成本批一次审查。工作台支持播放已采用静帧及手动逐张查看；同镜多张状态图暂分该镜时间，不增加总时长，缺时长时不伪造节奏。它不模拟真实运动、不代表声音效果，也不启动三维或付费任务。用户可以自由重看，重看不是再次走审查流程。

审查写 `decision_type: sequence_review`，以实际 `rehearse` 返回的 manifest绑定所看范围，记录真实 `summary`、`result: ready|revise` 和接点依据。两种 result 都表示本次整段审查已完成；有建议不表示流程回退。之后人工修改按 `revise` 落实并更新输入，不重新评审用户方案；原审查只对应其实际版本。

生成建议用一条 `generation_recommendation` 决定维护，同一ID随方案更新。设计初稿先给有用的初步建议；本批审查时汇总可执行方案；人工调整后只更新受影响的建议。旧建议若材料已经变化，页面提示需同步，而不撤销用户已选路线。

```json
{
  "decision_type":"generation_recommendation",
  "batch_id":"本作品稳定批次",
  "platform":"当前已选平台，未知时省略",
  "groups":[
    {"shot_ids":["SH01","SH02"],"input_mode":"多镜一次生成／首帧或其他真实建议","model":"已核实模型，未知时省略","reason":"控制目标及为何合组","inputs":"实际需要的人物、场景或运动依据","cost":"生成次数、秒数或核实的费用；未知明确写未知","limits":"实际风险和能力缺口"}
  ],
  "options":[
    {"path":"direct_platform","label":"直接去平台生成","recommended":true,"reason":"直接输入足以完成本段","tradeoff":"主要风险与成本"},
    {"path":"previs_reference","label":"先 Blender 预演，再平台生成","tool":"Blender","recommended":false,"reason":"预演可解决的具体空间问题","tradeoff":"增加准备工作，换取哪些可控性"}
  ]
}
```

示例是字段解释，不是可直接采用的真实建议。生成建议中的 `groups` 表示计划生成任务，按[生成分组方法](generation-strategy.md#从逐镜判断落到可制作的生成段落)关联真实镜头；文字分镜的镜头组与生成任务不强制一一对应，合并/拆分理由沿现有说明保存；平台模式由镜头控制目标决定，不默认全能参考。已选其他预演工具时按真实工具改 label/tool。建议与路线选择分开，`recommended` 不代表用户已选。

工作台在图序审查后集中展示结论、生成建议和两条路线，可记录用户选择；选择只写本地决定，不提交任务或消耗积分。用户在对话中明确选择同样沿用。项目工作方式也可以直接在对话回答，由助手通过 `workspace` 的 `set_mode` 同步同一数据并继续执行，不要求再点击页面。平台未定不伪填“待定平台”，后续按真实缺口处理。文字直投用 `review_basis: text_only`，不为界面制造图片或整段图稿审查。

## 阅读文档与文件组织

`分镜阅览.md` 展示当前镜头、采用素材、实际投喂正文和必要缺项。待确认/人工修订状态如实标注，历史确认和完整回执放同源 `制作记录.md`，不维护第二份正文。旧Markdown有无法从数据还原的人工内容时先保留并合并，不强行覆盖。

沿已有项目目录，将分镜与输入放在作品工作区，将平台候选和最终采用视频按[媒体目录](media-layout.md)统一归属。分镜根保留阅读入口和数据；图片素材按角色/场景/分镜图组织，活跃输入集中制作输入，预演、回执与暂存归过程记录。已明确弃用方案保留必要历史，不混入当前方案，也不以过期为由删除独有生成媒体。

`decision.data.supersedes` 明确替代旧记录；先承接仍有效的决定。文件搬迁核对实际消费者和引用，不能只为整齐移动工程。必要时 `过程记录/文件迁移.json` 保存 `{files:[{old_path,new_path,sha256}]}`；只有旧路径不存在、目标字节一致才解析为同一历史文件。

## 组图排版与画格提取

`python3 scripts/grid.py compose|extract --input spec.json --output NEW_DIR` 使用已安装 Pillow，原图不改。

- compose：`{columns:2,cell_size:[640,360],cells:[{shot_id,path},...]}`，等比缩放留白，不为凑格补镜。
- extract：`{path:实际组图,cells:[{shot_id,box:[左,上,右,下]},...]}`，按真实画格定位，不假定AI严格等分。
- `grid` 记录保存相同 cells映射；图片尺寸和画格合规不代替实际看图。

## 视频投产包示例

字段与准确复核由[出稿协议](prompt-delivery-check.md)维护，实际选择及上传规则由[视频生产](video-production.md)维护。包保存真实镜头、timeline、references、parameters、prompt与声音计划；已知逐镜内容时长须与当前工作台相符。平台固定档位或裁切余量用 `generation_handles:{head_seconds,tail_seconds,evidence}` 明示，必要时另给从0开始的 `content_timeline`；余量只能在首尾，不分摊拉长每镜。准确交接哈希同时绑定这些时间字段。以 `prepare` 自动继承指定路线的稳定批次、范围及必要依赖并绑定复核，不手工反复抄哈希。

未验证的动态接点随 `warnings` 返回，并进入导出manifest；`issues`为空只代表输入检查通过、可在已有授权内生成。正式输出为实际素材、完整提示词、参数映射及manifest，后续声音交接单列；不存在的素材不占位。任务及结果绑定真实包版本。外部旧视频可用 `result.data.source_type: external`、`source_evidence` 和真实视频文件登记，未知历史参数不伪造。

## 最小读写格式

正常制作先用本页的命令与最小输入格式；现有数据直接读取后局部改，不为每次更新重新查源码或手拼完整数据。接口说明不足或出现具体错误时，才定位 `scripts/storyboard.py new_document/new_shot/validate` 等相关实现。记录写入以本页为准；旧包可读取后修改受影响字段，新包按出稿协议准备，确有结构缺口时可参考隔离测试，但测试证据不能复制为生产证据。共用接口会维护版本、历史和派生视图，不能直接清除过期字段来放行。

创意参考属于按需辅助工具，不列入制作视图导航或阶段顺序。入口位于独立的“创作工具”区域；用户可从任何制作阶段打开，采用或返回都不改变当前制作阶段。

项目导航在所有页面统一放在顶部，采用原窄屏的横向布局；视觉定调同样保留顶部品牌、查找和镜头结构提示，不另隐藏导航或恢复左侧固定栏。

顶部结构提示按镜头组显示组数、各组镜头数量与组内数字顺序，只读且不跳转；数字是展示顺序，不改写正文镜号或稳定ID。
