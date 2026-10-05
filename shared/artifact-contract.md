# 共享工件约定

所有子 skill 共用同一个项目根目录与以下阶段目录。保留英文目录名、字段名和状态枚举，保证脚本兼容；面向用户的说明和模板正文使用中文。

```text
project/
|-- workflow-state.json
|-- 00_intake/
|   |-- project-brief.md
|   |-- ai-image-config.json
|   |-- font-report.json
|   |-- requirements-approval.json
|   `-- materials/{reports,papers,photos,promo,brand,data,other}/
|-- 01_inventory/{material-inventory.md,materials.json}
|-- 02_design/
|   |-- design-spec.md
|   |-- content.json
|   |-- claim-map.json
|   |-- generated-assets.json
|   |-- generation-prompts.md
|   |-- generated-assets/GEN-###.png
|   |-- split-references/{diagonal-cut,arc,...}/{*.png}
|   |-- split-references.json
|   |-- image-intent-plan.json
|   `-- image-plan.json
|-- 03_concepts/
|   |-- option-a/{S01.png,S02.png,preview.json}
|   |-- option-b/{S01.png,S02.png,preview.json}
|   |-- option-c/{S01.png,S02.png,preview.json}
|   |-- assets/GEN-###.png
|   |-- raw/**/*.png
|   |-- prompts/
|   |-- generation-jobs.json
|   |-- generation-ledger.json
|   |-- preflight.json
|   `-- approval.json
|-- 04_full-preview/
|   |-- previews.json
|   |-- assets/GEN-###.png
|   |-- raw/**/*.png
|   |-- slides/{S01.png,S02.png,...}
|   |-- generation-jobs.json
|   |-- generation-ledger.json
|   |-- generation-log.md
|   |-- preflight.json
|   `-- approval.json
|-- 05_reconstruction/{photos,vectors,rasters,cutouts/,assets.json}
|-- 06_build/{deck-spec.json,build-log.md}
`-- 07_delivery/{deck.pptx,deck.pdf,preview/,review/,review-manifest.json,qa-review.json,qa-report.md}
```

## 生图提示词的禁写信息

阶段 2.1／2.2 的新生成与图生图修订提示词，**禁止写文本框的具体尺寸、字号、元素具体坐标**：不写固定宽高、数值尺寸、字号指令或 x／y、像素位置、归一化坐标。允许并必须说明文本框高度贴合文本、仅保留适量内边距、避免框内大片留白；允许说明顺着分块边界排列或裁切显示边缘。保留分区与阅读顺序、文字内容和语义角色、框形与颜色、图片位比例、风格、导航及逻辑关系。整页画布 16:9（1920×1080）与图片位宽高比继续保留。具体坐标、文本框尺寸、字号和裁切轮廓点只留在本地设计稿、图片计划和重建规格中；不得将含这些信息的原始设计稿全文拼入提示词。

## 阶段状态

`workflow-state.json` 使用 `not_started`（未开始）、`in_progress`（进行中）、`awaiting_user`（等待用户）、`complete`（完成）或 `blocked`（受阻）。必需工件存在且满足阶段验收条件，才能标记为 `complete`。

阶段完成由共享 `workflow.py complete` 写入产物 SHA-256。批准记录分别位于 `00_intake/requirements-approval.json`、`03_concepts/approval.json` 和 `04_full-preview/approval.json`。设计稿写完后阶段 1.3 必须停在 `awaiting_user`，把 `02_design/design-spec.md` 交给用户复核或直接修改；重新读取该文件、同步受影响的 JSON 并记录复核原话后才能完成 1.3。完整预览全部生成后阶段 2.2 必须停在 `awaiting_user`，只有记录真实用户确认后才能完成，之后才允许进入阶段 3.1。阶段版本变化后原完成记录失效，不能只依据状态文本继续交付。执行方式见[执行与验收约定](operations.md)。

## 目录与进度条

阶段 1.1 必须确认 `include_toc` 与 `progress_bar`。目录页默认需要：需要时 `content.json` 第二页必须是唯一的 `toc`；不需要时不得出现 `toc`。标题页始终第一页。顶部进度条默认需要，表示“在除标题页和目录页外的每一页上方添加进度条”：它必须排除 `title`，存在目录页时还必须排除 `toc`，存在致谢页时必须排除 `thanks`。`design-spec.md` 必须分别保留 `## 目录要求` 和 `## 顶部进度条要求`，后者是独立设计要求，不得并入普通版式说明。

