---
name: beatra-ai-video-studio
description: "从一段镜头描述、一张图片、首尾帧、参考素材或已有视频出发，规划并制作短视频。Beatra AI视频工作室支持文生视频、图生视频、参考生视频、首尾帧视频、AI视频编辑和AI视频延长，覆盖产品视频、广告创意、社交短视频、AI空镜素材、转场、揭示和电影感概念镜头。交付后检查动作、主体稳定性、运镜、连续性与发布场景；如果请求或结果包含音频，也一并检查音频，再决定最小有效的修改、延长或重新生成。"
---

# Beatra AI视频工作室

把一个想法或用户提供的素材制作成一条方向明确的短视频。先理解用户想要的结果，设计一个清楚易读的镜头，选择匹配的视频操作，并在提出下一个付费阶段前检查真实交付结果。

## 范围与相邻路线

此 Skill 适用于视频提示词增强、文生视频、指定一张开场图、指定一张尾帧与可选首帧、使用宽松的多模态参考、修改已有视频，以及在一条源视频前后紧接着补充画面。它是面向短广告、产品故事、社交短视频、空镜、转场、揭示和电影感概念的综合视频工作区。

字幕、旁白制作、语音合成和时间线组装是独立工作。多镜头请求可以规划并交付为多条独立视频，但此工作流不声称会把它们拼接成一条时间线。如果用户只需要口播数字人或图片动起来，应使用聚焦的 talking-avatar 或 image-to-motion 工作流；如果用户需要更广泛的路线选择或多种不同镜头类型，则留在此处。

优先使用用户已经提供的素材。当请求以文字为主且没有可用静帧时，第一个付费阶段是 `beatra.videos.enhance_prompt` 或一张 `beatra.images.generate` 关键帧，各自使用自己的确认卡。这次礼金体量的首胜并不授权 `beatra.videos.generate`、`beatra.videos.animate`、`beatra.videos.interpolate`、`beatra.videos.generate_from_references`、`beatra.videos.edit` 或 `beatra.videos.extend`。不要在未说明的情况下替换可用素材。

## 输入与默认值

最低硬性输入是以下任意一种：

- 一段镜头文字描述；
- 一张必须作为开场帧且可访问的图片；
- 一张必须作为尾帧且可访问的图片，以及一张可选的首帧图片；
- 顺序和用途明确、可访问的图片、视频或音频参考，数量和时长符合所选实时模型卡的限制；或
- 一条可访问的源视频，加上精确的修改指令或延长方向。

只询问会改变路线或结果的信息。复用已知的发布场景、时长、画幅、分辨率、主体、动作、运镜、节奏、音频意图、视觉参考和必须保留项。没有指定时，默认制作一条短视频，采用一个清楚易读的动作、一个主要运镜、`model: "auto"`、所选实时模型卡允许的最短整数时长，以及卡允许的最低分辨率，除非用户点名更高档（Pro / 2K / 1080p）。不要在 `model: "auto"` 时省略时长，也不要在卡允许更短整数时写死 8、10 或 15。音频主导的时长仍由音频决定：写入不短于真实语音或歌曲长度、且卡允许的最小整秒，不要为了省钱而缩短台词。`beatra.videos.extend` 的 `duration` 是最终返回总时长，必须大于可信的源视频时长。以源素材为主导的路线默认省略宽高比，除非用户明确同意改变画布。

对于宿主 Agent 能访问的本地图片、音频或视频，先检查素材，再使用随包上传助手：

```text
python3 scripts/mcp_client.py upload ./approved-input.mp4 --mime-type video/mp4
```

上传只是传输，不是媒体检查。保留返回的 artifact 引用，绝不要把本地路径传给远程工具。

## 选择一条视频路线

每个逻辑付费阶段只选择一种视频操作：

1. 以文字为主且没有可用静帧：第一个付费阶段是 `beatra.videos.enhance_prompt`（读取 `video_prompt_enhancement` 模型事实），或一张 `beatra.images.generate` 关键帧（读取 `text_to_image` 模型事实）。各自使用自己的确认卡。提示词增强只返回文本，并在任务成功后根据实际 token 计费。关键帧只是一张静帧。二者都不授权后续视频调用。
2. 在那次礼金交付之后，或仍没有可用静帧但提示词已就绪：使用 `beatra.videos.generate`，并读取 `text_to_video` 模型事实，且必须先出示视频入场卡。
3. 一张图片是严格开场帧：使用 `beatra.videos.animate`，并读取 `image_to_video` 模型事实。
4. 一张图片是严格尾帧，并可选提供严格首帧：使用 `beatra.videos.interpolate`，并读取 `frames_to_video` 模型事实。
5. 有序图片、视频或音频素材用于指导一条新视频，但不固定边界帧：使用 `beatra.videos.generate_from_references`，并读取 `reference_to_video` 模型事实。
6. 必须修改已有画面：使用 `beatra.videos.edit`，并读取 `video_edit` 模型事实。
7. 必须在且仅在一条源视频前面或后面紧接着补充画面：使用 `beatra.videos.extend`，并读取 `video_extend` 模型事实。其必填整数 `duration` 是最终返回视频的总时长，必须大于可信的源视频时长，并不是要增加的秒数。

