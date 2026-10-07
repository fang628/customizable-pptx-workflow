# 执行与验收约定

本文件用于实际运行阶段工具。命令中的 `<skill>`、`<project>`、`<python>`、`<node>`、`<adapter-script>` 均替换为实际路径，含空格时加引号。PowerShell 调用带引号的可执行路径时，在前面加 `&`。所有 JSON 均使用 UTF-8。

阶段交接、原始底图与页面预览的区别、文字效果及修改退回范围，统一见[阶段边界与返工路由](artifact-contract.md#阶段边界与返工路由)。

## 生图提示词的禁写信息

提示词十二项结构、内部编号隔离、禁写几何、参考图与返工要求统一见[生图提示词口径](../stages/13-design/references/gen-prompt-scope.md)；本文件只记录当前阶段的操作。

## 规范库索引（按步骤）

规范库按步骤分段：**每开始一个步骤，先读一遍该步骤在索引里列出的章节**（再动手；跨越步骤时重读对应章节，不要凭记忆）。本文件与 [共享工件约定](artifact-contract.md) 是同一套规范库的两部分。

### 三个必读时点

以下要求适用于首次执行、返工和中断恢复。每次读取对应文件的当前版本，不凭记忆或只沿用上一阶段的概括。

1. **每个阶段开始前**：先读该阶段 `SKILL.md`，再读下表为该阶段列出的操作与工件章节；涉及内容或视觉决策时，同时读 [设计判断与检查提示](design-principles.md)及[信息密度与文字配色](content-density-and-text-color.md)。
2. **每轮编写或修订设计稿前**：重新读取阶段 1.3 的设计稿要求、[设计稿模板](../stages/13-design/assets/design-spec.md)、统一设计判断、信息密度与文字配色、中文排版，以及本轮实际采用的风格、页型与分块参考章节；同时核对最新需求和已有设计稿。即使已经完成阶段入口读取，也要在开始本轮写稿前完成这次对应规范复核。
3. **每轮编写或修订生图提示词前**：重新读取当前生成阶段的任务要求、比例与素材契约，以及本轮素材类型对应的提示词规范。阶段 1.2／1.3 的独立素材读本文件《独立素材生图任务》、AI 素材证据链和实际采用的素材参考；阶段 2.1／2.2 的整页预览读[生图提示词口径](../stages/13-design/references/gen-prompt-scope.md)、统一设计判断及相关页型／分块章节。同时核对当前页的最新定稿文案、图片计划和已确认风格；图生图返工同样执行。

只读取本阶段、本轮任务涉及的章节，不要求每次通读整套规范。读取后再编写，编写完成再运行对应自检；**脚本自检通过不能替代编写前阅读规范**。用户修改需求、设计稿或规范后，开始下一轮编写前重新读取受影响章节。

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

阶段与步骤的对应关系见[工作流总览](../SKILL.md)（0–7步）；本文件只写执行命令与验收口径。

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
      "page_id": "S01",
      "prompt": "封面整页预览：\n- **简约要求**：简约仅针对文本框：色块干净、边缘清楚、框内装饰克制；封面、目录和内容页三类底图保留原有主体、层次与细节，复杂底图不做简约化。\n- **紧密排版要求**：分组紧凑有序，减少无用途留白，给文字足够宽度与空间，不以缩小正文换取松散构图。\n- **创意要求**：通过本页实际选定的分区组合、图文呼应或主题结构体现创意，具体做法在下方排版树中展开；不靠特效堆叠或挤压文字实现。\n- **可读性要求**：文字层级清楚、对比充分，正文空间充足；复杂底图通过干净框底和位置安排保障阅读，不为构图或装饰缩小文字。\n- **视觉关系要求**：分组、箭头及图文对应准确表达真实内容关系，阅读顺序明确；不为创意制造错误因果或错误归属。\n- **原图保真要求**：事实照片和数据图不交给模型重画，不拉伸、不替换为近似图；本地等比插入并保留关键主体、坐标轴、图例和单位。无事实原图时说明不适用，底图仍保留已确认主体与细节。\n- **比例要求**：16:9 画布（1920×1080）。\n- **内容要求**：……\n- **排版要求**：按设计稿展开实际分块。\n  - **宏观分块**：主体区域。\n    - **微观子分块**：按实际空间关系展开。\n      - **文字及文本框／图片／装饰**：写各对象实际内容、样式和位置关系。\n- **底图与配图要求**：在已确认原底图上构建，保留主题主体，说明文字与图形关系，不画图片占位框。\n- **风格要求**：主色 #2F5D62，背景与装饰用与所给大图相近的颜色（同一套配色）。\n- **进度条要求**：无进度条。",
      "model": "gpt-image-2",
      "size": "1920x1080",
      "asset_mode": "strict",
      "output": "03_concepts/assets/GEN-001.png",
      "max_attempts": 4,
      "intended_use": "S01 的整页预览（按设计稿 S01 的分块、文字层级与图片位生成）",
      "factual_boundary": "整页预览为 AI 生成示意，不代表真实人物、地点、标识或数据"
    }
  ]
}
```

阶段 2.2 的任务字段相同，但输出根目录改为 `04_full-preview/assets/`，且每个任务对应 `content.json` 里的一页、必须覆盖全部页面。`asset_id` 在所有生图阶段间保持唯一，同一素材在同一页只登记一次使用。整页预览任务的任务元数据必须绑定页面，提示词只写该页设计稿的内容描述；`references` 可以复用本项目的既有产物（如更早的预览），引用外部材料时只能列出已登记且获准上传的材料。

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

阶段2.1／2.2整页的 `asset_mode` 只使用 `strict`，size默认1920x1080或其他精确16:9尺寸；生成实际原图非16:9就退回，保留失败来源与比例，不补边、不裁切修正。仅精确16:9原图等比缩放为1920x1080。以下模式用于阶段1.2／1.3独立素材：

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

按 PPT 要求从已登记材料里选出上屏文字与图片，再按三种设计方向（`styleId` a/b/c）各生成一组候选图片（封面大图、内容页背景底图，有目录页时每个方向各多一张，致谢页复用背景底图），**候选图片统一 16:9（1920×1080）横版，封面大图／目录页大图／背景底图的提示词里要写明 16:9**；最后把文字内容与候选图片编号按叙述顺序写成 `02_design/content-plan.md`（Markdown分级、同级文字同层，真实并列逐段列为子列表，避免无关系堆砌，每张图片配一句说明）。做法见[内容与素材清单](../stages/12-content/SKILL.md)。

```powershell
python <skill>/stages/21-concepts/scripts/run_generation.py <project> --stage content --execute
python <skill>/shared/scripts/workflow.py <project> complete 1.2
```

- 任务与账本：`02_design/generation-jobs.json`、`02_design/generation-ledger.json`；候选图片输出 `02_design/generated-assets/GEN-###.png`，登记到 `02_design/generated-assets.json`；
- `complete 1.2` 会核对：清单存在且分级、覆盖全部候选与计划图片编号、三种设计方向（a/b/c）各至少一张 `hero-image` 与一张 `content-background`、每张候选图片可读／哈希一致／横版／有用途说明、大图提示词写明了 16:9、生图任务与账本一致。

