# 执行与验收约定

本文件用于实际运行阶段工具。命令中的 `<skill>`、`<project>`、`<python>`、`<node>`、`<adapter-script>` 均替换为实际路径，含空格时加引号。PowerShell 调用带引号的可执行路径时，在前面加 `&`。所有 JSON 均使用 UTF-8。

## 生图提示词的禁写信息

阶段 2.1／2.2 的新生成与图生图修订提示词，**禁止写文本框的具体尺寸、字号、元素具体坐标**：不写固定宽高、数值尺寸、字号指令或 x／y、像素位置、归一化坐标。允许并必须说明文本框高度贴合文本、仅保留适量内边距、避免框内大片留白；允许说明顺着分块边界排列或裁切显示边缘。保留分区与阅读顺序、文字内容和语义角色、框形与颜色、图片位比例、风格、导航及逻辑关系。整页画布 16:9（1920×1080）与图片位宽高比继续保留。具体坐标、文本框尺寸、字号和裁切轮廓点只留在本地设计稿、图片计划和重建规格中；不得将含这些信息的原始设计稿全文拼入提示词。

## 规范库索引（按步骤）

规范库按步骤分段：**每开始一个步骤，先读一遍该步骤在索引里列出的章节**（再动手；跨越步骤时重读对应章节，不要凭记忆）。本文件与 [共享工件约定](artifact-contract.md) 是同一套规范库的两部分。

| 步骤 | 开工前必读（本文件） | 开工前必读（工件约定） |
|---|---|---|
| 0 建立环境 | 《环境与版本》《材料、定稿和来源》 | 《阶段状态》《编号与来源》《坐标与画布》《日志》 |
| 1.1 需求与材料 | 《用户确认与阶段版本》《材料、定稿和来源》 | 《阶段状态》《目录与进度条》《编号与来源》 |
| 1.2 内容与素材清单 | 《独立素材生图任务》《阶段 1.2 内容与素材清单》 | 《AI 素材证据链》《生图提示词记录》《编号与来源》 |
| 1.3 设计稿与复核 | 《阶段 1.3 设计稿与复核》《用户确认与阶段版本》 | 《目录与进度条》《图片与重建来源》《编号与来源》 |
| 2.1 A/B/C 方案确认 | 《阶段 2.1／2.2 分块参考图》《整页预览生成与组装》《逐页视觉检查与回调》 | 《整页预览与分块参考图》《AI 素材证据链》《生图提示词记录》《目录与进度条》 |
| 2.2 完整预览批准 | 《阶段 2.1／2.2 分块参考图》《整页预览生成与组装》《逐页视觉检查与回调》《用户确认与阶段版本》 | 《整页预览与分块参考图》《AI 素材证据链》《图片与重建来源》 |
| 3.1 元素拆解 | 《重建与构建》 | 《可编辑性约定》《图片与重建来源》《坐标与画布》 |
| 3.2 素材重建 | 《重建与构建》《独立素材生图任务》 | 《图片与重建来源》《编号与来源》《AI 素材证据链》 |
| 3.3 组装与交付 | 《重建与构建》《渲染、审阅与交付》 | 《可编辑性约定》《进度条文本》《日志》 |
| 4 演讲稿（可选） | 《渲染、审阅与交付》 | 《日志》 |

## 环境与版本

需要 Python 3.11 及以上、Node.js，以及 `shared/requirements.txt` 和根目录 `package.json` 中声明的依赖。本版本测试环境为 Python 3.12、PptxGenJS 4.0.1、Sharp 0.35.4、jsonschema 4.26.0、Pillow 12.3.0、PyYAML 6.0.2。没有依赖时，由使用者在选定环境安装；环境检查器不自动安装软件。Windows 中文环境读取含中文的 UTF-8 脚本和 Markdown 前先设置 `$env:PYTHONUTF8='1'`。

```powershell
$env:PYTHONUTF8='1'
python <skill>/stages/00-init/scripts/check_environment.py --node <node> --project <project>
# 字体检查：必需字体族可重复给出；缺失时返回非零退出码，结果写入 00_intake/font-report.json
python <skill>/stages/00-init/scripts/check_environment.py --node <node> --project <project> --font "Microsoft YaHei" --font "SimHei"
# 仅当需要核查显式覆盖脚本是否与配置一致时，再加 --adapter-script <adapter-script>
python -m pip install -r <skill>/shared/requirements.txt
npm install --prefix <skill>
```

字体清单覆盖微软雅黑、黑体、宋体、等线、楷体、思源黑体、Noto Sans CJK、Arial、Times New Roman 和 Cambria，并记录每个族的常规体与粗体是否可用。预览与成品必须使用设计稿声明的字体族；缺少字体时在 `00_intake/font-report.json` 记录回退方案，并在逐页看图时确认字面与换行没有变化。字号换算见[中文排版与字号规范](../stages/13-design/references/typography-cjk.md)：预览像素值 ÷ 2 = 交付磅值。

构建器首先使用普通 Node 依赖解析，其次使用 `CODEX_NODE_MODULES` 或本机已配置的 Codex 依赖目录。设置 `PPTX_PYTHON` 或传 `--python` 可指定 Python。依赖版本已固定，但未交付跨平台锁文件；更换环境需重新验证。现有 PPTX 模板导入不受支持，品牌样式需重建为原生对象，不能声称直接套用了用户母版。

## 材料、定稿和来源

`01_inventory/materials.json` 是机器可读材料清单；Markdown 保留材料含义、冲突和证据说明。登记命令计算原件 SHA-256，不移动原件：

