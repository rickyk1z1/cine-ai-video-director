# 详细方法如何接入当前生产

这些方法是生产步骤的具体实现说明，不是另一套影片工作流。只按[触发索引](tygg-reference-map.md)加载本次需要的分支；项目的当前分镜、既有范围决定、production记录和唯一制作Markdown继续为准。下载的TYGG文件夹不是运行依赖。

## 已选预演范围 → 工程规格 → 白模 → 投产

本工程入口只在用户已为当前批次选择“先白模预演再去 AI 视频平台生成”，或明确单独要求制作白模时使用；不能因分镜图完成或工程工具可用就自行进入白模。“继续”结合已展示的具体问题与既有决定理解；同范围已有选择就沿用，没有路线决定时沿[视频生产](video-production.md)说明直投与预演的区别及推荐。整段静态图序审查是本批一次的助手质量工作，不会授权 Blender；人工调整后不再重新进行语义评审。

1. 使用read读取工作台的当前section/shot ID、内容与时长，沿用适用的内容确认或范围内继续制作授权。图稿、视频阶段的局部改文字或补镜直接同步当前分镜，不要求重新确认整段文字。工程规格不能自行增删镜头或改台词；工程中发现需要改设计时更新同一工作台，再派生新工程版本。桥接可准备计划不代表用户选择了 Blender，执行仍受本批工具与范围决定约束。
2. 只实施当前段落内某一镜或连续镜头组时，在工程JSON设置`shot_ids:["实际镜头ID"]`，按原顺序连续选择；省略时沿用整个段落。只需为所选镜头声明机位与必要资产，不填造未实施对象。输出frame_range从1开始。默认`source_timebase:"section"`按当前段落累计量化，source_frame_range保留原段落整数帧位置；所选范围之前的时长须已知，之后的未知时长不阻挡制作。独立局部参考明确设置`source_timebase:"local"`，仅量化所选镜头，不依赖前面无关镜头的时长，也不写source_frame_range或声称原片时间位置；局部量化可能与整段量化相差一帧。非连续镜头分开建工程，两种模式均保留当前所选镜头顺序及真实时长。

确定实际fps、相机策略、主体与场景对象。把工程计划保存为项目内JSON：scene_id、fps、assets、cameras（键为原shot_id）、budgets、performance，按需加blocking、contact_hand_plan、events和asset_uses。机位id、lens_mm、focus_target必须有实际设计，focus_target须在assets声明；不是让用户填写这些内部参数。
3. 用桥接工具导出SceneSpec：

```text
python <skill>/scripts/previs_bridge.py prepare --directory <分镜目录> --section-id <当前段落ID> --engineering <工程计划.json> --project-root <项目根> --output <新版本scene-spec.json>
python <skill>/scripts/previs_bridge.py check --directory <分镜目录> --project-root <项目根> --spec <scene-spec.json>
```

桥接保留原shot ID和内容，秒按累计时间一次量化为整数帧，帧区间含首尾；0–5秒/24fps对应1–120帧。生成任务的秒区间仍为起点包含/终点不包含，不混用。相关时长未知、所选镜头既无确认也无范围授权、缺相机设计等明确拒绝，不伪造现成对象。

新`source_binding.scope_version=2`关联原文档、段落和当前所选范围指纹；指纹绑定原文/需求、相关段落及镜头组备注、当前镜头与时基，section时基另绑定影响原时间位置的前置镜头及其时长。check按统一范围授权解释验证当前可准备性、来源、镜头顺序、正文与时长映射，并调用SceneSpec离线校验。无scope_version的旧确认快照绑定仍可读，保持原section时基与真实确认来源；局部工程不因范围外文字改动而失效，相关改动则须派生新版本。source_revision记录派生时读到的版本，独立制作记录的写入不使工程失效。没有Blender对象查询的通过项只代表计划数据。`--output`不覆盖旧工程；技术细化不修改source_binding或分镜正文。

4. SceneSpec作为previs记录的 `files` 项（role=scene_spec），工程、实际白模视频、验证报告分别列files；`data`记录source_binding、实际frame/fps与版本、静态和动态采用。只填当前已发生的状态，不因生成SceneSpec就写已建模。风格、结构资产、尺寸依据作为depends_on记录；说明写body并自动汇入制作Markdown。
5. Blender执行前再次运行bridge check；通过真实工具读取版本、场景和对象，按详细资料写本次有限脚本执行，不把SceneSpec当已经内置的自动建模器。按静态查看后已同意继续的决定，或明确完整运镜制作授权实施动画，不因局部改稿重复确认文字；继续制作许可不冒充静态或动态采用。保存实际工程/导出视频并更新同一previs记录版本。所得视频和采用外观/音频进入当前package记录。
6. 投产入口能力、每镜图与对白要求仍由video-production和voice-assets控制。完成白模不等于满足采用录音及所选口型实现，也不等于可以跳过投产选择。