### 阶段 1.3 设计稿与复核

设计稿逐页使用[设计稿模板](../stages/13-design/assets/design-spec.md)的四项结构：页面信息、页面目的与阅读逻辑、嵌套排版树、本页视觉差异与特殊说明。最终文案从content-plan.md精简后，只在树中对应文字对象下记录一次，并同步content.json；同处记录角色、字号pt或继承角色、文本框形状、对齐及粗略空间关系，图片和装饰嵌套到实际所属分块。来源与路径引用图片意图总表、claim-map.json，不抄多份清单；共用风格集中在《全篇视觉约定》，逐页只写例外。不记录坐标或精确框尺寸。complete 1.3支持新树结构和旧字段结构，新结构检查页面覆盖、四项信息、嵌套列表及各文字对象的文案、框形与字号声明；实际空间关系和元素完整性仍需逐页复核。特殊分块比例与每页有图等既有要求继续执行。同类内容可以复用结构，变化来自内容关系。全篇跨页承接集中写入《全篇叙述逻辑链》，逐页不再重复该表。

```powershell
python <skill>/shared/scripts/workflow.py <project> await 1.3 --notes "..."
python <skill>/shared/scripts/workflow.py <project> complete 1.3
```

设计稿写完后必须**停机**等用户复核：用户可以直接改 `02_design/design-spec.md`；改完要重新 `await 1.3`／`complete 1.3`，在此之前不得生成任何整页预览（1.3 完成后设计稿再被改动会让 1.3 变成 stale，后续阶段的 `complete` 会拒绝）。
### 阶段 2.1／2.2 分块参考图

生成页面预览时不提供分块参考图，也不要求复制分块图或建立 split-references.json；参考库仅供设计阶段本地查阅。分区形态和全部文本框／图形元素改由提示词详细说明，具体口径见生图提示词规范。风格参考、获准材料及图生图返工原页仍按各自用途提供，不能与分块示意图混淆。