```powershell
python <skill>/shared/scripts/workflow.py <project> material --id PHOTO-001 --path 00_intake/materials/photos/site.jpg --kind photo --description "现场实拍"
```

只有用户允许该材料发送到外部生图服务时，才加 `--allow-external-upload`。路径可以是项目内相对路径或外部绝对路径；后者不可移植，打包交接时须在获得授权后复制原件并重新登记。原件变化会使正式交付检查失败。

阶段 1.1 必须把目录页和顶部进度条结论写入 `00_intake/project-brief.md`，并在需求批准前记录用户原话。阶段 1.3 编写 `02_design/content.json`，作为准确文案、页面顺序、目录条件和进度条条件的唯一机器来源。设计稿必须分别包含 `## 目录要求` 与 `## 顶部进度条要求`；后者原句是“在除标题页和目录页外的每一页上方添加进度条”，必须作为独立要求保留。

`content.json` 的关键结构如下：

```json
{
  "include_toc": true,
  "progress_bar": {
    "enabled": true,
    "exclude_page_types": ["title", "toc", "thanks"]
  },
  "sections": [
    {"id": "SEC-01", "title": "研究背景与问题", "slide_ids": ["S03", "S04"]},
    {"id": "SEC-02", "title": "方法与数据", "slide_ids": ["S05", "S06", "S07"]}
  ],
  "slides": [{
    "id": "S01",
    "page_type": "title",
    "layout_id": "T01",
    "reference_categories": ["title-T01"],
    "reference_ids": ["R058"],
    "title": "项目阶段进展",
    "texts": [
      {"id": "S01-TITLE-01", "text": "项目阶段进展", "source": "用户确认主题"},
      {"id": "S01-BODY-01", "text": "已完成现场调研，正在整理结果。", "source": "REPORT-001，第 3 页"}
    ],
    "materials": ["PHOTO-001", "REPORT-001"]
  }]
}
```

需要目录时，第二页必须是唯一的 `toc`；不需要时全篇不得出现 `toc`。标题页必须排除进度条；存在目录页时目录页也必须排除，存在致谢页时致谢页也必须排除。其余默认合格页面各自包含且只包含一个 `progress` 元素。

进度条启用时必须提供 `sections`：它们是进度条分段与标题的唯一来源，标题与目录页逐字一致，且必须覆盖除标题页和目录页外的全部合格页面，每页属于且只属于一个小节。小节标题即进度条内的文字；条内要写全部小节标题、当前小节放大或加粗、当前分段与整条存在色差，具体见[参考风格与选型规范](../stages/13-design/references/style-guide.md)的《顶部进度条设计规范》。

所有原生文本框，包括页码与脚注，都应登记在 `texts`；**图片来源不需要在页面上标注**（来源只留在设计稿、材料清单与图片意图里），但**图片旁边要有图片说明（图注）**：每张图一句，写进设计稿《图片意图总表》的「图片说明」列，并作为上屏文本（`Sxx-CAPTION-01`）登记进 `content.json` 的 `texts`。表格和图表数据在构建规格中定义，通过原始数据来源和逐页人工审阅核对；当前不会自动证明它们与原始报告的事实一致。

阶段与步骤的对应关系见[工作流总览](../SKILL.md)（0–8 步）；本文件只写执行命令与验收口径。

## 用户确认与阶段版本

只在用户实际确认后执行批准命令，`--evidence` 填写确认原话或可定位的会话记录。不能由代理编造用户确认；JSON 记录用于追溯，不是身份认证或防篡改系统。

**停机点**只有四个：`1.1`（需求与材料确认）、`1.3`（设计稿复核）、`2.1`（A/B/C 方案确认）、`2.2`（完整预览批准）；交付完成（全部阶段 `complete`）是任务的终点。除停机点外，代理**不得结束任务进程**：`0`、`3.1`、`3.2`、`3.3` 以及每个阶段内部都要连续执行到下一个停机点。

- `await <阶段>` 只接受这四个阶段，其他阶段会直接报错。
- 停机点阶段必须先暂停再完成：每个停机点都运行 `await <阶段>`（`await 1.1`、`await 1.3`、`await 2.1`、`await 2.2`）把结论交给用户；没有这一步 `complete` 会被拒绝。
- `stop-point` 报告当前能不能停：退出码 0 表示合法停机点或已交付，非 0 表示必须继续（`status` 也会打印同样的一行）。

```powershell
python <skill>/shared/scripts/workflow.py <project> stop-point
python <skill>/shared/scripts/workflow.py <project> await 1.1 --notes "需求与材料清单待用户确认"
python <skill>/shared/scripts/workflow.py <project> approve requirements --evidence "用户确认记录"
python <skill>/shared/scripts/workflow.py <project> complete 1.1
python <skill>/shared/scripts/workflow.py <project> complete 1.2
python <skill>/shared/scripts/workflow.py <project> await 1.3 --notes "设计稿待用户复核或修改"
python <skill>/shared/scripts/workflow.py <project> complete 1.3
python <skill>/shared/scripts/workflow.py <project> await 2.1 --notes "A/B/C 三版预览待用户选定"
python <skill>/shared/scripts/workflow.py <project> approve concept --option b --evidence "用户确认采用 B 方案"
python <skill>/shared/scripts/workflow.py <project> complete 2.1
python <skill>/shared/scripts/workflow.py <project> approve preview --evidence "用户确认完整预览"
python <skill>/shared/scripts/workflow.py <project> complete 2.2
python <skill>/shared/scripts/workflow.py <project> status
```

每轮回复结束前运行 `stop-point`：只有它返回 0（停在合法停机点，或全部阶段已完成）才允许结束，否则必须继续跑完当前阶段再到下一个停机点。