进度条是粗条分段导航，不是细线游标：条内逐段写出全部小节标题，文字取自 `content.json` 的 `sections` 并与目录页小节标题逐字一致；当前小节标题放大或加粗，当前分段与整条轨道、与已完成分段形成明显色差。`sections` 是进度条标题与分段的唯一来源，启用进度条时必须覆盖全部合格页面，每页属于且只属于一个小节。


- `background`：本地基础底色；本工作流正式交付仍按页型嵌入规定的 AI 基础大图，不以底色替代大图。内容页／致谢页用作背景底图时使用 `content-background`：弱对比（叠加不透明度后全图反差 ≤35%，推荐 10%–22%）、透明度取 0.10–0.35，并从课题语义提炼、贴合主题，不得压住正文与证据；
- `asset`：独立 AI 素材，可 `contain/cover`、设置焦点、裁剪、旋转、调节透明度、几何遮罩，以及三种插入方式：`edge.mode = "cutout"` 抠出主体不留背景、`edge.mode = "feather"` 羽化边缘保留背景叠入、`edge.mode = "none"` 常规插入；页内非满幅、非通栏的素材必须抠边、羽化或套遮罩，禁止硬边方形素材直接入画；
- `image`：`image-plan.json` 规定的计划图片；路径存在时嵌入登记原件，缺失时绘制占位框；
- `shape`：矩形、圆、椭圆、胶囊形、气泡形、三角形、平行四边形、梯形、六边形、V 形、菱形、粗箭头、自定义多边形，以及线条 `line`、线阵 `lines`、圆弧 `arc`、圆环 `ring`、点阵 `dots`、分色色块 `split-block` 等装饰词汇元素；
- `clip`：把元素（例如文本框内的小圆环、点阵、线阵、色块）裁剪到另一个元素的边界内，保证小尺寸元素不超出文本框；
- `svg`：精确保留的 SVG 线稿、图标或依据 AI 素材重绘的独立图形；
- `text`：只允许来自 `content.json` 的逐字文案；
- `progress`：按 `content.json` 的 `sections` 计算的粗分段顶部进度条，条内写全部小节标题并突出当前小节。

每张整页预览固定输出 1920×1080 PNG（`preview_images.normalize` 规范化），其生成证据保存在该阶段的 `generation-jobs.json` 与 `generation-ledger.json`。

## AI 素材证据链

AI 生图证据链从阶段 1.1 的 `00_intake/ai-image-config.json` 开始。配置记录用户确认的供应商、模型、凭据环境变量、凭据就绪状态、参考图上传许可、参考图上限、适配脚本和参数映射，不保存密钥值。生图不设次数预算：旧配置里的 `stageBudgets` 已废弃并被脚本忽略，需要更多候选或重试时直接追加任务即可。

阶段 2.1、2.2 分别以 `03_concepts/generation-jobs.json` 与 `04_full-preview/generation-jobs.json` 定义任务，以同名 `generation-ledger.json` 记录真实 API 调用。所有任务输出必须是稳定路径 `03_concepts/assets/GEN-###.png` 或 `04_full-preview/assets/GEN-###.png`，不得以页面编号或整页方案图作为输出。每个成功记录必须包含供应商、实际模型、唯一 `request_id`、提示词哈希、适配脚本哈希、原始生成图路径与哈希、规范化输出路径与哈希、规范化尺寸、尝试次数和状态。

