# TYGG详细方法：何时加载、输出到哪里

这里保留可直接指导制作的细节，不每次整库加载。先使用主Skill确定阶段与已有决定，再按当前问题读取对应文件。原38份参考已逐项对照，5份重复流程由现有入口承接，其余保留完整技术细节或适配后的实用部分。文件数量不代表验证通过。

| 触发条件 | 按需读取 | 输出与消费者 |
|---|---|---|
| 风格/节奏或导演选择困难 | [directing-story-and-editing](production-detail/directing-story-and-editing.md)、[director-plan-example](production-detail/director-plan-example.md)、[production-document-templates](production-detail/production-document-templates.md) | style/decision记录及工作台镜头，不另写可编辑分镜正文 |
| 角色基础图、状态图或跨视角一致性 | [character-image-assets](production-detail/character-image-assets.md)、[reference-image-driven-assets](production-detail/reference-image-driven-assets.md) | asset记录、母图依赖、每镜图与提示词 |
| 用户选择Blender，开始建立空间 | [scene-blockout-and-camera-motion](production-detail/scene-blockout-and-camera-motion.md)、[scene-semantic-detail-library](production-detail/scene-semantic-detail-library.md)、[reality-to-design-quality](production-detail/reality-to-design-quality.md)、[research-evidence-and-reality](production-detail/research-evidence-and-reality.md) | 工程计划/SceneSpec → previs记录 → 静态审查 |
| 建筑外到内或复杂空间通行 | [commercial-architecture-blockout](production-detail/commercial-architecture-blockout.md) | 拓扑、可走区、门洞、碰撞代理与镜头位置 |
| 新建或改变简化人物 | [previs-visual-contract](production-detail/previs-visual-contract.md)、[character-proxy-standard](production-detail/character-proxy-standard.md) | derive_proxy_dimensions参数 → 同一角色rig与支撑设计 |
| 可见持物/递接/开门 | [contact-hand-ik](production-detail/contact-hand-ik.md)、[interaction-choreography](production-detail/interaction-choreography.md) | 接触手部计划、IK/锚点、事件、归属与局部验证 |
| 长镜头、走位或相机运动 | [blocking-and-camera-paths](production-detail/blocking-and-camera-paths.md)、[camera-and-action](production-detail/camera-and-action.md) | 空间曲线、时间映射、看向/焦点、切点和连续性 |
| 准备实际Blender调用 | [blender-mcp-setup](production-detail/blender-mcp-setup.md)、[blender-mcp-execution](production-detail/blender-mcp-execution.md)、[scene-contract](production-detail/scene-contract.md) | 真实实例/版本核对与previs_bridge生成/检查 |
| 布局/路线变更需局部校验 | [fast-validation](production-detail/fast-validation.md)、[offline-handoff-check](production-detail/offline-handoff-check.md) | 实际请求 → validate_previs_fast/validate_handoff结果文件 |
| 重复资产、规模或性能问题 | [performance-budget](production-detail/performance-budget.md)、[asset-library](production-detail/asset-library.md) | probe_hardware/inspect_performance与实际3D资产manifest |
| 白模视频导出与完整视频正文 | [reference-video-delivery](production-detail/reference-video-delivery.md)、[ai-video-and-asset-prompts](production-detail/ai-video-and-asset-prompts.md)、[reference-prompt-template](production-detail/reference-prompt-template.md) | previs文件及package完整正文/上传映射；对白沿当前音频要求 |
| 用户另行选择详细人体表演 | [animation-and-performance](production-detail/animation-and-performance.md) | 限定镜头的详细rig/动作计划，不作为普通白模前置 |
| 复杂静态几何可能值得外部生成 | [hyper3d-scene-assets](production-detail/hyper3d-scene-assets.md) | 只先比较对象价值；用户选择后再核实入口与费用 |
| 核对方法出处或版本范围 | [research-sources](production-detail/research-sources.md) | 来源依据，历史核验不变成本机当前实测 |

