# 导演与动画来源索引

> 本地适配自TYGG AI Film Studio v3.2.7，详细技术参考，按[加载与输出映射](../tygg-reference-map.md)使用。现有主Skill的用户选择、确认节点、已采用声音及所选实现路径优先；不继承来源中的新增授权。版本/性能数字属于来源记录或启发式，执行时核对本机。


导演与动画资料访问日期：2026-09-08；视频参考提示词补充日期：2026-09-10。只将实际读取的公开正文/源码列为已读；网页中的影片、嵌入视频、付费课程和完整教材未观看/通读。以下是精炼的独立方法总结，不复制第三方Skill或教材。来源提供理论/实现依据，不能据此声称新场景已获电影级质量或实时验证。

## 教学与作者原始资料

| ID | 已读正文 | 用于本Skill的知识与边界 |
|---|---|---|
| D01 | Yale Film Analysis：[Cinematography](https://filmanalysis.yale.edu/cinematography/) | 构图选择、视点、跟随与重新构图、镜头运动的叙事作用；光学简化以B06及投影关系校正，不照搬固定焦段心理标签。 |
| D02 | Yale Film Analysis：[Editing](https://filmanalysis.yale.edu/editing/) | 连续性、动作匹配、延长镜头的意义；节奏涉及画内运动、声音与剪辑。文中具体镜头时长定义不作为硬阈值。 |
| D03 | Yale Film Analysis：[Mise-en-scene](https://filmanalysis.yale.edu/mise-en-scene/) | 深度调度、距离与关系、画外空间。阅读了文字分析，未另行观看其影片片段。 |
| D04 | Judith Weston：[Top 10 Ideas from Directing Actors](https://judithweston.com/web/archive/top-10-ideas-directing-actors) | 以动词、事实、意象、身体行动与事件帮助表演和剧本分析；不能把情绪词机械映射成统一姿势。属于作者公开文章，不是完整书籍。 |
| D05 | Judith Weston：[12 Tips for Directors](https://judithweston.com/web/extras/12-tips-directors) | 以视觉与调性揭示故事情绪核心，准备与开放性；具体Blender字段为本Skill设计。 |
| D06 | David Bordwell：[Creating suspense through film form](https://www.davidbordwell.net/blog/2006/09/26/film-form-and-the-viewers-experience/) | 观众既有信息影响好奇、悬念与惊讶，以及对节奏的感受；不能只凭镜头长度判断拖沓。 |
| D07 | David Bordwell：[Calm that camera!](https://www.davidbordwell.net/blog/2023/04/30/calm-that-camera/) | 与导演Ken Kwapis讨论机位/移动选择；静止、克制跟随、自由相机与长镜头都是选择，持续移动不自动产生叙事价值。 |
| D08 | ASC：[Shot Craft: Tools for Camera Movement](https://theasc.com/article/shot-craft-camera-movement/) | 将dolly、tracking、Steadicam、手持和升降机位按叙事意图区分；作为镜头运动动机与连续镜头多样性的依据。 |
| D09 | ASC：[Casino Royale: High Stakes For 007](https://theasc.com/article/casino-royale-high-stakes-007/) | 赌场牌局的前景/中景/背景层次、视线关系和多景别切换；用于桌游区的可拍视线通廊与人物关系镜头。 |
| D10 | ASC：[Beyond The Frame: Casino](https://theasc.com/article/beyond-the-frame-casino-1995/) | 赌场空间中的运动摄影、快速推进和环境节奏；用于判断移动是否服务于信息和情绪。 |
| D11 | ASC：[Ocean's Eleven: Smooth Operators](https://theasc.com/article/oceans-eleven-smooth-operators/) | 复杂空间中的镜头运动首先澄清人物与地点关系；用于建立镜和场面调度审核。 |
| A01 | AnimSchool，Angelo Sta Catalina：[The Key Poses of a Run Cycle](https://blog.animschool.edu/2024/04/10/the-key-poses-of-a-run-cycle/) | contact/down/push/peak，自然与夸张跑的差别、接触点与轮廓；非Disney官方统一跑步标准，未观看完整课。 |
| A02 | AnimSchool，Tyler Phillips：[Storytelling in Staging](https://blog.animschool.edu/2025/03/07/storytelling-in-staging/) | 简单姿势与机位先组织故事、thinking beats、快中慢对比；不把文章案例节拍数普遍化。 |
| P01 | OpenStax / Rice University：[6.3 Centripetal Force](https://openstax.org/books/college-physics-2e/pages/6-3-centripetal-force) | v²/r解释急弯成本；用于人物路径的合理性提示，不据此编造人体极限或自动求出合格步态。 |

## Blender 5.2 官方依据

| ID | 正文/源码 | 核实的实现边界 |
|---|---|---|
| B01 | [Follow Path](https://docs.blender.org/manual/en/5.2/animation/constraints/relationship/follow_path.html) | 路径时间/offset、owner偏移和约束组合，不能自动规划机位或避障。 |
| B02 | [Damped Track](https://docs.blender.org/manual/en/5.2/animation/constraints/tracking/damped_track.html) | pure swing旋转；没有时间滞后/弹簧阻尼选项。 |
| B03 | [Track To](https://docs.blender.org/manual/en/5.2/animation/constraints/tracking/track_to.html) | Track/Up轴及极点附近滚转风险。 |
| B04 | [F-Curve Properties](https://docs.blender.org/manual/en/5.2/editors/graph_editor/fcurves/properties.html) | 插值、速度连续性和自动手柄超调；缓入缓出不能机械套在每个路标。 |
| B05 | [NLA Sidebar](https://docs.blender.org/manual/en/5.2/editors/nla/sidebar.html) | Replace/Add/Combine、外推及Strip Time；轨道名称不隔离通道、不自动管理root motion。 |
| B06 | [Cameras](https://docs.blender.org/manual/en/5.2/render/cameras.html) | 焦距/传感器/FOV、机位与Dolly Zoom、Focus Object与焦点距离。 |
| B07 | [anim_path.cc，5.2 release分支](https://github.com/blender/blender/blob/blender-v5.2-release/source/blender/blenkernel/intern/anim_path.cc) | 本次源码按采样路径累计长度求位置，仅使用第一条spline；不是简单原始Bezier参数。分支可更新，结论限本次所读快照。 |

## MCP 安装与客户端连接

核对日期：2026-09-10。用于 [MCP 连接与安装选择](blender-mcp-setup.md)；安装时核对目标环境和当时的官方版本。

| ID | 官方依据 | 核实的实现边界 |
|---|---|---|
| M01 | [Blender Lab MCP](https://www.blender.org/lab/mcp-server/) 与 [官方仓库](https://projects.blender.org/lab/blender_mcp) | 插件、服务端和客户端分别就绪；`.mcpb` 依赖客户端支持。仓库 v1.0.0 的运行入口通过本地官方发行包 README、pyproject 与源码核对。 |
| M02 | [Codex MCP 配置](https://developers.openai.com/codex/mcp) | CLI 或配置文件登记本地服务；配置存在不代表当前会话已加载或已连上 Blender。 |

## 摄影与赌场案例补充

| ID | 已读正文 | 用于本Skill的知识与边界 |
|---|---|---|
| C01 | ASC Shot Craft: [Tools for Camera Movement](https://theasc.com/article/shot-craft-camera-movement/) | Dolly、轨道、升降、手持等运动应由叙事目的驱动；不把“运动越多越电影”当作规则。 |
| C02 | ASC: [Casino Royale](https://theasc.com/article/casino-royale-high-stakes-007/) | 赌场戏中的空间建立、视线组织、前中后景和运动选择案例；只提炼摄影方法，不复制具体镜头。 |
| C03 | ASC: [Beyond The Frame: Casino](https://theasc.com/article/beyond-the-frame-casino-1995/) | 通过镜头位置、遮挡和调度表达复杂公共空间；案例分析不构成固定镜头模板。 |
| C04 | ASC: [Ocean's Eleven](https://theasc.com/article/oceans-eleven-smooth-operators/) | 稳定器、轨道和多主体调度的组合案例；不据此硬性规定焦段或镜数。 |
| C05 | BFI: [Film Language](https://www.bfi.org.uk/education-research/education/teaching-film-language) | 景别、构图、剪辑和声音共同产生意义；镜头验收不能只看相机移动。 |

## 六个社区仓库：固定提交审读

R01–R06是创作者方法/工作流样本，其自称“大师法则”“成功率”“电影级”不构成权威证据。这里只提炼方法并注明改造，不导入它们的工具调用、提示词限制或审批流程。未运行远程代码、调用收费服务或复现其生成视频。

| ID | 仓库与所读核心文件（固定提交） | 采纳与改造 | 许可读取情况 |
|---|---|---|---|
| R01 | [Higgsfield generate](https://github.com/higgsfield-ai/skills/blob/fb18134b4aabe99c4bf7ff01c8f4883400efc80d/higgsfield-generate/SKILL.md)、[explainer](https://github.com/higgsfield-ai/skills/blob/fb18134b4aabe99c4bf7ff01c8f4883400efc80d/higgsfield-video-explainer/SKILL.md) | 素材职责、音画时间配对、分段交付；所读模块主要为生成服务编排，无Blender导演/步态求解实现。此判断不覆盖其全部产品。 | 根LICENSE MIT已读。 |
| R02 | [漫剧老李](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/aa20fb60054ae52553a4b13f8810ed2fcd89ba70/short-drama-director/SKILL.md)、[空间俯视](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/aa20fb60054ae52553a4b13f8810ed2fcd89ba70/short-drama-director/references/spatial-topview-camera.md)、[因果节拍](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/aa20fb60054ae52553a4b13f8810ed2fcd89ba70/short-drama-director/references/screenplay-gate-engine.md) | 目标/阻碍/选择、每镜任务、演员与机位地图、攻防状态；去掉固定12节拍、必反杀、静止/侧拍/慢镜禁令及无直接出处的大师冠名。 | short-drama-director/LICENSE MIT已读，范围限该目录。 |
| R03 | [MapleShaw Seedance](https://github.com/MapleShaw/seedance2.0-prompt-skill/blob/a2ab7fd9b73e1d531fabd7f59f390e8d39dc57a5/SKILL.md)、[camera-codec](https://github.com/MapleShaw/seedance2.0-prompt-skill/blob/a2ab7fd9b73e1d531fabd7f59f390e8d39dc57a5/references/camera-codec.md)、[storyboard-driven](https://github.com/MapleShaw/seedance2.0-prompt-skill/blob/a2ab7fd9b73e1d531fabd7f59f390e8d39dc57a5/references/storyboard-driven.md) | 分解相机描述、区分连续动作切片与切镜、保存失败边界；其Z/Y/X是提示词编码，不当世界坐标；不采用最多双轴、固定节奏公式或必裁首尾。 | 根LICENSE MIT已读。 |
| R04 | [songguoxs Seedance](https://github.com/songguoxs/seedance-prompt-skill/blob/57d1e2f273747c238dd892698a05137ab2f10d4a/.claude/skills/seedance/SKILL.md) | 时间片、参考素材职责、声画分离及段间状态；平台语法/时长限制留给输出适配，不承担三维路线设计。 | README声明MIT；TYGG作者当时未找到独立LICENSE正文。 |
| R05 | [jnMetaCode shortfilm](https://github.com/jnMetaCode/ai-shortfilm-prompts/blob/f21500e5946973949c6bbf02e67e0c21b2e63a35/skills/shortfilm-prompt/SKILL.md)、[NOTICE](https://github.com/jnMetaCode/ai-shortfilm-prompts/blob/f21500e5946973949c6bbf02e67e0c21b2e63a35/NOTICE) | 主体登记、镜头卡、画外信息、动作/情绪落点；纠正相同边缘进出的错误示例；不强制呼吸手持、无配乐、固定镜数/时长或瑕疵。 | MIT覆盖其原创；NOTICE区分保留权利的Mx-Shell原始提示词，未搬运提示词档案。 |
| R06 | [fight-video-create-skill](https://github.com/qualsenWeb/fight-video-create-skill/blob/28ab4b658fe41cbd54842f470fd879c38e9c9737/SKILL.md) | 当前明确专注战斗剧情/动作/空间/分镜；吸收路线先行、动作结果持续、镜头意图与压力交接；不照搬固定动作密度、动态结尾、遮挡自动越轴。 | README明确无独立许可证；只研究、链接与独立总结，不复制原文入本Skill。 |

## 视频生成与参考提示词

2026-09-10 实际读取以下正文。仅研究文字指导与厂商案例提示词，未运行生成或复现效果。通用方法保存在 [AI 视频与图片资产提示词](ai-video-and-asset-prompts.md)，不绑定某个项目或本机研究目录。

| ID | 官方来源 | 采纳与边界 |
|---|---|---|
| V01 | ByteDance Seed：[Introducing Seedance 2.5](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)，发布于2026-07-31 | 白模负责结构运动、图片负责指定外观属性的案例；当时公布单次最长30秒及时间戳控制。能力记录不转成固定片长，也不保证逐帧执行；复杂运动与多主体交互仍有局限。 |
| V02 | [Dreamina Seedance 2.5 User Guide：白模](https://bytedance.larkoffice.com/wiki/NjnWwvf4BiFYFLk2RzrcEgaunGf#VhDjdmAjyo1YoQxrp0dcb8wenbd)，页面显示8月17日修改 | 提炼参考声明、对象映射、剧情细节、场景处理和整体要求。粗白模以动态结构为用途，肢体细节要在文本中补清；不据此禁止所有肢体参考或要求已认可预演返工。 |
| V03 | Dreamina：[Motion Reference Guide](https://dreamina.capcut.com/seedance/seedance-2-5-motion-reference-guide) | 说明每个输入的用途及保留/变化属性；区分身份、运动、风格与声音。属于厂商指南，不是实测成功率或平台硬优先级。 |
| V04 | Dreamina：[Prompt Guide](https://dreamina.capcut.com/seedance/seedance-2-5-prompt) | 可观察行动、时间节拍、简明具体的约束；提示词长度取决于任务。示例的镜数、节拍和风格不通用化。 |

本次还回看 [HiAPIAI Blender Previs Engine](https://github.com/HiAPIAI/awesome-ai-video-workflows/tree/main/blender-previs/engine) 的原作者说明：视频、提示词和素材用途成套交接的方法可参考，但该文档仍面向 Seedance 2.0，不将其短片范围或审核流程复制成2.5规则。R03、R04同样不能作为当前2.5参数依据。

涉及具体平台/入口的时长、素材数、上传格式、引用语法和编辑功能时，复用适用的已核实资料；存在版本或时效疑问再查对应官方说明。普通提示词交付不重复整轮调研，不搬入案例的人数、道具、场景、对白或结局。

## 使用来源的方式

### 2026-09-10 · 2.9 流程修订补充

针对创作访谈、摄影色调、可见分镜、简化代理和参考提示词重新读取六个仓库的12份相关文档。下表记录吸收的方法与边界；是本Skill的独立综合，不是对社区效果数据的复现，也没有把外部Skill当成当前任务的执行指令。

| 来源 | 用于2.9的内容 | 不移植的部分 |
|---|---|---|
| [Higgsfield explainer](https://github.com/higgsfield-ai/skills/blob/main/higgsfield-video-explainer/SKILL.md) 与 [generate](https://github.com/higgsfield-ai/skills/blob/main/higgsfield-generate/SKILL.md) | 风格是明确的前期决定，生产参数有出处；区分普通生成、参考、编辑与延长 | 不引入其CLI、默认模型、固定块时长或自动提交任务 |
| [漫剧老李导演规则](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/main/short-drama-director/references/cinematic-dramaturgy-rules.md)、[视觉预设](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/main/short-drama-director/references/audiovisual-aesthetic-presets.md)、[输出组织](https://github.com/lixiaoxiao9888-create/manju-laoli-skill/blob/main/short-drama-director/references/seedance-render-engine.md) | 每镜说明任务；摄影、色光、材质、声音明确；全段共同要求与时段细节分开 | 不用固定12节拍、15秒、强制反杀/动结尾、通用微步进或额外AI复核 |
| [MapleShaw Skill](https://github.com/MapleShaw/seedance2.0-prompt-skill/blob/main/SKILL.md) 与 [剪辑节奏](https://github.com/MapleShaw/seedance2.0-prompt-skill/blob/main/references/editing-rhythm.md) | 将景别、构图、运镜、色光明确表达；区分时间段与切镜，考虑段间色光连续 | 不硬套2.0参数、固定镜数、统一首尾裁切、CG品牌词或预设大量抽卡 |
| [songguoxs Skill](https://github.com/songguoxs/seedance-prompt-skill/blob/master/.claude/skills/seedance/SKILL.md) | @引用逐项表述用途；不同任务的参考范围分开；段间状态明确 | 2.0的数量/时长不当2.5限制；计划标签不冒充实际绑定 |
| [jnMetaCode Skill](https://github.com/jnMetaCode/ai-shortfilm-prompts/blob/main/skills/shortfilm-prompt/SKILL.md) 与 [项目规划表](https://github.com/jnMetaCode/ai-shortfilm-prompts/blob/main/templates/project-planner.zh.md) | 主体登记与稳定名称、视觉设定、镜头级动作和声音的独立说明 | 不强制所有影片手持、无配乐、器材品牌或瑕疵；不沿用机械同边出入画例子 |
| [fight-video-create-skill](https://github.com/qualsenWeb/fight-video-create-skill/blob/main/SKILL.md) | 动作设计保留目的、触发、响应、接触/落空、结果与下一步条件，转译为可审分镜 | 仅吸收书面设计方法，不把完整武打链做进圆柱代理，不复制其原文或专用资料库 |

以下记录上游2.9的吸收历史，不是当前强制访谈或阶段门禁；当前范围、已有决定与3.0主规则优先。对应方法入口为 [风格选择](../style-development.md)、[文档模板](production-document-templates.md)、[阶段确认](../workbench.md)、[代理合同](previs-visual-contract.md) 与 [参考提示词模板](reference-prompt-template.md)。图片/视频/文本的属性分工仍以V01–V04的参考用法为依据；上表的文本经验不能证明平台会逐帧遵从。

### 2026-09-10 · 3.1 三选项访谈与局部手部

此项记录上游历史中的三选项访谈与局部手部要求，不把固定选项数或逐项提问转为当前用户要求。当前风格讨论按 [风格选择](../style-development.md) 只补实质缺口；驾驶/持物等镜头的简化手部方法见 [接触手部规范](contact-hand-ik.md)，激烈动作仍省略复杂手部表演。这是交互和制作方法的来源记录，不是经过Seedance对照实验的性能结论。

本次取得 [Blender 5.2 KinematicConstraint API](https://docs.blender.org/api/5.2/bpy.types.KinematicConstraint.html) 和 [Blender 5.0 IK说明](https://docs.blender.org/manual/id/5.0/animation/constraints/tracking/ik_solver.html) 的搜索返回正文，用于核对链长、极向目标及拉伸语义。5.2英文手册直连读取失败，未据此声称已读取该页或实测新rig；执行时按实际Blender RNA能力确认。手臂比例、接触附件和镜头切换策略为本Skill工程约定。

### 2026-09-10 · 3.0 使用反馈与工程默认

3.0根据明确的Skill改版要求，把剧本/分镜同轮展示、人物设定板左1/3头部与右2/3正侧背、连续剧情进度恢复、默认圆柱弯曲骨骼和圆滑摄影机转弯写入流程。角色比例及4骨骼配置是可调整的预演工程默认，见 [尺寸与弯曲标准](character-proxy-standard.md)，不是医学比例或Seedance效果的实验结论。它们不改变此前资料的版本适用边界，不保证视频模型逐帧遵从，也不触发旧项目返工。

- 保存 reference_id、purpose（剧情/构图/动作/运镜/声音/外观）、适用范围、来源版本和读取范围。参考一个片段的摄影机运动，不自动继承其中人物、服装、对白或事件。
- 教学正文解释原理，官方文档解释软件行为，社区Skill提供组织方式。本Skill的路线公式、时间字段、碰撞采样和审片步骤属于工程/创作综合，明确为设计方法或启发式，不冒充出处原话。
- 未获取正文的网页、只看书目介绍的书籍及未观看影片不写成“已学习完整知识库”。未独立复现实验的社区成功率不引用为效果保证。
- 知识库更新后通过实际输入检验导演决策；至少保留方案、关键假设、实际实现、审片问题和改动。问题反馈限定到案例/风格/版本，不随意升级成全局禁令。

## 多主体动作与参考责任的补充依据（2026-09-12核对）

- ByteDance Seed，2026-07-31，[Seedance 2.5官方介绍](https://seed.bytedance.com/en/blog/one-take-creation-flexible-referencing-introducing-seedance-2-5)：白模参考可传递姿态、路线和机位；官方也列出复杂动作物理合理性及多人交互稳定性仍有提升空间。这不证明某次生成失败的唯一原因，也不适用于未经核实的其他模型。
- Chris Hurtt / Animation Mentor，2017-06-07，[Anticipation](https://www.animationmentor.com/blog/anticipation-the-12-basic-principles-of-animation/)：准备动作的时长、速度与幅度应配合后续动作；避免命中前无意开始受力响应。
- Shawn Kelly / Animation Mentor，2006-10，[Contrast in Timing](https://newsletters.animationmentor.com/newsletter/1006/feature_geek.html)：等间隔动作容易机械，时间对比帮助表现动机和力度。

可见道具省略、目标响应隔离和参与者状态表属于本Skill的制作方法，基于上述原理与项目复盘推导；不声称是厂商保证的控制协议。

## 粗预演参考、自然表演与实测反馈（3.2.3）

本节吸收2026-09-12此前已完成的参考提示词调研及随后用户的生成反馈；规则更新未另做生成实验。执行入口是 [自然表演与人物连续性](ai-video-and-asset-prompts.md#大体时间与自然表演) 和 [提示词模板](reference-prompt-template.md)，使用本Skill不依赖原项目目录或完整调研缓存。

| 依据 | 采用的方法与证据范围 |
|---|---|
| [Dreamina / ByteDance Seedance 2.5 User Guide](https://bytedance.larkoffice.com/wiki/NjnWwvf4BiFYFLk2RzrcEgaunGf) | 此前读取粗白模与30秒等相关章节：结构参考职责、可辨认代理与真人对应、局部表演补足、按时间或逻辑组织剧情。不是逐帧控制保证，不推出所有时间信息都应删除。 |
| [Dreamina Motion Reference Guide](https://dreamina.capcut.com/seedance/seedance-2-5-motion-reference-guide) 与 [Prompt Guide](https://dreamina.capcut.com/seedance/seedance-2-5-prompt) | 素材职责与局部修订、必要而具体的约束；通用用法结合本任务取舍，不把其模板当所有参考任务的固定长度或动作密度。 |
| [GrandVisionsAI 的简化与详细预演对照说明](https://x.com/GrandVisionsAI/status/2096993565599490465)及[公开提示词回复](https://x.com/GrandVisionsAI/status/2096993966549880939) | 原作者报告支持区分整体路线与局部自然交互；属于创作者自报，未独立复现，不推出代理越简单必然越好。 |
| [Emily2040 reference workflow](https://github.com/Emily2040/seedance-2.0/blob/main/references/reference-workflow.md)与[performance example cards](https://github.com/Emily2040/seedance-2.0/blob/main/references/performance-example-cards.md) | 2.0资料中的职责组织和表演写法可供比较；表演卡自述未生成，不作为2.5性能或文戏效果的实测证据。 |
| 用户实测反馈与采用要求 | 用户报告“大体时间分段、段内自然动作”的版本整体和动作自然度改善，并明确保留顶部结构；随后报告入画、服装和融合歧义。反馈支持保留该稿作为项目修订基准，不能量化成功率或证明某一句话的唯一因果。 |

文戏的目的、倾听、潜台词、情绪延续及符合景别的少量表演线索，是上述表演建议与本索引D04–D05等导演原理的任务化综合。新增打戏和文戏示例均为独立编写、尚未生成验证；它们演示信息选择，不构成通用效果咒语。人体自然度、空间/摄影、身份连续性与交互结果分别记录，单次成功不升级为模型性能定律。

## 文戏的细微表情、对白与情绪推进（3.2.4）

2026-09-12针对结构预演下的文戏重新阅读官方表演示例，并结合已完成的专题调研和用户对两类文字案例的意见修订。执行入口为 [文戏规则](ai-video-and-asset-prompts.md#文戏关系倾听与情绪延续) 与 [文戏模板示例](reference-prompt-template.md#文戏动作段示例试探与迟疑)；发布包不依赖本机报告或项目素材。

| 已读依据 | 采用的方法与边界 |
|---|---|
| [ByteDance 官方手册的长视频文戏示例](https://bytedance.larkoffice.com/wiki/NjnWwvf4BiFYFLk2RzrcEgaunGf#Kepid00aXojXyAxGSmKcaOv0nzc)及[声音参考章节](https://bytedance.larkoffice.com/wiki/NjnWwvf4BiFYFLk2RzrcEgaunGf#Gvstd4xHuoF0yFxQTSHcx2esnGf) | 已读阶段中的具体表情、声音变化与情绪解释支持把意图落实为可读表演；声音素材另行声明对象和范围。其近景、精细时间和表情组合属于示例，不据此要求每段逐部位编排，也未独立复核示例成片效果。 |
| [Dreamina Prompt Guide](https://dreamina.capcut.com/seedance/seedance-2-5-prompt)与[Motion Reference Guide](https://dreamina.capcut.com/seedance/seedance-2-5-motion-reference-guide) | 可观察指令、视线与参考职责支持按信息缺口补足表演；不推导“越短越自然”或“细节越多越好”。 |
| [FlyAIgh 表演指令审计](https://www.flyaigh.com/blog/guide-ai-video-acting-directions) | 已读作者公开提示词、方法与结果表：两次输出为纯文字输入，时长分别5秒与8秒，未独立逐帧复核。可用于理解模糊表情可能被近似处理，不能当同条件实验或证明删除情绪词有效。 |
| [Higgsfield 提示词指南](https://higgsfield.ai/blog/seedance-2-5-prompting-guide)与[Pray 真人视频参考教程](https://www.prayproductionstudio.com/tutorials/seedance-video-references) | 前者的细节密集多镜头案例和后者的真人对白参考具有不同输入条件。阅读文字与教程转录后区分其适用范围，不要求粗预演继承不存在的表情或声音。 |
| [Emily2040 表演示例卡](https://github.com/Emily2040/seedance-2.0/blob/main/references/performance-example-cards.md)与[参考工作流](https://github.com/Emily2040/seedance-2.0/blob/main/references/reference-workflow.md) | 参考职责、按预期语气预读台词、分别检查说话内容与口型可借鉴；卡片明确尚未生成，2.0背景不作为2.5能力证明。 |
| 用户对文戏提示词的书面审阅与更新授权 | 用户要求在关键转折补足细微表情，查看安静挽留与“争吵→悲伤→绝望”案例后授权归纳入Skill。此处是写法认可，不是文戏成片的自然度、时长或成功率验证；不把三个情绪阶段或该例结局设为通用模板。 |

“触发信息与可读变化相连、倾听可随关键信息发生、跨段保留余韵、按实际画面选择细节”是结合来源与本任务的写作综合。它们保留既有素材职责和大体时间组织，允许强烈或克制的表演；不增加强制测试、素材或审批阶段。