阶段 1.3 的设计稿 Markdown 是用户直接修改的复核入口。设计件写完后先 `await 1.3`，在对话中给出设计稿绝对路径与建议复核要点；用户给出继续指令后，重新读取设计稿、同步受影响的 JSON、把复核原话与日期写入“设计状态”，再 `complete 1.3`。阶段未处于 `awaiting_user` 时 `complete 1.3` 会拒绝执行。

其他阶段同样用 `complete 2.2` 等标记完成。工具检查前置阶段并保存文件指纹；重新完成上游阶段会把下游重置为未开始。`status` 会把已变化的阶段及其下游显示为 `stale`，不删除原文件。批准绑定文件版本，改动需求、材料清单、选中预览或定稿后需要重新核实批准。旧版状态文件可以保留，但未绑定指纹的旧完成记录必须重新验收。

## 独立素材生图任务

**所有 AI 生图的提示词都要写进 `02_design/generation-prompts.md`**（一个文件，按「## 阶段 1.2／1.3／2.1／2.2」分节，逐个任务写 id、素材编号、用途、参考图与提示词全文）；`complete` 会在 1.2／2.1／2.2 核对该阶段的每个任务都出现在里面。

生图前先读取并验证 `00_intake/ai-image-config.json`。供应商、模型、凭据环境变量、适配脚本、参考图上传许可和 `referenceImageLimit` 必须已经在阶段 1.1 由用户确认；生图不设次数预算，脚本忽略旧配置里的 `stageBudgets`，但费用要按供应商定价向用户估算说明。脚本不得读取或输出密钥值，也不得静默切换供应商、模型或适配脚本。适配器通过配置的 `adapterArguments` 映射到具体供应商命令；默认 `gpt-image-2`（VSAKURA）只是预填值，不把任何一家视为唯一协议。

阶段 2.1／2.2 的 AI 输出是**整页预览**（一页一张 1920×1080 整页设计图），阶段 1.2／1.3 的输出是独立素材。两者都必须给出稳定 `asset_id`，输出必须是 `{stage-dir}/assets/{asset_id}.png`。示例：

```json
{
  "jobs": [
    {
      "id": "CONCEPT-A-S01",
      "asset_id": "GEN-001",
      "prompt": "S01 整页预览：\n① 比例要求：16:9 画布（1920×1080）。\n② 内容要求：……\n③ 排版要求：……\n④ 图片占位框比例：……\n⑤ 风格要求：主色 #2F5D62，背景与装饰用与所给大图相近的颜色（同一套配色）。\n⑥ 进度条要求：无进度条。",
      "model": "gpt-image-2",
      "size": "1536x1024",
      "asset_mode": "crop",
      "output": "03_concepts/assets/GEN-001.png",
      "max_attempts": 4,
      "intended_use": "S01 的整页预览（按设计稿 S01 的分块、文字层级与图片位生成）",
      "factual_boundary": "整页预览为 AI 生成示意，不代表真实人物、地点、标识或数据"
    }
  ]
}
```

阶段 2.2 的任务字段相同，但输出根目录改为 `04_full-preview/assets/`，且每个任务对应 `content.json` 里的一页、必须覆盖全部页面。`asset_id` 在所有生图阶段间保持唯一，同一素材在同一页只登记一次使用。整页预览任务的提示词必须写明页面编号与该页设计稿内容；`references` 可以复用本项目的既有产物（如更早的预览），引用外部材料时只能列出已登记且获准上传的材料。

任务清单不需要次数预算：`max_total_attempts` 已废弃（保留仅为兼容旧文件，脚本忽略）。`max_attempts` 可选，用来覆盖命令行 `--attempts`，含义是“单任务在本轮运行内的重试上限”，默认 8，可按需要调大；失败后可以再次运行继续重试，累计次数只记录在账本里、不设上限。

需要把已生成的素材改成更贴合主题、更协调的独立素材时，可以做生图编辑，用 `edit_source` 指明被编辑的本阶段素材，输出使用新的 `GEN-###` 并保留原图与来源关系（不得另起无来源编号绕过原图）：

```json
{
  "jobs": [{
    "id": "FULL-MOTIF-02-EDIT",
    "asset_id": "GEN-105",
    "prompt": "在保留原六边形节点网络结构的前提下，把配色改为浅蓝白、降低对比并添加半透明层次，无文字、无人物、无标识、无实验数据",
    "model": "gpt-image-2",
    "asset_mode": "preserve",
    "edit_source": {"assetId": "GEN-104", "path": "04_full-preview/assets/GEN-104.png"},
    "output": "04_full-preview/assets/GEN-105.png",
    "max_attempts": 4,
    "intended_use": "内容页右侧的装饰纹样（用该方向的元素图插入）",
    "factual_boundary": "只作抽象装饰，不代表真实人物、地点、标识、数据或实验结果"
  }]
}
```

`edit_source` 只能指向同一阶段的 `assets/GEN-###.png` 稳定路径，被编辑素材必须已经存在；它与 `references` 一起计入用户确认的 `referenceImageLimit`，并要求 `allowReferenceUpload` 为 true。账本记录被编辑素材的编号与 SHA-256。被编辑素材本身保留，不覆盖、不改名。

`asset_mode` 可取：

- `preserve`：默认，完整保留供应商原始纵横比和尺寸，素材可用于任意本地裁切。
- `pad`：必须同时给出 `asset_size` 和 `asset_background`，等比缩放后在本地补边。
- `crop`：必须同时给出 `asset_size`，按明确目标尺寸裁剪，不得拉伸。

AI 原始素材不以 16:9 为必要条件；只有整页预览和正式渲染图强制 1920×1080。不得使用 `preview_mode` 或 `preview_background` 等旧字段。