被退回或需要修改的素材／整页预览**一律用图生图改原图**：素材用 `edit_source` 指向被退回的那张本地图、整页预览把被退回的页图放进任务 `references`，提示词逐条写明保留项与调整要求，在该图基础上重绘，不得重新文生图从头生成、也不得另起无来源关系的编号绕过原图。允许对已生成的素材做生图编辑：任务用 `edit_source` 指明被编辑素材的 `assetId` 与本阶段稳定路径，编辑结果仍输出为新的 `GEN-###`。被编辑素材的路径与 SHA-256 写入账本记录，并计入参考图上传许可与数量上限；被编辑素材本身保留，不得覆盖。

AI 只生成可独立组合的素材：贴合主题的简单图标、抽象纹理、背景场、装饰色块、平面纹样、可裁切的主题图形、具象的说明性现实风格插画、封面用的整体大图，以及内容页的弱对比背景底图（`content-background`）。除封面大图、目录页大图与背景底图外，也可以生成现实 3D 风格的示意图并抠掉背景（`illustrative-scene` + `cutout` 或几何遮罩）作为页面元素使用，其内容必须与同页文字表达同步。通常使用 `asset_mode: "preserve"` 保留供应商原始尺寸；只有任务明确声明 `asset_size` 时才按 `pad` 或 `crop` 规范化。AI 输出不得包含准确文案、数字、图表、图例、单位或标识，也不得伪造真实人物、地点、事件、证书、截图或实验证据；现实风格插画必须标注为“AI 生成示意图”，其 `factual_boundary` 与替代文本都要写明示意边界，且不得占用计划图片区域。封面大图（`hero-image`）与目录页大图（`toc-image`）的提示词要写明**主体偏右、左侧干净**：主体放在右半幅且完整，左侧约 40%–50% 只留柔和背景／渐变，方便左侧排标题与要点文字。

预览中做过 `cutout` 或几何遮罩的 AI 素材，在阶段 3.2 用 `shared/scripts/cutout_asset.py` 烘焙为透明 PNG：输出写入 `05_reconstruction/rasters/`，登记 `RECON-###` 并记录 `sourceAssetId: "GEN-###"`、抠图参数与透明像素比例，阶段 3.3 插入该透明文件。未满幅的方形素材不得直接插入 PPTX。

某阶段组装时发现缺少素材或效果不理想，可以直接追加 `GEN-###` 任务并重新组装；不设次数预算，但不得改用未确认供应商。每个 `GEN-###` 在本阶段内保持全局唯一，同一素材在同一页只登记一次使用；需要多种独立呈现时登记新的素材或后续 `RECON-###` 重绘。

## 图片与重建来源

`origin` 缺省为 `planned`。`planned` 图片是 `image-plan.json` 约束的事实性或计划内容图片：本地预览在路径存在时嵌入该图片，正式 PPTX 在阶段 3.3 按同一路径和适配参数插入；位置可按《成品美化与位置调整》的记录优化。`reconstruction` 是阶段 3.2 为复现已批准预览而准备的 SVG、局部抠图或独立装饰对象，不加入图片计划，不得改变计划图片区域的来源；阶段 3.3 可按成品美化记录调整位置，原 image-plan.json 保留为基线。

两种元素都必须使用稳定 ID 和正确 `sourceId`：计划生成素材保留 `GEN-###`，局部抠图和新登记的重建素材使用 `RECON-###`。本地预览中的 `svg` 元素在阶段 2.1／2.2 使用 `RECON-###` 作为 `sourceId`，可选 `sourceAssetId: "GEN-###"` 说明它依据哪项 AI 素材重绘。

## 编号与来源