不要随意交换这些路线。提示词增强只返回文本，不会开始视频生成。编辑会改变已有内容，延长会续接一条视频，参考素材会指导一条新视频，图片动画会把一张图片保留为开场帧，插值会保留必选尾帧和可选首帧。`beatra.videos.extend` 既不会拼接多条视频，也不会组装时间线。

## 黄金路径

1. 检查所有可访问的源素材。记录每份素材的角色及其真实 MIME 类型、字节大小、图片尺寸与宽高比、音频和视频时长，以及实时模型卡要求的其他事实。说明发布场景、一个可见事件、节奏、运镜、音频意图和必须保留项。如果宿主无法检查某项属性或素材本身，应直接说明，而不是编造。
2. 从七条路线中选择一条。遇到来源含糊或多镜头工作时阅读意图与路线（references/intent-and-routing.md），并阅读镜头设计（references/shot-design.md）把目标整理成简洁方向。当请求以文字为主且没有可用静帧时，第一个付费阶段是提示词增强或一张关键帧；静帧选项阅读图片辅助视频（references/image-assisted-video.md）。
3. 在依赖模型可用性、可接受输入组合、媒体限制、控制项、时长、画幅、分辨率或价格前，为该阶段的精确能力调用 `beatra.models.list`。除非用户选择了一个具体且符合条件的模型，否则保留 `model: "auto"`。用户明确指定的模型必须按原请求评估，绝不能静默替换。在调用 `beatra.videos.generate`、`beatra.videos.animate`、`beatra.videos.interpolate`、`beatra.videos.generate_from_references`、`beatra.videos.edit` 或 `beatra.videos.extend` 之前，写入卡允许的最短整数时长（音频主导和延长规则不变），以及卡允许的最低分辨率，除非用户点名更高档。
4. 根据一张当前可用的模型卡检查完整 payload。按需比较真实媒体类型、MIME 类型、字节大小、尺寸、宽高比、时长、参考数量与组合，以及受支持的控制项。编辑和延长还要包含可信的源视频时长。如果缺少必需事实，或没有实时模型卡接受计划中的 payload，应在付费调用前停下，只请求最小的兼容素材或计划调整。
5. 当第一个付费阶段是礼金体量的首胜时，先出示该阶段自己的确认卡——`beatra.videos.enhance_prompt` 使用路线 `video_prompt_enhancement`、工具、提示词、若已设置的目标时长和画幅，以及实时临时估算；一张关键帧使用路线 `text_to_image`、工具 `beatra.images.generate`、方向、若已设置的画布、输出数量和实时临时估算——然后只提交该阶段一次并交付文本或静帧。仅在一至四张有序参考图需要组成新镜头画面时使用 `beatra.images.transform`；使用 `beatra.images.edit` 时，`images[0]` 是底图且只应修改有限部分。在构建依赖它的视频工作前，检查交付的静帧。这张礼金卡不授权任何视频调用。
6. 在创建任何 `client_request_id` 或调用 `beatra.videos.generate`、`beatra.videos.animate`、`beatra.videos.interpolate`、`beatra.videos.generate_from_references`、`beatra.videos.edit` 或 `beatra.videos.extend` 之前出示视频入场卡：路线和 MCP 工具名、实时模型卡时长、分辨率和画幅、实时临时估算、注册赠额 600 分通常买不起这一单视频，以及余额不足时怎么办。数值估算只能来自当前模型卡；终态任务的 `billing.net_charged_credits` 才是最终值。规划、比较或「去做这条短片」不构成批准。在用户确认已充值或余额足够覆盖本次估价之前，不要创建 `client_request_id` 或提交。
7. 使用一个不透明且稳定的 `client_request_id` 冻结精确 payload。只调用随包客户端：把 MCP 工具名放在 `call` 后，并通过标准输入传入 JSON 参数。下面的例子使用已准入时长 `5`；请替换为当前模型卡实际允许的最短整数：

   ```text
   printf '%s' '{"prompt":"A close product reveal with one slow push-in and a stable background.","model":"auto","duration":5,"client_request_id":"opaque-video-id"}' | python3 scripts/mcp_client.py call beatra.videos.generate
   ```

   不要配置、调用或依赖宿主 Beatra Connector。不要使用 REST/OpenAPI 作为降级方案。已冻结的请求只提交一次。
8. 立即记录返回的任务 ID，并使用 `beatra.tasks.get` 轮询同一任务直到终态。queued 和 running 表示仍在进行，并非失败。不要因为任务较慢而重新提交。
9. 交付所有返回的视频或图片 artifact 或链接。只报告真实的终态状态、解析后的模型、尺寸、时长、用量和 `billing.net_charged_credits`。检查可访问的结果是否符合请求的动作、主体稳定性、运镜、连续性、音频、必须保留项和发布场景，并说明宿主 Agent 能检查与不能检查的内容。
10. 推荐最小有效的下一步：接受视频、做一次聚焦编辑、延长视频，或重新生成。绝不要暗示一条未经检查的视频已经是完成的宣传成片。

## 多镜头工作与付费确认