```powershell
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage content --execute
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage concepts
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage concepts --execute
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage full --execute
# 仅在排查时显式覆盖，但必须与 ai-image-config.json 的 adapterScript 指向同一脚本：
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage concepts --adapter-script <adapter-script>
# 默认模型 gpt-image-2（VSAKURA）不支持 seed：任务里不要写 seed；--qwen-script 是旧命令兼容别名，不应用于新项目。
```

默认只检查并显示任务计划；`--execute` 才调用付费服务。生图不设次数预算，费用需按实际供应商定价估算并向用户说明。每一轮运行会为每个任务重试到成功或达到单任务上限（`--attempts`，默认 8；可用任务的 `max_attempts` 覆盖）；配置类错误（供应商、模型、凭据、适配脚本不一致）立即停止，避免继续计费；失败的任务可以直接再次运行继续重试。相同输入、脚本、素材和输出指纹命中时复用缓存。超时也计入尝试次数，因为供应商可能已经计费。不得切换到未获准供应商。

组装时发现缺少素材或效果不理想，可以直接追加新的独立 `GEN-###` 任务、重新生图并组装；不设次数预算，只需在日志里记录尝试次数与费用估算，并向用户说明本轮大致花费。

参考图数量不得超过配置中的 `referenceImageLimit`，且每张须为已登记、获准上传的本地材料；风格参考图也先登记为材料并记录上传许可。`generation-ledger.json` 只保留供应商、模型、请求编号、提示词哈希、适配脚本哈希、原始／规范化输出哈希、规范化记录、次数和状态。中断后的 `in_progress` 不视为成功，已消耗次数保留。同一个项目不要并行运行多个生成器；项目状态变更使用现有项目锁，锁不表示不同生成任务可以安全并行。

### 阶段 1.2 内容与素材清单

按 PPT 要求从已登记材料里选出上屏文字与图片，再按三种设计方向（`styleId` a/b/c）各生成一组候选图片（封面大图、内容页背景底图，有目录页时每个方向各多一张，致谢页复用背景底图），**候选图片统一 16:9（1920×1080）横版，封面大图／目录页大图／背景底图的提示词里要写明 16:9**；最后把文字内容与候选图片编号按叙述顺序写成 `02_design/content-plan.md`（Markdown 分级、同级文字同层、避免平行结构，每张图片配一句说明）。做法见[内容与素材清单](../stages/12-content/SKILL.md)。

```powershell
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage content --execute
python <skill>/shared/scripts/workflow.py <project> complete 1.2
```

- 任务与账本：`02_design/generation-jobs.json`、`02_design/generation-ledger.json`；候选图片输出 `02_design/generated-assets/GEN-###.png`，登记到 `02_design/generated-assets.json`；
- `complete 1.2` 会核对：清单存在且分级、覆盖全部候选与计划图片编号、三种设计方向（a/b/c）各至少一张 `hero-image` 与一张 `content-background`、每张候选图片可读／哈希一致／横版／有用途说明、大图提示词写明了 16:9、生图任务与账本一致。

### 阶段 1.3 设计稿与复核

设计稿逐页写下**最终上屏文字**（`- **上屏文案（最终文字）：**`——设计稿里的文字就是要放进 PPT 的最终内容，不是概述）与**详细排版分级**（按[设计稿模板](../stages/13-design/assets/design-spec.md)的《排版分级写法》：分块方式 → 各分块 → 分块上部／下部／左部／右部／分块内 → 并列文本逐条；每段文字或图片都写明对应的文本框或图像框；框内小元素可省略，选用时写明类型、颜色与位置），最终文字从阶段 1.2 的 `02_design/content-plan.md` 精简定稿，一段文本里有并列结构就拆成列表、条内再并列再降一级（列表套列表），避免单段过长；逐页还要写明「**元素位置与大小**」——每段文字与每张图片的归一化框 `x`／`y`／`w`／`h`（0–1）与叠放顺序，因为整页预览直接按设计稿生成，没有中间稿。逐页规划不得残留「待填写」：`complete 1.3` 会核对上屏文案字段、元素位置与大小、分块方式与占位文字；**两页之间不要用完全一样的特殊分块方式**（换一种分块或把形态差异写进分块方式），完全相同的组合会被拒。设计稿还要单列**《全篇叙述逻辑链》**一节：逐页写清这一页承接上一页的哪条结论、要回答或证明什么、把什么结论交给下一页，全篇形成因果与递进（不能只罗列章节名）；`complete 1.3` 会核对这一节存在。

```powershell
python <skill>/shared/scripts/workflow.py <project> await 1.3 --notes "..."
python <skill>/shared/scripts/workflow.py <project> complete 1.3
```

设计稿写完后必须**停机**等用户复核：用户可以直接改 `02_design/design-spec.md`；改完要重新 `await 1.3`／`complete 1.3`，在此之前不得生成任何整页预览（1.3 完成后设计稿再被改动会让 1.3 变成 stale，后续阶段的 `complete` 会拒绝）。
### 阶段 2.1／2.2 分块参考图

整页预览**没有骨架图中转稿**：设计稿的《排版分级》与《元素位置与大小》就是排布依据。用到分块参考图的页面，要把**分块参考图**连同设计提示词一起交给 AI——9 种特殊分块（斜切／弧线／扇形／同心圆／波浪／金字塔／圆形放射／左圆右栏／六边形蜂窝）以及不计入特殊分块比例的**横带**与**四宫格（错位）**：

```powershell
python <skill>/shared/scripts/prepare_split_references.py <project>
```