- 材料编号：`REPORT-001`、`PAPER-001`、`PHOTO-001`、`PROMO-001`、`BRAND-001`、`DATA-001`、`OTHER-001`。
- 设计阶段生成素材编号：`GEN-001`、`GEN-002` 等；只有非事实性素材可以生成。阶段 1.2 的候选图按设计方向成组（`styleId` 取 `a`/`b`/`c`，与 `option-a/b/c` 对应）：每个方向各有一套封面大图（`hero-image`）与内容页背景底图（`content-background`），有目录页时各有一张 `toc-image`；致谢页复用 `content-background`，不要求 `thanks-image`（历史候选可保留登记，不能替代背景）。
- 阶段 2.1／2.2 独立素材编号：`GEN-###`，在全部阶段间保持唯一，输出路径固定到该阶段 `assets/GEN-###.png`。
- 重建素材编号：`RECON-001`、`RECON-002` 等；用于 SVG、局部抠图和未受图片计划约束的重建素材。
- 页面编号：`S01`、`S02` 等。
- 元素编号：`<页面>-<类型>-<序号>`，例如 `S04-TITLE-01`、`S04-PHOTO-02`。
- 不改变原始文件。记录来源路径与页码或时间位置。设计候选生成素材放入 `02_design/generated-assets/`；进入正片前在阶段 3.2 登记到 `05_reconstruction/assets.json`。裁剪图、处理后的照片、SVG 和新生成的重建素材放入 `05_reconstruction/` 的对应子目录。

## 进度条文本

阶段 3.3 重建顶部进度条时，每段的标题文本框标注 `origin: "progress"`：文字逐字取自 `content.json` 的 `sections`，**不写进 `content.json` 的 `texts`**（`texts` 只放页面文案）。发布校验对 `origin: "progress"` 的文本单独与 `sections` 比对，并检查它只出现在允许的页面；其余 `text` 元素仍与 `content.json` 逐字比对。

## 元素识别与重建

阶段 3.1 的第一步是逐页生成 `05_reconstruction/element-inventory.md`：列出预览里除文字之外的所有元素（**不含计划图片的占位块**；含全部装饰性线条、线阵、点阵、圆环、圆弧、色块、分色、图形、图标、渐变与光影），逐项写明大致位置、服务的文字／文本框／图片与**计划的分离方式**（`ai抠图`／`svg重绘`／`原生组装`），并给出《分离方式汇总》；然后再写详细的 `slide-elements.md`，两份文档的元素要一一对应。阶段 3.2 按清单**逐个**还原：形状或颜色复杂用 AI 抠图或 SVG 重绘，形状与颜色简单用 PPT 原生元素组装，不得遗漏、不得简化，还原后的形状、颜色、渐变与视觉效果必须与已批准预览一致。阶段 3.3 的页面背景只能是该页对应的 AI 大图（标题页 `hero-image`、目录页 `toc-image`、其余页 `content-background`），不能用其他图片充当背景；除背景外其余元素初次位置与已批准预览一致；成品可按下节授权自由调整位置。

## 成品美化与位置调整

生成 PPTX 后必须渲染并逐页评审画面美观度；若布局不够美观，可自由调整各元素的位置、对齐、间距、分区与叠放关系，不受已批准预览的精确坐标限制，也无需为这类位置美化再次询问用户。保持最终文案、数据、图片身份与来源、元素完整性、可编辑性和已确认风格；图注随对应图片移动，箭头保持原逻辑关系，背景仍覆盖整页，导航仍符合页型与小节要求。调整后不得越界、遮挡或产生不合理重叠。

保留已批准预览、设计稿与 image-plan.json 作为原始基线，不为位置美化重写它们或重新启动阶段 2.2。最终位置写入 06_build/deck-spec.json：meta.layoutAdjustmentAuthorization 记录用户原话或本工作流第 28 条授权，每个移动元素写 layoutAdjustment（from 为首次调整前的英寸 x／y，需要改叠放关系时同时记录原 z；reason 写具体美化原因），新位置与层级使用元素自身的 x／y／z。多轮调整继续保留同一原始起点。计划图片的位置和层级可按该记录调整，但其 w／h、sourceId、path、fit、focal、crop、altText 与已批准计划保持一致；边缘显示裁切可按特殊分块要求调整 boundaryMask，须在 layoutAdjustment.from.boundaryMask 保留初始轮廓（原来没有则为 null），并记录原因与规则 29 或用户授权。