## 工程计划样式

先按镜头设计填写，不给所有镜头强制相同焦段。下面仅说明字段，不是可直接执行的生产计划：

```json
{
  "scene_id":"本段共用空间ID", "fps":24, "seed":0,
  "assets":[{"id":"角色或产品锚点ID","role":"subject"}],
  "cameras":{"原镜头稳定ID":{"id":"实际计划相机ID","lens_mm":50,"focus_target":"角色或产品锚点ID"}},
  "budgets":{"visible_triangles":500000,"expanded_visible_triangles":500000,"objects":500,"base_objects":500,"hardware_profile_id":"实际profile_id","calibration_status":"heuristic","instance_count_soft":5000,"texture_mb":512,"target_fps":24,"viewport_status":"unverified","render_resolution":[1280,720]},
  "performance":{"hardware_profile_id":"实际profile_id","stage":"production","measurement_method":"not_run","viewport_fps":null,"depsgraph_ms_p95":null,"warnings":["未进行实时测量"]}
}
```

预算示例取保守起点，不能当本机测量；实际参数以performance-budget详细解释与本次需要为准。序号、原文、焦点对象和工程路径不能照抄占位。JSON Schema用于字段结构，离线校验另管引用与时段，两者都不证明画面质量。

## 脚本执行表

| 脚本（相对Skill根） | 何时使用 | 输入与输出 | 本质边界 |
|---|---|---|---|
| scripts/previs/derive_proxy_dimensions.py | 选用圆柱球头模板后，新建或改角色尺度 | 身高、成人/儿童/自定义比例 → 参数JSON，放入previs.data或项目参数文件 | 不创建模型、不测姿态；手部附件另算 |
| scripts/previs/probe_hardware.py | 需要实际预演预算，已有档案不适用时 | 只读本机硬件；--output显式项目路径 | 不装依赖、不启动压力测试；统一内存/未知显存不当独显 |
| scripts/previs/validate_handoff.py | SceneSpec建模前或修改时 | 项目根+相对scene-spec/可选hardware-profile → 声明检查JSON | 非完整Schema；旧--package只兼容旧格式，当前投产不使用它 |
| scripts/previs/validate_previs_fast.py | 改路线/相机/碰撞代理后需局部检查 | scene中的previs_validation_request → result | Blender内执行；临时切帧后恢复，不渲染，不证明手部IK/全程碰撞/表演 |
| scripts/previs/inspect_performance.py | 实际负载变化、卡顿或用户要求 | Blender当前scene/view layer → result | 不改数据、不测FPS；不是局部增量检查器 |

后两项不是普通Python程序。在已授权的目标Blender中，将审阅后的脚本纯文本交给真实代码执行工具；取其`result`保存报告，不能编造MCP调用名。使用现有CLI后台副本时明确副本输入、输出和保存方式；不借验证打开用户未指定工程。生产中一次只做一个Blender重操作。

## 图像、场景和事件记录映射

- 母图与状态图：各为asset记录，实际图在files，image_id/角色ID/采用版本/locked_features/allowed_changes/actual_inputs放data，父图记录列depends_on。空白占位生成脚本未引入。
- 完整地点：同一项目内精确引用asset_id+version；固定布局、碰撞/导航/语义锚点和3D manifest为附件。本场相机/路径/动作属于previs，不写回共享母资产。
- 角色代理：H/W/D/L、参数来源、四骨骼模板版本以及接触手部计划放previs.data或SceneSpec附件；不是另一份角色外观定稿。
- 事件：记录发起者、目标、接触时刻、归属变化与结果，使用同一原shot_id。事件表和场次节奏细节写previs.data，关键人读解释放body；台词与镜头变动仍回工作台。
- 完整提示词：详例只提供写法；正式正文在package.data.prompt。多角色音频每条映射到录音、角色与时段，示例音色词不能取代已采用录音。
- 检查结果：按实际原始JSON保存，再附入previs.files；body说明检查范围、未验证项、需要用户看的内容，不能只填passed。

## 验证与可选范围

离线：`python -B -m unittest discover -s <skill>/scripts/previs -p test_offline_workflow.py`，另运行test_proxy_dimensions.py。普通Python不得用通配发现运行需要bpy的test_validate_previs_fast.py。

Blender隔离验证：`blender --background --factory-startup --python-exit-code 1 --python <skill>/scripts/previs/test_validate_previs_fast.py`。只用独立内存测试场景，不保存blend、不连接生产实例。通过只说明该版本下局部检查器可运行，不证明MCP连通或影片质量。

高级人体动画与Hyper3D不自动开启。Hyper3D需要明确本批对象、工具能力、质量与消耗选择；本次补充参考不授权安装、付费、生成3D资产或发布共享库。