- 脚本按设计稿《页面分块要求》匹配每页的分块方式，把 `shared/references/splits/` 里的形态样例复制到 `02_design/split-references/<分块>/`，并写出 `02_design/split-references.json`（逐页列出该页要给的参考图）；
- 把清单里该页的每条路径写进**该页整页预览任务的 `references`**（与设计提示词同时给出）；标题页、目录页、致谢页与纯常规分块页面不给参考图；
- 提示词要同时写明页面编号、分块方式与形态、设计稿分块行里的分标题（写了 `；分标题：（文字）` 的也要带进提示词并用真实文字画出；没写的不许自己加）、每段文字的文本框形状与颜色、标题／正文／注释的语义角色、逐张计划图片的图片位比例、计划图片只画比例一致的占位块；
- 参考图**只是分区参考**：只说明这一页分成哪几块、分界的走向／弯曲方向／顶点或圆心的相对位置；图上的黑线、线宽、锯齿与具体位置都**不要照抄**——预览里不画这些分界线，分区靠色差与构造间距；**弧线保持弧度、斜线保持倾角，不能简化成横平竖直的直线**；提示词还要写清分块方式名与形态（方向／倾角／走向／弯曲程度／圆心位置）；
- `complete 2.1`／`complete 2.2`（以及 `approve concept`／`approve preview`）会核对：`02_design/split-references.json` 存在且与设计稿分块方式一致、参考图已复制进项目、每条分块的参考图都进入了该页预览任务的 `references`，并且提示词写明了分块方式、形态、"不要直线化"、文字的语义角色与逐张图片位比例。

### 阶段 1.3 补充生成素材

设计稿阶段可以在用户允许生图后，补充装饰、纹理、抽象背景、主题纹样、贴合主题的简单图标和具象的说明性插画。使用同一份已确认配置与适配器，先 dry-run 核查供应商、模型、脚本、凭据就绪状态和上传许可，再显式执行。AI 只生成无文字视觉层，不生成需要准确表达的文字、数字或图表；现实风格插画必须标注为“AI 生成示意图”，不得伪装成真实照片、真实人物或实验证据。

生成后把原始返回图与规范化图存入 `02_design/generated-assets/`，把实际路径、SHA-256、供应商、模型、请求编号、提示词哈希、种子、`intendedUse` 和 `factualBoundary` 登记到 `02_design/generated-assets.json`。禁止用 Pillow、HTML、CSS 或本地绘图生成候选后伪装成 API 结果。设计阶段素材是后续风格方向的可追溯参考；若要在阶段 2.1／2.2 的本地预览中采用同一视觉语言，应在对应阶段登记新的独立 `GEN-###` 任务，不能绕过该阶段的证据链。

## 整页预览生成与组装

阶段 2.1／2.2 的整页预览**直接按设计稿生成**：写在《阶段 2.1／2.2 分块参考图》里的分块参考图先复制进项目、再放进该页任务的 `references`（特殊分块页必须给；标题页／目录页／致谢页与纯常规分块页不给），提示词给出设计稿的该页内容（页面编号、分块方式与形态、每段文字的文本框形状、**文本框颜色（填充与背景底色要有适度色差且避免强烈反差（不是边框色差））**、每段文字的语义角色、目录页条目的标号、逐张计划图片的占位框比例（**强调比例不能改变、不拉伸、不变形**）、设计稿写了的页内逻辑关系（箭头／箭形色块的起止与方向）、图片位与风格约束；**禁止在提示词中写元素具体坐标、文本框具体尺寸和字号；须写明框高贴合文本、适量内边距、避免框内大片留白**，提示词只以分区关系与阅读顺序表达布局，设计稿的《元素位置与大小》仅用于本地核对与重建，但每张计划图片的占位框比例必须逐张写清），并声明分块参考图只作分区示意（弧线保持弧度、斜线保持倾角，不能简化成直线）；照片与实验数据图只画占位块（提示词用分区与图片位比例表达，精确位置与比例在本地按 `image-plan.json` 核对，逐张记进预览清单的 `placeholders`；占位块要做成与背景可分辨的平坦色块，`complete 2.1／2.2` 会核对清单里的占位块位置、大小与比例——与登记原件的宽高比相差超过 12% 会拒；阶段 2.1 保留占位块；阶段 2.2 在 AI 底稿生成后本地插入登记原图并逐页实际查看，再等待批准），阶段 3.3 使用同一原件组装；**文字只用于表达内容与语义角色**，不要求模型逐字排印（成品文字由阶段 3.3 用原生文本按设计稿重建）。提示词要**按分点分行写**（① 比例要求 ② 内容要求 ③ 排版要求 ④ 图片占位框比例 ⑤ 风格要求 ⑥ 进度条要求）；⑤ 风格要求里要写明背景与装饰用与所给 AI 大图相近的颜色（同一套配色），`complete 2.1／2.2` 会比对该页预览与同风格大图的主色，相差过大直接拒。**撰写完提示词先自检再出图**：`run_generation.py`（dry-run 与 `--execute`）会逐页核对提示词里的分点结构、16:9 画布（1920×1080）、占位块与图片位比例、设计稿每段最终文字与文本框形状、风格要求与同风格配色要求、进度条要求（标题页／目录页／致谢页写明「无进度条」），缺一项直接拒绝生成。生成后逐页实看并回调提示词。

阶段 2.1 为 A/B/C 分别写 `03_concepts/option-a|b|c/preview.json`；阶段 2.2 写覆盖全部定稿页面的 `04_full-preview/previews.json`（含 `styleConstraints`）。字段必须符合 `shared/schemas/preview-pages.schema.json`，每页写明 `promptSummary`（这一页用了设计稿的哪些分块、文字层级与图片位），提示词必须写明页面编号。