记录位置美化与预览的差异，不把它们当成未经批准的偏离。若 preview_match 为 false，在 qa-review.json 的 deviations 中按页记录 type: layout_adjustment、原因、调整前后位置与当前对照图证据，approved_by 引用用户既有授权或本工作流第 28 条，approved_at 写授权依据的记录时间；不得伪造用户逐项确认。实际逐页审阅人及审阅时间仍如实填写。修改构建规格后重新构建、渲染、生成对照图并审阅当前版本，旧审阅不能直接复用。

## 文本框装饰

框内小元素装饰为可选项，可以写「无装饰」；选用时写清类型、颜色与位置，同级并列框保持一致，不遮挡文字。不因无装饰拒绝设计或交付；已批准预览中采用的装饰仍须按元素清单重建。

内容页可按表达需要补充已登记的主题图标或说明性插画；不为填满留白强制补图，补充素材不得替代事实图片或统一背景，采用后写入设计稿与素材清单。

## 可编辑性约定

优先使用原生文本框、形状、表格和图表。照片、截图、纹理和生成插画保留为独立图片对象。复杂装饰可以使用经过验证的 SVG 重绘；仅限装饰、纹理或非文字图形区域时，也可以从已批准预览局部抠图并保留透明通道。SVG 可以独立选中，但内部路径可能需要在 PowerPoint 中转换后才能编辑。不能抠取文字、表格、图表或计划图片区域，也不能为了复现预览而把整页扁平化。

## 生图提示词记录

所有阶段（1.2／1.3／2.1／2.2）的 AI 生图提示词都集中记录在 `02_design/generation-prompts.md`：按阶段分节，每个任务写 id、素材编号、用途、参考图（分块参考图／材料）与提示词全文，生成后补记状态与输出。`complete 1.2／2.1／2.2` 会核对该阶段每个任务都已登记。

## 整页预览与分块参考图

阶段 2.1／2.2 的整页预览**直接按设计稿生成**，没有中间稿：设计稿的《排版分级》与《元素位置与大小》就是排布依据（标题页只给该方向的 AI 大图 `hero-image`＋单页设计稿；其他页按设计稿生成，需要特殊分块的页面把**分块参考图**放进任务的 `references`）。

用到分块参考图的页面（9 种特殊分块：斜切／弧线／扇形／同心圆／波浪／金字塔／圆形放射／左圆右栏／六边形蜂窝；以及不算特殊分块、不计入比例的横带与四宫格），预览任务的 `references` 必须带上对应的**分块参考图**：先运行 `python <skill>/shared/scripts/prepare_split_references.py <project>`，把 `shared/references/splits/` 里的形态样例按分块复制到 `02_design/split-references/<分块>/`、并写出 `02_design/split-references.json`（逐页列出该页用到的参考图）；再把清单里该页的每条路径写进该页预览任务的 `references`——参考图与设计提示词一起交给 AI。参考图只作分区示意（分成哪几块、分界走向），图上的线条不要照抄：预览里弧线保持弧度、斜线保持倾角，不能简化成横平竖直的直线；`complete 2.1／2.2` 会核对清单与设计稿分块方式一致、参考图已复制且已进入该页任务。

在记录批准之前，必须逐页登记整页预览清单（`03_concepts/option-<x>/preview.json` 或 `04_full-preview/previews.json`）：逐页登记 `id`、`file`、`jobId`、`sha256` 与 `promptSummary`（这一页用了设计稿的哪些分块、文字层级与图片位），阶段 2.2 还要写 `styleConstraints`；页面上有计划图片时，还要在 `placeholders` 里逐张写 `imageId` 与该页占位块的 `box`（位置与 `image-plan.json` 一致、比例与登记原件相差不超过 12%；阶段 2.1 只画占位块；阶段 2.2 在批准前插入登记原图并逐页检查，阶段 3.3 使用同一原件组装）。阶段 2.1 清单按预览 PNG 的 SHA-256 与生图账本绑定；阶段 2.2 分别登记最终预览与 AI 原始页的哈希，以 providerSha256 绑定生图账本，并登记实际插入的 originals；`approve concept` 与 `approve preview` 会核对文件存在、页序覆盖、阶段 2.1 的预览哈希／阶段 2.2 的 AI 原始页哈希与账本一致、`promptSummary` 已写、提示词按分点分行写（比例要求／内容要求／排版要求／图片占位框比例／风格要求／进度条要求；生成前自检会核对）、风格点写明与所给 AI 大图相近的配色（同一套配色）且预览与同风格大图的主色相差不能过大、任务提示词写明了页面编号、分块方式／形态（弧线斜线不直线化）、文字的语义角色与逐张图片位比例，特殊分块页的参考图已进入任务，以及占位块的位置、大小与比例（比例看清单里的 `placeholders[].box`，与登记原件相差不超过 12%）；替换任何预览后必须重新生成并登记。阶段 2.1 只核对选中的方案。

