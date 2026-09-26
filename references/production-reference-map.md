# 制作技术索引：何时读取、输出到哪里

这里保留可直接指导制作的细节，不每次整库加载。先使用主Skill确定阶段与已有决定，再按当前问题读取对应文件。以下按实际制作问题组织方法，读取范围由当前任务决定。

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

## 使用边界

详细人体表演、外部静态几何生成和性能测量，只在相应需求成立时使用。四骨骼代理是一套可计算模板，不是所有角色的强制形态；实例工程仍需在实际版本执行、展示与检查。