## 逐页视觉检查与回调

整页预览由 AI 生成后没有本地逐元素机检：**每轮生成后必须逐页实际打开 PNG 看图**，逐页核对——文字是否排进设计稿标注的框位、层级与留白、重心与对齐、主题贴合度、进度条是否合规、跨页是否统一；另外**目测**每个图片占位块的宽高比是否与计划插入的原件比例一致（这是看图时的粗略检查、不是机检：完全一致的机检由 `complete` 负责，这里只需要一眼看出明显不对）；明显不一致就用图生图重画占位块，或修正清单里的占位框后复看。发现问题就回调：改提示词重生成、用 `edit_source` 局部编辑，或用 `crop_asset.py`／`cutout_asset.py` 调整裁切与抠图，再把问题与调整记入 `03_concepts/concept-review.md` 或 `04_full-preview/generation-log.md`。

```powershell
python <skill>/shared/scripts/workflow.py <project> await 2.1 --notes "..."
python <skill>/shared/scripts/workflow.py <project> await 2.2 --notes "..."
```

阶段 3.3 还须评审实际成品美观度，可按成品位置美化授权优化各元素位置，重新构建、渲染与审阅。项目内写入由根目录 `workflow.lock` 串行化：`workflow.py`、`run_generation.py` 等命令先取锁，锁存在时直接报错；同一项目不要并行运行生成器或构建，锁超过 10 分钟视为陈旧并被下一个进程接管。

## 重建与构建

参照 [deck 规格](schemas/deck.schema.json) 写 `06_build/deck-spec.json`。原生图形、SVG 和位图仍按阶段 3.2 分流；没有自动从整页位图还原任意矢量的工具。阶段 3.1 先逐页写出 `05_reconstruction/element-inventory.md`（非文字元素＋大致位置＋计划的分离方式；计划图片只按占位块记录，不拆、不抠），再写 `slide-elements.md`；阶段 3.2 按清单**逐个**还原：形状或颜色复杂用 AI 抠图／SVG 重绘，形状与颜色简单用 PPT 原生元素组装，不得遗漏或简化。阶段 3.3 的页面背景只能是该页对应的 AI 大图（标题页 `hero-image`、目录页 `toc-image`、其余页 `content-background`），不能改用其他图片充当背景。

- 坐标 `x,y,w,h` 使用英寸；归一化值转换为 `x*画布宽`、`y*画布高`、`w*画布宽`、`h*画布高`。
- `z` 从小到大绘制，相同层级保持原数组顺序；元素 ID 写入 PowerPoint 对象名。
- `origin` 缺省为 `planned`；`planned` 图片必须与 `image-plan.json` 的编号、来源、路径、位置和适配参数一致，本地预览只有在文件已存在时才嵌入，正式 PPTX 在 3.3 插入；成品美化的位置与层级可按本节授权记录调整，原图片计划保留为基线。`origin: "reconstruction"` 的图片、SVG 和局部抠图不由图片计划约束，作为独立对象插入。
- `image.fit` 为 `contain` 或 `cover`，默认前者；`cover` 可用 `focal:{"x":0.5,"y":0.5}` 指定原图归一化焦点。生成裁剪图片保留来源和嵌入字节哈希。局部抠图透明 PNG 必须设置 `preserveAlpha: true`，否则构建器会按背景色展平透明通道。AI 背景底图在预览里用 `background.asset.opacity`（0.10–0.35），在 deck-spec 里换算成 `transparency = 100 - opacity × 100`（例如 opacity 0.25 → `transparency: 75`），构建器会原样传给 PptxGenJS；底图必须是弱对比的内容页背景，不要把强反差照片铺满整页。
- 原始照片、标识和截图使用已登记 `sourceId` 和原件路径，裁剪交给构建器。计划中的生成素材保留 `GEN-`；局部抠图和非计划重建素材使用 `RECON-`。所有进入正片的生成、裁剪和重建素材都登记到 `05_reconstruction/assets.json`。
- SVG 必须有有效 `viewBox`，禁止 `script`、`foreignObject`、外部链接与嵌入位图。本检查不是完整 SVG 安全审计，也不保证所有 SVG 特性都兼容 PowerPoint。
- 正式交付使用 `LAYOUT_WIDE` 或宽高比为 16:9 的 `CUSTOM`。底层草稿模式保留 `LAYOUT_4X3` 和其他自定义画布用于工程测试，但本工作流不接受它们的单页预览或正式交付。
- 表格禁用自动分页，避免意外增加页面；内容放不下需拆页。仍需渲染检查溢出。

```json
{"assets": [{"path": "05_reconstruction/rasters/decoration.png", "sha256": "文件实际的64位小写SHA256", "sourceId": "GEN-001"}]}
```

从已批准预览抠取复杂装饰区域时，优先保留透明通道：

```powershell
python <skill>/shared/scripts/crop_asset.py <project> `
  04_full-preview/slides/S01.png 05_reconstruction/cutouts/decor-001.png `
  --source-id RECON-001 --x .72 --y .18 --width .22 --height .45 `
  --alpha-mode keep --manifest 05_reconstruction/assets.json `
  --description "从已批准预览重建设计装饰；不含文字、图表和计划图片区域"
```

源图本身有透明通道时用 `--alpha-mode keep`；需要同尺寸灰度蒙版时用 `--alpha-mode mask --alpha-mask <mask.png>`；只有本来就不需要透明背景的普通裁剪才使用默认 `flatten`。蒙版尺寸必须与源图完全一致。矩形裁剪配合蒙版仍然不是任意轮廓分割器，复杂物体需要先用可靠的分割工具生成蒙版，或改用 SVG 重绘。