## 坐标与画布

正式画布强制为 16:9，尺寸约为 13.333333 × 7.5 英寸。构建规格中的元素坐标使用英寸。最终单页预览严格满足像素宽 × 9 = 像素高 × 16，标准 1920×1080；AI 原始素材是可自由裁切和重绘的独立输入，不受整页比例约束。不得采用近似比例或拉伸图，详见[预览规范](preview-contract.md)。

预览中的坐标采用 1920×1080 归一化 `box` 或像素坐标，与 PPTX 英寸坐标分开保存；图片适配默认 `contain`，填充裁剪须显式指定。元素层级为整数 `z`，构建器按升序绘制。阶段 2.2 的 `image-plan.json` 的 `pixelBox` 必须由 1920×1080 的归一化 `box` 计算，构建规格中的英寸坐标必须与其一致；阶段 1.3 的图片意图不包含这些精确几何字段。文字字号同样分两套单位：预览 `fontSize` 是像素，构建规格 `fontSize` 是磅，同一处文字必须满足**磅值 = 预览像素 ÷ 2**，详见[中文排版与字号规范](../stages/13-design/references/typography-cjk.md)。

## 日志

记录提示词、模型及版本、可用时的随机种子、参考材料编号、输出路径和已知失败。不得在项目文件中保存凭据或私密 API 密钥。
## 图片边缘轮廓

元素排布必须贴合特殊分块的形态：弧形分块可让文本框的中心或排列轨迹趋近弧线；也可裁切框体靠近分界的一侧，使轮廓贴合弧线、斜线、波浪或扇区边缘。文本本身保持完整、原生可编辑，放在裁切轮廓内的安全区域。图片也可按分块轮廓适当裁切显示边缘，保留关键主体与信息，不改变登记原件或拉伸图片。同级框保持一致的基础形状、配色与内边距；高度随实际文字适配，靠分界一侧的局部裁切轮廓可随边界变化。文本框的高度要与实际文本高度相匹配，仅保留适量内边距，避免框内大片留白；不要为同级等高而把短文本放入过高的框。

image-plan.json、deck-spec.json 的图片元素与 previews.json 的 originals 可用 boundaryMask：points 为至少三个闭合轮廓顶点（x／y 在 0–1 之间，以图片框为参照，可沿曲线采样），boundary 写分块与贴合边缘，reason 写裁切原因，protectsContent: true 表示已逐页看图确认主体和关键信息完整，不是机检证明。预览原图先 contain 等比放入图片框，再本地应用轮廓；组装时按同一登记原件应用轮廓并保留独立图片对象，原件哈希不变。框体裁切用原生图形或独立 SVG，文字另放原生文本，不使用 boundaryMask 裁切文字。

成品可沿用规则 28／29 或用户既有授权调整轮廓；from.boundaryMask 保存最初轮廓（没有则 null），同时保留初始 x／y，reason 说明排版原因。不得借此改换图片来源、矩形 crop、fit 或计划尺寸。重新渲染审阅当前版本。

## 背景与文本框底色协调

背景色与文本框填充色（框体底色，不是描边色）应有适度色差，能区分层次但避免强烈反差；优先采用协调的邻近色或轻微明度变化。描边色单独说明，不能用边框色差代替填充色差。文字与框底仍须清晰可读。设计和提示词写清填充与背景的柔和层次关系；逐页看图检查实际落地，纹理背景以框所在区域的可见底色为准。