整页预览没有骨架图中转稿。提示词使用Markdown十二项顶层列表，排版要求按宏观分块→微观子分块→更深子分块→所属文字及文本框、图片、装饰逐层嵌套，完整文案放在实际所属元素下；写法见[嵌套分块树](../stages/13-design/references/gen-prompt-scope.md#markdown-嵌套列表与实际分块树)。按当前页设计稿，把每个文本框、主视觉、图片占位框、图标、箭头、装饰和分区色块的形态、位置关系、样式与叠放逐项提取进提示词；不写内部编号、具体坐标、文本框尺寸或字号。详细字段统一见[全部文本框与图形元素的逐项说明](../stages/13-design/references/gen-prompt-scope.md#全部文本框与图形元素的逐项说明)。验收不再要求分块图清单、复制文件或分块图任务引用，仍核对实际设计形态、图片比例和完整生成证据。

### 阶段 1.3 补充生成素材

设计稿阶段可以在用户允许生图后，补充装饰、纹理、抽象背景、主题纹样、贴合主题的简单图标和具象的说明性插画。使用同一份已确认配置与适配器，先 dry-run 核查供应商、模型、脚本、凭据就绪状态和上传许可，再显式执行。AI 只生成无文字视觉层，不生成需要准确表达的文字、数字或图表；现实风格插画必须标注为“AI 生成示意图”，不得伪装成真实照片、真实人物或实验证据。

生成后把原始返回图与规范化图存入 `02_design/generated-assets/`，把实际路径、SHA-256、供应商、模型、请求编号、提示词哈希、种子、`intendedUse` 和 `factualBoundary` 登记到 `02_design/generated-assets.json`。禁止用 Pillow、HTML、CSS 或本地绘图生成候选后伪装成 API 结果。设计阶段素材是后续风格方向的可追溯参考；候选可作为已登记的风格参考复用，不必仅为复用而重新生图；2.1／2.2整页任务仍建立本阶段生成证据。候选作为独立计划图片采用时，沿用原GEN编号并写进图片意图／图片计划；仅新增或编辑独立素材时登记新任务及新GEN编号，保留原来源关系。

## 整页预览生成与组装

阶段 2.1／2.2 的整页生成与十二项提示词结构统一见[生图提示词口径](../stages/13-design/references/gen-prompt-scope.md)。元素描述见上节，输出尺寸见 preview-contract.md；提示词和账本按下方命令登记。2.2 先插入全部登记原图、逐页实看，再提交批准；配色距离仅输出设计复看提示。

阶段 2.1 为 A/B/C 分别写 `03_concepts/option-a|b|c/preview.json`；阶段 2.2 写覆盖全部定稿页面的 `04_full-preview/previews.json`（含 `styleConstraints`）。字段必须符合 `shared/schemas/preview-pages.schema.json`，每页写明 `promptSummary`（这一页用了设计稿的哪些分块、文字层级与图片位），页面编号只写入任务元数据，不进入提示词。

## 逐页视觉检查与回调

整页预览由 AI 生成后没有本地逐元素机检：**每轮生成后必须逐页实际打开 PNG 看图**，逐页核对——文字是否排进设计稿标注的框位、层级与留白、重心与对齐、主题贴合度、进度条是否合规、跨页是否统一；另外**目测**每个图片占位块的宽高比是否与计划插入的原件比例一致（这是看图时的粗略检查、不是机检：`complete`只核对清单声明的框与计划、原件比例是否在容差内；实际画面框位、比例和可读性仍由逐页看图确认）；明显不一致就用图生图重画占位块，或修正清单里的占位框后复看。发现问题就回调：改提示词重生成、用 `edit_source` 局部编辑，或用 `crop_asset.py`／`cutout_asset.py` 调整裁切与抠图，再把问题与调整记入 `03_concepts/concept-review.md` 或 `04_full-preview/generation-log.md`。

```powershell
python <skill>/shared/scripts/workflow.py <project> await 2.1 --notes "..."
python <skill>/shared/scripts/workflow.py <project> await 2.2 --notes "..."
```

阶段 3.3 还须评审实际成品美观度，可按成品位置美化授权优化各元素位置，重新构建、渲染与审阅。项目内写入由根目录 `workflow.lock` 串行化：`workflow.py`、`run_generation.py` 等命令先取锁，锁存在时直接报错；同一项目不要并行运行生成器或构建，锁超过 10 分钟视为陈旧并被下一个进程接管。

## 重建与构建

参照 [deck 规格](schemas/deck.schema.json) 写 `06_build/deck-spec.json`。原生图形、SVG 和位图仍按阶段 3.2 分流；没有自动从整页位图还原任意矢量的工具。阶段 3.1 先逐页写出 `05_reconstruction/element-inventory.md`（非文字元素＋大致位置＋计划的分离方式；计划图片按已插入原图的框与登记来源单独记录，不从扁平预览拆抠事实图），再写 `slide-elements.md`；阶段 3.2 按清单**逐个**还原：形状或颜色复杂用 AI 抠图／SVG 重绘，形状与颜色简单用 PPT 原生元素组装，不得遗漏或简化。阶段 3.3 按已批准设计重建背景，可采用原生纯色、渐变或实际采用的登记图像。

- 坐标 `x,y,w,h` 使用英寸；归一化值转换为 `x*画布宽`、`y*画布高`、`w*画布宽`、`h*画布高`。
- `z` 从小到大绘制，相同层级保持原数组顺序；元素 ID 写入 PowerPoint 对象名。
- `origin` 缺省为 `planned`；`planned` 图片必须与 `image-plan.json` 的编号、来源、路径、位置和适配参数一致，其他页型2.1概念图保留占位，2.2完整预览必须插入全部登记原件再批准，正式PPTX在3.3独立插入同一原件；成品美化的位置与层级可按本节授权记录调整，原图片计划保留为基线。`origin: "reconstruction"` 的图片、SVG 和局部抠图不由图片计划约束，作为独立对象插入。
- `image.fit` 为 `contain` 或 `cover`，默认前者；`cover` 可用 `focal:{"x":0.5,"y":0.5}` 指定原图归一化焦点。生成裁剪图片保留来源和嵌入字节哈希。局部抠图透明 PNG 必须设置 `preserveAlpha: true`，否则构建器会按背景色展平透明通道。AI 背景底图在预览里用 `background.asset.opacity`（可参考 0.10–0.35，以实际可读性判断），在 deck-spec 里换算成 `transparency = 100 - opacity × 100`（例如 opacity 0.25 → `transparency: 75`），构建器会原样传给 PptxGenJS；底图必须是弱对比的内容页背景，不要把强反差照片铺满整页。
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

组装时按已批准设计重建背景与实际采用的素材；候选大图仅作候选和参考，不强制上屏。纯色、渐变和登记图像均可用作背景，采用项的身份、来源及完整性仍由图片计划与重建清单核验。

进度条按原生对象重建：每段的标题文本框标 `origin: "progress"`，文字逐字取自 `content.json` 的 `sections`；这类文本不属于页面文案，不写进 `content.json` 的 `texts`，发布校验会单独与 `sections` 比对。

## 渲染、审阅与交付

```powershell
& <skill>/stages/33-build/scripts/render_powerpoint.ps1 -ProjectDir <project>
# 需要投影备份时加 -Pdf：同时导出 07_delivery/deck.pdf，并在渲染清单记录 pdf_path 与 pdf_sha256
& <skill>/stages/33-build/scripts/render_powerpoint.ps1 -ProjectDir <project> -Pdf
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

2.2必须先本地插入全部登记原图、逐页实际看图再提交批准；其他页型2.1仍保留占位；封面／目录在原底图上构建，不要求图片占位框，见[原底图构建契约](preview-contract.md#封面与目录的原底图构建)。provider原始页、最终预览、originals与哈希字段及插图命令统一见[原图插入与批准契约](preview-contract.md#完整预览的原图插入与批准顺序)。修订使用provider底稿，完成后重新插图复看，不交给模型重画事实图。

## 图片边缘轮廓

采用特殊分块时，可按阅读需要让元素贴合其形态：弧形分块可让文本框的中心或排列轨迹趋近弧线；也可裁切框体靠近分界的一侧，使轮廓贴合弧线、斜线、波浪或扇区边缘。文本本身保持完整、原生可编辑，放在裁切轮廓内的安全区域。图片也可按分块轮廓适当裁切显示边缘，保留关键主体与信息，不改变登记原件或拉伸图片。同级框保持一致的基础形状、配色与内边距；高度随实际文字适配，靠分界一侧的局部裁切轮廓可随边界变化。文本框的高度要与实际文本高度相匹配，仅保留适量内边距，避免框内大片留白；通常避免短文本高框；同尺度对比卡片可等高。

image-plan.json、deck-spec.json 的图片元素与 previews.json 的 originals 可用 boundaryMask：points 为至少三个闭合轮廓顶点（x／y 在 0–1 之间，以图片框为参照，可沿曲线采样），boundary 写分块与贴合边缘，reason 写裁切原因，protectsContent: true 表示已逐页看图确认主体和关键信息完整，不是机检证明。预览原图先 contain 等比放入图片框，再本地应用轮廓；组装时按同一登记原件应用轮廓并保留独立图片对象，原件哈希不变。框体裁切用原生图形或独立 SVG，文字另放原生文本，不使用 boundaryMask 裁切文字。

成品可沿用规则 28／29 或用户既有授权调整轮廓；from.boundaryMask 保存最初轮廓（没有则 null），同时保留初始 x／y，reason 说明排版原因。不得借此改换图片来源、矩形 crop、fit 或计划尺寸。重新渲染审阅当前版本。

## 背景与文本框底色协调

底色层级与文字可读性按[设计判断与检查提示](design-principles.md)；本项目分别记录填充色、描边色和实际采用的对比关系。