进入正片的 AI 素材要在阶段 3.2 烘焙透明 PNG，避免 PPTX 里出现方形素材：

```powershell
python <skill>/shared/scripts/cutout_asset.py <project> `
  04_full-preview/assets/GEN-104.png 05_reconstruction/rasters/gen-104.png `
  --source-id RECON-010 --source-asset-id GEN-104 `
  --tolerance 28 --feather 2 `
  --manifest 05_reconstruction/assets.json `
  --description "按已批准预览抠出 AI 素材边缘"

# 只需要几何遮罩时跳过边缘抠图
python <skill>/shared/scripts/cutout_asset.py <project> `
  04_full-preview/assets/GEN-105.png 05_reconstruction/rasters/gen-105.png `
  --source-id RECON-011 --source-asset-id GEN-105 --mask hexagon --no-cutout `
  --manifest 05_reconstruction/assets.json
```

脚本从边框估计背景色、只去掉与边框相连的纯色区域并羽化边缘，输出记录 `sourceAssetId`、抠图参数与 `transparentRatio`。抠图后没有透明像素或几乎整张素材被抹掉时脚本会失败，此时要换素材或改用 `--mask`，不能把方形素材直接放进 PPTX。

```powershell
node <skill>/stages/33-build/scripts/build_pptx.js <project> --python <python> --mode draft
python <skill>/stages/33-build/scripts/validate_project.py <project> --mode draft
node <skill>/stages/33-build/scripts/build_pptx.js <project> --python <python> --mode release
```

`draft` 不要求批准，但必须满足规格和文件结构；`release` 构建要求阶段 1.1 至 3.2 完成且版本有效。输出仍须在渲染审阅后才能正式交付。旧 PPTX 及相关记录保存在 `07_delivery/history/`；写新文件前先在构建目录生成临时文件，再替换输出。程序不是多文件事务，不要同时构建同一项目。

组装时必须用上生成的三张大图：封面页插标题图 `hero-image`、目录页插目录图 `toc-image`、每个内容页／致谢页用背景图 `content-background` 作整页背景（`transparency = 100 - opacity × 100`）；`validate_project.py --mode release` 与 `complete 3.3` 会逐页核对。

进度条按原生对象重建：每段的标题文本框标 `origin: "progress"`，文字逐字取自 `content.json` 的 `sections`；这类文本不属于页面文案，不写进 `content.json` 的 `texts`，发布校验会单独与 `sections` 比对。

## 渲染、审阅与交付

```powershell
& <skill>/stages/33-build/scripts/render_powerpoint.ps1 -ProjectDir <project>
# 需要投影备份时加 -Pdf：同时导出 07_delivery/deck.pdf，并在渲染清单记录 pdf_path 与 pdf_sha256
& <skill>/stages/33-build/scripts/render_powerpoint.ps1 -ProjectDir <project> -Pdf
python <skill>/stages/33-build/scripts/prepare_review.py <project>
python <skill>/stages/33-build/scripts/prepare_review.py <project>
python <skill>/stages/33-build/scripts/validate_project.py <project> --mode release --output <project>/07_delivery/validation.json
python <skill>/shared/scripts/workflow.py <project> complete 3.3
```

当前已提供 Windows PowerPoint 渲染器，不启动可见演示窗口。其他平台可使用可靠渲染器并按相同字段记录 `render-manifest.json`，但跨平台适配未实现和验证。

### 成品位置美化

生成 PPTX 后必须渲染并逐页评审画面美观度；若布局不够美观，可自由调整各元素的位置、对齐、间距、分区与叠放关系，不受已批准预览的精确坐标限制，也无需为这类位置美化再次询问用户。保持最终文案、数据、图片身份与来源、元素完整性、可编辑性和已确认风格；图注随对应图片移动，箭头保持原逻辑关系，背景仍覆盖整页，导航仍符合页型与小节要求。调整后不得越界、遮挡或产生不合理重叠。

保留已批准预览、设计稿与 image-plan.json 作为原始基线，不为位置美化重写它们或重新启动阶段 2.2。最终位置写入 06_build/deck-spec.json：meta.layoutAdjustmentAuthorization 记录用户原话或本工作流第 28 条授权，每个移动元素写 layoutAdjustment（from 为首次调整前的英寸 x／y，需要改叠放关系时同时记录原 z；reason 写具体美化原因），新位置与层级使用元素自身的 x／y／z。多轮调整继续保留同一原始起点。计划图片的位置和层级可按该记录调整，但其 w／h、sourceId、path、fit、focal、crop、altText 与已批准计划保持一致；边缘显示裁切可按特殊分块要求调整 boundaryMask，须在 layoutAdjustment.from.boundaryMask 保留初始轮廓（原来没有则为 null），并记录原因与规则 29 或用户授权。

记录位置美化与预览的差异，不把它们当成未经批准的偏离。若 preview_match 为 false，在 qa-review.json 的 deviations 中按页记录 type: layout_adjustment、原因、调整前后位置与当前对照图证据，approved_by 引用用户既有授权或本工作流第 28 条，approved_at 写授权依据的记录时间；不得伪造用户逐项确认。实际逐页审阅人及审阅时间仍如实填写。修改构建规格后重新构建、渲染、生成对照图并审阅当前版本，旧审阅不能直接复用。

**不做自动逐像素比对**：AI 生成的整页预览与原生重建的成品不可能逐像素一致，自动比对会大量误判。改为逐页人工对照：`prepare_review.py` 生成"已批准预览 vs PPTX 渲染"的逐页对照图与总览，对照检查版面、色块、图片、装饰与文字排布，并逐个确认计划图片区域已经填入登记原件；差异记进 `qa-review.json` 的 `deviations`／`notes`，未获批准的差异不得交付。