第一次使用工程附件或脚本时先读[接入说明](previs-integration.md)，其中定义原镜头ID、确认指纹、帧/秒换算、文件记录及实际命令。

## 三份结构合同与示例

- [scene-contract.schema.json](production-detail/scene-contract.schema.json)：结构/格式参考，不是新的分镜权威或已完成工程。
- [asset-manifest.schema.json](production-detail/asset-manifest.schema.json)：结构/格式参考，不是新的分镜权威或已完成工程。
- [hardware-profile.schema.json](production-detail/hardware-profile.schema.json)：结构/格式参考，不是新的分镜权威或已完成工程。
- [minimal-scene-spec.json](production-detail/minimal-scene-spec.json)：结构/格式参考，不是新的分镜权威或已完成工程。

## 逐份对照与取舍

| TYGG原文件 | 2.0对照结论 | 具体遗漏、增量价值与处理 |
|---|---|---|
| `ai-video-and-asset-prompts.md` | 需要适配 | 补齐角色映射、入画/画外连续性、动作和文戏提示词颗粒度及偏差归因。 |
| `animation-and-performance.md` | 值得保留为按需参考 | 完整人体、步态和动作重定向只在用户另行选择详细预演范围时加载。 |
| `asset-library.md` | 需要适配 | 补齐完整地点资产、局部变体、实例/rig复用与3D资产清单；不启动共享资产库发布业务。 |
| `asset-manifest.schema.json` | 需要适配 | 保留实际3D资产清单数据结构，与当前asset记录通过文件引用衔接。 |
| `blender-mcp-execution.md` | 需要适配 | 补齐真实工具发现、增量写入、幂等恢复、RNA/GN/Action版本分支、采样与缓存边界。 |
| `blender-mcp-setup.md` | 需要适配 | 保留安装/启用/加载/实例层次诊断；不在本轮安装、授权或切换实现。 |
| `blocking-and-camera-paths.md` | 需要适配 | 补齐空间/时间曲线、motion_owner、相机独立路线、视线/焦点分离和世界速度采样。 |
| `camera-and-action.md` | 需要适配 | 保留摄影选择、参照系、事件与连续性；不强套近战模板。 |
| `character-image-assets.md` | 需要适配 | 保留同角色多状态、母图依赖、代理映射与清晰构图；设定板版式作为选择而非强制。 |
| `character-proxy-standard.md` | 需要适配 | 2.0只说明少量弯曲控制，遗漏H/W/D/L计算、环线数量、连续权重和支撑补偿；保留整套可选四骨骼模板及离线计算器。 |
| `commercial-architecture-blockout.md` | 值得保留为按需参考 | 补齐外到内拓扑、净空、柱网与功能分区；按实际地点选择可见结构，不继承来源中特定场景。 |
| `contact-hand-ik.md` | 需要适配 | 2.0没有具体IK链、pole、腕/掌偏移及父子来源切换；保留比例、2骨IK、禁拉伸、世界变换与避免依赖环细节。 |
| `directing-story-and-editing.md` | 需要适配 | 补齐视点/信息差、beat作用、场次节奏层级、有效可读窗口与切点设计。 |
| `director-plan-example.md` | 值得保留为按需参考 | 保留完整长镜头节拍表与无人物例子，对白例子绑定外部录音。 |
| `fast-validation.md` | 需要适配 | 补齐可执行请求、采样上限、代理碰撞及不覆盖项；接入现有脚本，避免临时重写校验。 |
| `hardware-profile.schema.json` | 需要适配 | 保留硬件档案结构，预算和实测字段分离。 |
| `hyper3d-scene-assets.md` | 需要适配 | 保留复杂静态对象筛选、替换锚点与实例成本；去掉固定质量/材质/安装顺序，作为用户选用的可选分支。 |
| `interaction-choreography.md` | 需要适配 | 保留明确目标、持续状态、触发/作用/响应与结果占位。 |
| `interactive-development.md` | 已经充分吸收 | 整体方向再细调、继承已知信息在2.0已实现；不继承逐项三选和正文问卷禁令。 |
| `minimal-scene-spec.json` | 需要适配 | 保留可解析静态示例用于离线验证，生产工程由当前已获制作授权的分镜范围派生。 |
| `offline-handoff-check.md` | 需要适配 | 保留SceneSpec离线检查；旧generation-package仅作兼容测试，当前投产以storyboard package为准。 |
| `performance-budget.md` | 需要适配 | 补齐预算表、统一内存边界、实例展开、GN/LOD及测量含义；启发值不作为硬件实测。 |
| `previs-visual-contract.md` | 需要适配 | 保留代理表达/最终表演职责逐类对照及可见道具取舍，限定为已选中性模板。 |
| `production-approval-gates.md` | 已经充分吸收 | 2.0已有分镜/资产/静态/动态/投产/结果审查；不再建立另一套审批门。 |
| `production-document-templates.md` | 需要适配 | 把身份、摄影、节拍、交互和连续性表转为当前record正文模板，不新增Canon/PROJECT另一套状态。 |
| `project-documentation.md` | 已经充分吸收 | 当前项目入口、当前分镜及历史确认、范围决定与production记录已承接；不引入PROJECT+project-state的另一套权威。 |
| `reality-to-design-quality.md` | 值得保留为按需参考 | 保留功能到形态、可识别最低结构与资料判断。 |
| `reference-image-driven-assets.md` | 需要适配 | 保留母图/空间合同分工、输入DAG、跨视角和状态一致性、完整生图卡与建模转译；去掉占位与固定排版。 |
| `reference-prompt-template.md` | 值得保留为按需参考 | 保留完整双人交接、多主体动作、文戏及多人反应实例；对白改为已确认录音，不让模型重新配音。 |
| `reference-video-delivery.md` | 需要适配 | 补齐干净预演输出、有限帧段恢复、源帧/局部时间和媒体验证；统一接当前集中投产包。 |
| `research-evidence-and-reality.md` | 值得保留为按需参考 | 保留confirmed/inferred/artistic及研究层级，不加资料数量门槛。 |
| `research-sources.md` | 值得保留为按需参考 | 保留出处及作者当时的核验/未验证范围，不转述为本机当前实测。 |
| `revision-and-handoff.md` | 已经充分吸收 | 现有修订/快照/历史任务已实现；只补SceneSpec桥接与具体事件，不复制第二套生命周期。 |
| `scene-blockout-and-camera-motion.md` | 需要适配 | 保留结构层级、净空、轨迹和低成本识别几何。 |
| `scene-contract.md` | 需要适配 | 补齐SceneSpec/ShotSpec、事件、时间与场次接口；由当前授权范围导出，只作为工程派生物。 |
| `scene-contract.schema.json` | 需要适配 | 保留工程结构校验合同，并由当前分镜与范围授权桥接检查防止双真源。 |
| `scene-semantic-detail-library.md` | 值得保留为按需参考 | 补齐按场所功能/尺度/边界/操作/环境信号选择识别部件的候选库。 |
| `user-review-and-prompt-handoff.md` | 已经充分吸收 | 2.0已实现按采用版本交付、手动/自动、反馈后由用户选择重提。 |

## 明确不采用的部分

不引入空白占位PNG生成器；不继承固定人物板/道具三视图配额、全套逐题三选问卷、字符画标识、PROJECT与project-state第二套权威、默认Hyper3D参数与数量档、默认共享库发布，以及用户认可后反复追加全片检查。高级人体和Hyper3D仅按实际选择加载。来源中的影片剪辑、旁白重创或后期口型不进入当前素材生产范围。

已选用的四骨骼代理是一套可计算模板，不是所有角色的强制形态；任何实例工程仍需在实际版本执行、展示与审查。
