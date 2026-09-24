# 声音资产与对白镜头

生成声部由[视频条数与声音计划](sound-plan.md)决定。这里负责采用录音、片段与口型交接，不要求所有任务原生完成全部声音。

无人声不建立配音待办；画外旁白不要求口型；现场真人讲述不自动成为片内声音。复用已采用声线与录音，原录音保留完整；只有本次任务确需准备新录音且已选定供应商时，使用对应可用工具并核对实际入口与鉴权；不输出凭据，不因命令不在PATH就重装。克隆按实际授权执行。真人录音或已授权素材无需虚构供应商voice_id。

`voice.data`记录`source_type: synthesized | recorded | licensed`、实际台词text、说话者、source_duration（兼容duration_seconds）、来源依据source_evidence、试听采用依据adoption_evidence及真实文件。合成来源记录可取得的声线标识或来源依据、语言、模型、语速与实际参数/任务标识；供应商不提供voice_id时不虚构。只送台词，不送角色标签、中文释义或舞台指令；触发单位与多角色按任务分开。声线身份由试听核对，不由编号保证。

`package.data.audio_uses`逐项记录record_id、source_in/source_out（源秒数）、start（片内开始秒数）和implementation：

- native_recording：录音确实上传，入口有preserves_recording与evidence；画内对白另须native_lipsync。只用源片段时另核实supports_audio_range与range_evidence；不假定提示词能精确裁片。
- external_overlay：仅画外声音在后续原声对齐。记录handoff与authorization_evidence；不是当前生成模型的附件，也不能冒充当前视频已经有声。
- post_lipsync：已授权后续口型处理，记录handoff与authorization_evidence；当前交付画面及明确待办，不标口型完成，不在本Skill内擅自接入后期服务。

需要模型直接生成对白时，使用`implementation: native_generation`，在该项及实际投喂正文中写明相同的台词text与说话者speaker，并以`audio_capability.native_speech`、evidence核对当前入口；画内对白还需核对native_lipsync。它不引用虚构录音文件或voice_id。未写audio_uses的旧包按整段原生录音解释，不自动迁移历史。speech=none/offscreen/dialogue继续兼容；speech描述人声关系，不替代可组合sound_plan。上传录音列references与depends_on；外部交接录音只列depends_on及audio_uses，导出单独交接文件，不能伪称已上传。

源文件规格与片内采用长度分别检查。采用范围必须落在真实源长度内，播放区间容纳于视频窗口；上传文件仍按[出稿协议](prompt-delivery-check.md)实测完整长度及入口限制。台词超时先调整受影响设计，不默默加速、补静音或重复台词。只在新来源、规格变化或实际错误时核查，复用仍有效依据。

结果按本次实现路径检查台词、说话者、语言、听感、时机、声音重复及必要口型。画面完成、声音待对齐、口型待处理与全部媒体完成分别报告；已生成不等于采用。不合格按已有修改与消耗授权定点修复，未授权的再次提交另说明。