对于多镜头请求，把每个镜头规划为单独交付的视频。在执行前冻结镜头清单、每个阶段的路线和精确 payload、依赖关系、必需或可选的静帧阶段、付费调用总次数和临时估算。以文字为主且没有可用静帧的镜头，仍须先出示礼金体量的提示词或关键帧确认卡。对整套计划的一次明确确认并不授权任何视频阶段；每次视频生成、动画、插值、参考、编辑或延长仍须出示各自的入场卡，并等待充值或余额确认。每个付费请求仍须使用自己的稳定 ID，并且只提交一次。

按顺序运行依赖阶段。先检查图片再制作对应视频；在下游依赖某条视频或返回的最后一帧前，也先检查它。如果某次交付实质改变了下一个已批准镜头，应暂停并重新规划下一阶段，而不是静默沿用过时假设。交付独立视频，并说明时间线组装不属于此工作流。

## 变更、恢复与取消

工具、模型、来源、来源顺序、提示或指令、方向、时长、宽高比、分辨率或可选控制项发生变化，都属于新的逻辑付费工作。分配新 ID，为视频阶段出示新的入场卡，并重新取得充值或余额确认，除非该变更已包含在一个冻结且已准入的序列中。绝不要为变化后的参数复用 ID。遇到 `insufficient_balance` 时，转述返回的公开文案，余额错误里的充值地址保持原样，翻译其余部分，只有用户说已充值后才用同一冻结 `client_request_id` 重试。

如果创建响应丢失，只能使用相同请求 ID 重试完全一致的已冻结 payload。如果任务 ID 丢失，针对相关能力调用 `beatra.tasks.list`，再用 `beatra.tasks.get` 检查可能的候选任务，并对照私有请求台账匹配，然后才可以考虑完全一致的重试。规划替代工作前先恢复原请求；绝不要重复提交付费请求，也不要猜测其 artifact、扣费、退款或状态。

只有用户要求取消时才调用 `beatra.tasks.cancel`。只调用一次，并使用 `beatra.tasks.get` 确认产生的终态。409 并不表示已取消，因此应继续轮询同一任务，而不是创建替代工作。

## 账户余额

用户问还剩多少积分，或某次实时估价够不够时，调用 `beatra.wallet.get`。问已经扣了多少
时，调用 `beatra.wallet.ledger`。两者都是只读的。不要臆造查余额或充值的工具。也不要把
`wallet.get` 变成每次付费提交前的必需步骤。

模型卡返回里带 `top_up` 块时，按卡片给出的档位和顺序原样转述。不要给档位排高低，不要
贬低其中任何一档，也不要替用户挑。选哪一档是用户自己的事，钱包页会把整份清单摆在他
面前。任何时候都不要凭记忆报档位。

## 按任务查阅参考资料

- 阅读意图与路线（references/intent-and-routing.md），以分类用户提供的媒体、区分全部七条路线，或规划单独交付的多镜头内容。
- 阅读镜头设计（references/shot-design.md），以设计主体动作、运镜、节奏、画布、音频意图和保留重点。
- 当没有可用静帧，或不合适的静帧需要单独图片阶段时，阅读图片辅助视频（references/image-assisted-video.md）。
- 阅读视频方案（references/video-recipes.md），以查看精确 payload 形态、按路线进行的实时模型与媒体准入、视频入场卡、上传语义和付费执行。
- 阅读检查与迭代（references/review-and-iteration.md），以检查终态结果并选择一个聚焦的下一步操作。
- 仅在授权或共享凭据需要处理时阅读安装与身份验证（references/installation-and-auth.md）。
- 阅读安装注册（references/installation-registration.md），了解不计费的尽力而为包注册步骤。
- 阅读任务与结果（references/tasks-and-results.md），了解共享任务和 artifact 语义；阅读账单、错误与恢复（references/billing-errors-and-recovery.md），了解返回的账单或错误详情。
- 当随包客户端无法连接时阅读随包 MCP Client 连接诊断（references/mcp-connection.md）。不要配置宿主 Connector。
- 更新与安全：更新与安全（references/updates-and-security.md）
- 仅在用户要求删除此包或共享凭据时阅读卸载与断开连接（references/uninstall-and-disconnect.md）。

每次 Beatra 操作都只能使用或调用随包的 `scripts/mcp_client.py`。

## 更新与安全

本 Skill 会自动更新。内置客户端每天最多一次从 Beatra 官网读取本渠道的版本信息
（中国大陆网络走 www.beatra.cn 与 cdn.beatra.cn）。有新版本时，它下载官方发布包，
逐个文件校验 SHA-256，再替换本 Skill 自己的文件；你放进这个目录的其他文件不会被
改动。替换过程中断时，下次运行会自动恢复到替换前的状态。除此之外，它不下载或执行
任何其他代码，只通过 HTTPS 与 Beatra 官方服务通信；你选择上传的文件只会传到
Beatra 为这次上传签发的一次性地址。

关闭自动更新：`python3 scripts/mcp_client.py update --auto off`。关闭后，客户端每天
最多提示一次在你安装它的商店里更新的命令。详见更新与安全（references/updates-and-security.md）。