`prepare_review.py` 先验证预览批准与渲染版本，再生成总览、预览与渲染的逐页对照图和默认全部未通过的 `qa-review.json`（不再生成 `visual-match.json`，也不自动比对）。它不会自动批准页面。阶段 3.3 同时评审实际成品美观度；授权的位置美化按本节记录，不能因未逐坐标复现预览而阻止优化。填写真实审阅人、ISO 时间，并逐项设置 `visual/content/photos/editability/preview_match`；未检查的项保持 false，不能批量填 true 冒充审阅。每次重新构建或渲染后旧审阅失效。

正式校验覆盖规格类型、页面关系、XML、内容类型、页数、画布、原生文本、图片/表格/图表数量、对象编号、输入版本、审阅清单和 QA 哈希链。它不证明叙事质量、事实真实性、阅读顺序、无障碍完整性或所有 Office 实现的兼容性；这些不属于阶段 3.3 的交付门禁。`qa-report.md` 应报告已检查项、工具版本、已批准偏差和逐页对照检查结果。

## 回归测试

运行 `python <skill>/tests/test_workflow.py --node <node>`。测试在临时目录中使用合成资料和模拟确认，不调用真实生图、不代表用户真实批准。测试覆盖结构和工作流约束；端到端视觉质量需要真实项目验证。

## 完整预览的原图插入与批准顺序

**阶段 2.2 的强制顺序：AI 生成整页底稿 → 本地插入全部登记原图 → 逐页实际查看插入后的完整预览 → `await 2.2` 等待用户批准。停机点在原图插入并检查之后；只有占位块的完整预览不得提交批准。** 阶段 2.1 仍用占位块确认设计方向。原图在本地按图片计划插入，使用 `contain` 等比保留全图；采用 `boundaryMask` 时只裁切显示边缘，关键主体与信息完整，不拉伸；不得让 AI 重画事实图。保留 AI 原始输出及其生成账本不变，最终预览与原始输出分别登记路径和哈希。

阶段 2.2 的 `previews.json` 中，`file`／`sha256` 指向插入原图后的最终预览，`providerFile`／`providerSha256` 指向不可覆盖的 AI 原始页并与账本一致，`originals` 逐张记录 `imageId`、`sourceId`、`path`、`sha256`、`box`、`fit: contain`（可选 `background`）；无计划图片页也登记 `originals: []`。保留 `placeholders` 记录原始页预留框。原图插入后逐页实际看图，填写 `review`；再次插入会清空旧结论，须复看。`await 2.2`、`approve preview` 与 `complete 2.2` 均检查插入记录、原图身份及哈希、实际合成像素与图片计划；批准记录同时绑定最终预览、AI 原始页和原图文件。这里的像素验证只检查确定性的本地插图，不用于比较 AI 预览与原生 PPTX 的视觉质量。

执行：`python <skill>/shared/scripts/preview_originals.py <project>`。先完善图片计划并生成预览清单，再运行本地插图脚本；它处理全部页面，保留 provider 输出与账本，重置插入后的逐页审阅结论。修订设计用 AI 原始页进行图生图，保留修改谱系；修改结束后重新插入相同登记原图并复看，不将插入后的事实图交给模型重画。阶段 3.1 按已批准最终预览识别图片框与来源；阶段 3.2／3.3 使用同一登记原图作为独立图片对象，不能从扁平预览裁出事实图来替代原件。

## 图片边缘轮廓

元素排布必须贴合特殊分块的形态：弧形分块可让文本框的中心或排列轨迹趋近弧线；也可裁切框体靠近分界的一侧，使轮廓贴合弧线、斜线、波浪或扇区边缘。文本本身保持完整、原生可编辑，放在裁切轮廓内的安全区域。图片也可按分块轮廓适当裁切显示边缘，保留关键主体与信息，不改变登记原件或拉伸图片。同级框保持一致的基础形状、配色与内边距；高度随实际文字适配，靠分界一侧的局部裁切轮廓可随边界变化。文本框的高度要与实际文本高度相匹配，仅保留适量内边距，避免框内大片留白；不要为同级等高而把短文本放入过高的框。

image-plan.json、deck-spec.json 的图片元素与 previews.json 的 originals 可用 boundaryMask：points 为至少三个闭合轮廓顶点（x／y 在 0–1 之间，以图片框为参照，可沿曲线采样），boundary 写分块与贴合边缘，reason 写裁切原因，protectsContent: true 表示已逐页看图确认主体和关键信息完整，不是机检证明。预览原图先 contain 等比放入图片框，再本地应用轮廓；组装时按同一登记原件应用轮廓并保留独立图片对象，原件哈希不变。框体裁切用原生图形或独立 SVG，文字另放原生文本，不使用 boundaryMask 裁切文字。

成品可沿用规则 28／29 或用户既有授权调整轮廓；from.boundaryMask 保存最初轮廓（没有则 null），同时保留初始 x／y，reason 说明排版原因。不得借此改换图片来源、矩形 crop、fit 或计划尺寸。重新渲染审阅当前版本。

## 背景与文本框底色协调

背景色与文本框填充色（框体底色，不是描边色）应有适度色差，能区分层次但避免强烈反差；优先采用协调的邻近色或轻微明度变化。描边色单独说明，不能用边框色差代替填充色差。文字与框底仍须清晰可读。设计和提示词写清填充与背景的柔和层次关系；逐页看图检查实际落地，纹理背景以框所在区域的可见底色为准。
