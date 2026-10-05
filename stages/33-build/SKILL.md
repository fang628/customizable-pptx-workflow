---
name: 33-build
description: "依据确认后的元素清单与素材，组装、校验、渲染和验收可编辑 PPTX 并交付。用于 pptx-workflow 的阶段 3.3。"
---

# 阶段 3.3：组装与验收

**停机点：无（本阶段是交付终点）。** 组装、校验、渲染与比对必须连续完成；全部阶段 `complete` 后任务才结束。

**开工前先读规范库**：先读[执行与验收约定](../../shared/operations.md)的《规范库索引（按步骤）》里「3.3 组装与交付」一行与它列出的章节，再读[共享工件约定](../../shared/artifact-contract.md)的对应小节；每进入一个新步骤都重读该步骤的章节，不要凭记忆。

等于设计稿与预览里该段文字的字号（预览像素 ÷ 2）；整页预览是 AI 生成的，字号以设计稿的最终文字与字级约定为准，必要时在构建规格里显式记录。

`origin: "reconstruction"` 的 PNG、透明局部抠图和 SVG 来自阶段 3.2，作为独立对象插入，不受 `image-plan.json` 的数量或位置约束。透明抠图设置 `preserveAlpha: true`；外部 SVG 使用独立 `svg` 元素或路径，不能和整页背景合成。两种图片都必须写入 `05_reconstruction/assets.json` 或登记材料来源，并保持对象 ID、`sourceId`、`z` 和元素清单一致。

重建时把预览图形翻译成 PptxGenJS 能识别的原生形状。构建规格只能写右列的预设名（`shared/scripts/qa_rules.py` 的 `PREVIEW_TO_NATIVE_SHAPES` 是同一张表的机器可读版本）；写预览侧的名字（`capsule`、`bubble`、`dots`、`split-block`、`v-shape`、`right-pentagon`、`sparkle`、`arrow-*`）会让构建器直接报 `Unknown shape`：

| 预览图形 | 构建规格写法 |
|---|---|
| `rectangle`／`rounded-rectangle` | `rect`／`roundRect` |
| `capsule` | 全圆角 `roundRect` |
| `bubble` | `ellipse` 加一个半透明高光 `ellipse`；云纹／气泡装饰可用 `cloud` |
| `ellipse`／`circle` | `ellipse` |
| `line` | `line` |
| `lines` | 按 `lineCount` 拆成多条 `line` |
| `ring` | `donut`（或粗描边 `ellipse`）；线宽约为内径一半，重建时保持预览记录的比例 |
| `arc` | `arc` |
| `dots` | 按同一网格拆成多个 `ellipse` |
| `split-block` | 2–5 个相邻 `rect`，斜向分色按预览角度切分 |
| `triangle`／`parallelogram`／`trapezoid`／`hexagon`／`chevron`／`pentagon`／`diamond` | 同名预设 |
| `sparkle` | `star4` |
| `right-pentagon` | `homePlate`（配 `rotate` 90°，两直角＋一对平行边，锐角朝右） |
| `v-shape` | `chevron` |
| `arrow-right`／`arrow-left`／`arrow-up`／`arrow-down` | `rightArrow`／`leftArrow`／`upArrow`／`downArrow` |
| `custom-polygon` | 拆成基本形状，或按阶段 3.2 的素材方案处理 |

预览里的 `rotation`（度）在构建规格里写成 `rotate`，`right-pentagon` 就是靠它把 `pentagon` 转向的；斜向排布的文本框同样写 `rotate`，角度与预览一致。

线阵 `lines` 按 `lineCount` 拆成多条 `line`；被 `clip` 裁剪的小元素直接把几何缩到文本框内重建；进度条的 `container` 用一个更大的全圆角 `roundRect` 作底层块，再叠各分段；AI 素材按 `edge.mode` 重建：`cutout` 插入阶段 3.2 烘焙的透明 PNG，`feather` 插入烘焙了羽化透明边缘的 PNG（`preserveAlpha: true`），常规插入按矩形图片并设置预览记录的透明度。用户提供的原照片按已批准预览的裁剪框、焦点和 `fit` 由构建器插入登记原件，不修改原件、不拉伸、不裁掉主体关键部位。

AI 素材按边缘处理结果插入：预览中做过 `cutout` 或几何遮罩的素材，插入阶段 3.2 烘焙的透明 `RECON-###` PNG（`preserveAlpha: true`，初次位置、尺寸、透明度与预览一致；成品位置可按美化记录调整），不得直接插入原始方形 `GEN-###`；只有满幅或通栏的整图才允许用矩形 `GEN-###`。封面必须由一张整体大图承担主视觉，其余页面不得堆叠零碎素材。渲染比对时透明边缘、封面大图和素材数量都会体现为逐页差异，发现偏差先回到阶段 3.2 重烘焙或修改 deck-spec。

带渐变填充的标题：PptxGenJS 不支持文字渐变，使用阶段 3.2 生成的 SVG（`<text>` + `<linearGradient>`，登记 `RECON-###`）插入；若改用“渐变中间色 + 原生阴影”的近似方案，必须在 `qa-review.json` 里记录为已批准偏差（逐页对照检查时一眼能看出渐变被换成了纯色）。`shadow` 用原生文本阴影参数还原。

内容页背景底图用一张整页 `image` 重建，并设置 `transparency = 100 - opacity × 100`（例如预览 `opacity: 0.25` → `transparency: 75`，`opacity: 0.35` → `transparency: 65`），保持与预览一致的弱对比；不得改用满不透明度或加深对比，也不得在底图上再叠一层纯色盖住内容。背景底图的主题必须与课题一致，封面不使用该类型承担主视觉。

组装时**必须按实际页型使用该方向的基础大图（有目录页时使用目录图）**（同一设计方向的那一套）：**封面页**放标题图 `hero-image`、**目录页**放目录图 `toc-image`、**每个内容页／致谢页**以背景图 `content-background` 作整页背景（`transparency = 100 - opacity × 100`）；发布校验会逐页核对，缺少该页型所需大图就报错（标题页缺标题图、存在目录页却缺目录图、内容页／致谢页缺背景底图）。这三张图按阶段 3.2 的登记路径插入（生成素材进入正片时在该阶段登记并保留 `GEN-###` 关系）。**页面的背景只能是这三张 AI 大图**（按页型取对应那一张），不得改用其他图片、别的生成图或自绘底色充当页面背景；除背景大图外，其余元素按 `05_reconstruction/element-inventory.md` 逐个重建，初次位置与已批准预览一致；成品渲染后可按《成品美化与自由调整位置》优化位置，保留风格与元素。

目录页的标号与小标题要**分开成两个单独的文本框**：标号一个框、小标题一个框（各自可编辑），别把“01 研究背景”写进同一个框；**标号字号比小标题略大一点**（例如小标题 26 pt 时标号 28–30 pt，或按预览放大 1.1–1.2 倍）；两个框里的文字都要**在文本框中心**（水平居中 `align: "center"` ＋ 垂直居中 `valign: "middle"`），标号落在编号底座正中。

文本框里的文字必须**在框的中心**（`align: "center"` ＋ `valign: "middle"`），且**不能出格**：放不下就放大文本框或减少文字，不要缩到低于该层级的字号下限，也不要把字挤到框外；`spec_errors`／`validate_project.py` 会检查文字是否放得进文本框、框内文字是否居中，报错就回元素清单与构建规格修正。

**背景层先铺 AI 大图**：每个页面先放该页对应的大图作背景——标题页 `hero-image`、目录页 `toc-image`、其余页（含致谢页）`content-background`（整页 `image` + `transparency` 与预览一致），再在它上面重建其余元素；**禁止用 AI 整页预览当底图拼接**。**完全拆解元素**：所有可见元素逐个独立重建（原生图形／SVG／抠图），不得把整页预览贴成一张图、也不得在预览图上叠文字或局部补丁；装饰色块与线条一个都不能漏。**渐变风格必须还原**：标题、线条与色块上的渐变（`linearGradient`／`radialGradient`）要记录色标与方向，用阶段 3.2 的 SVG 重绘或按几何还原；不得简化成纯色，除非在 `qa-review.json` 记为已批准偏差。页面上除背景大图外，其余元素都要是独立对象：文本与简单形状原生可编辑，SVG 内部路径可能需转换后编辑，局部透明位图只支持独立选中与替换。框内装饰为可选项；未采用的装饰不补加，已批准预览中采用的装饰仍须逐个重建。

**异形文本框与线条装饰一定要还原，不能省略**：胶囊形／圆角矩形／直角五边形／梯形／六边形／椭圆／气泡／分色色块，以及托线、线阵、点阵、圆弧、圆环、四芒星、斜向分色，都要在成品里出现——能原生还原就用原生（`roundRect`／`homePlate`／`ellipse`／`donut`／`line`／`arc` 等），不能原生还原就换方法，绝不能退化成普通矩形、也不能悄悄删掉。

预览里出现的每个元素都要在成品里复现，**不能省略**：能用原生形状表达的用 `text`／`shape`／`table`／`chart` 重建；不能原生还原的（复杂纹样、有机图形、渐变标题、光影材质等）按顺序尝试——① 生成独立 SVG 重绘（`RECON-###`），② 从已批准预览里裁出该区域再做 AI 抠图得到透明 PNG，③ 用 AI 生图重画同款元素；实在无法复现的必须在 `qa-review.json` 记成已批准偏差并说明原因，不能悄悄丢掉。

封面页与标题页使用的 AI 大图：**裁切时不要切到画面主体**——按设计稿的 `focal` 保留主体完整，边缘用羽化融进画面（左边缘羽化），宁可留一点背景也不要裁掉主体；裁完要对照预览确认主体没有被切断。

顶部进度条同样用原生对象重建：每个小节一个全圆角 `roundRect` 段，段内一个文本框写该小节标题，文字逐字取自 `content.json` 的 `sections`、与目录页一致，并把这些标题文本框标注 `origin: "progress"`——**进度条标题不属于页面文案，不要写进 `content.json` 的 `texts`**；发布校验会把 `origin: "progress"` 的文本与 `sections` 逐字比对，其余 `text` 元素仍与 `content.json` 逐字比对；未到达段、已完成段、当前段使用预览中记录的三种填充色，当前小节标题用加粗且更大的字号。不得用一张位图、一条细线或省略标题的图形代替进度条，各页进度条的高度与配色规则保持统一；其位置可随成品布局美化调整，仍须保留顶部导航、同级对齐和完整小节标题。

替换以下绝对路径占位符后执行构建和检查：

```powershell
node <subskill-dir>/scripts/build_pptx.js <project-dir> --python <python-path> --mode draft
python <subskill-dir>/scripts/validate_project.py <project-dir> --mode draft
```

组装器支持原生 `text`、`shape`、`table`、`chart`，以及独立 `image` 和 `svg` 对象；演讲备注使用页面级 `notes`。除非用户明确接受不可编辑版本，否则不得使用整页位图替代页面。试构建通过不代表正式交付通过。正式构建使用 `--mode release`，会验证阶段、预览批准、计划图片和输入版本，具体要求见[执行约定](../../shared/operations.md)。

## 成品美化与自由调整位置

生成 PPTX 后必须渲染并逐页评审画面美观度；若布局不够美观，可自由调整各元素的位置、对齐、间距、分区与叠放关系，不受已批准预览的精确坐标限制，也无需为这类位置美化再次询问用户。保持最终文案、数据、图片身份与来源、元素完整性、可编辑性和已确认风格；图注随对应图片移动，箭头保持原逻辑关系，背景仍覆盖整页，导航仍符合页型与小节要求。调整后不得越界、遮挡或产生不合理重叠。

保留已批准预览、设计稿与 image-plan.json 作为原始基线，不为位置美化重写它们或重新启动阶段 2.2。最终位置写入 06_build/deck-spec.json：meta.layoutAdjustmentAuthorization 记录用户原话或本工作流第 28 条授权，每个移动元素写 layoutAdjustment（from 为首次调整前的英寸 x／y，需要改叠放关系时同时记录原 z；reason 写具体美化原因），新位置与层级使用元素自身的 x／y／z。多轮调整继续保留同一原始起点。计划图片的位置和层级可按该记录调整，但其 w／h、sourceId、path、fit、focal、crop、altText 与已批准计划保持一致；边缘显示裁切可按特殊分块要求调整 boundaryMask，须在 layoutAdjustment.from.boundaryMask 保留初始轮廓（原来没有则为 null），并记录原因与规则 29 或用户授权。

记录位置美化与预览的差异，不把它们当成未经批准的偏离。若 preview_match 为 false，在 qa-review.json 的 deviations 中按页记录 type: layout_adjustment、原因、调整前后位置与当前对照图证据，approved_by 引用用户既有授权或本工作流第 28 条，approved_at 写授权依据的记录时间；不得伪造用户逐项确认。实际逐页审阅人及审阅时间仍如实填写。修改构建规格后重新构建、渲染、生成对照图并审阅当前版本，旧审阅不能直接复用。

## 视觉一致性与美观度检查

阶段 3.3 以已批准预览为初始设计基线，同时评审实际成品的美观度。画面不够美观时，可自由调整文字、图片、色块、装饰及其他对象的位置与叠放关系，再检查对齐、留白、重心、图文关系与跨页统一性。结构检查仍核对元素齐全、文字居中且不出框、事实图片正确嵌回；不能以忠实复现预览为由保留明显难看的布局。

逐页比对会遮罩成品文字框区域（整页预览里的文字只是排版参考、不是权威内容，只核对版面、色块、图片与装饰；成品文字在阶段 3.3 用原生文本按设计稿重建）

Windows 使用本阶段 `render_powerpoint.ps1` 生成带版本指纹的渲染清单，加 `-Pdf` 会同时导出 `07_delivery/deck.pdf` 并在清单记录 `pdf_path`／`pdf_sha256`，作为现场没有 PowerPoint 或字体缺失时的投影备份；再运行 `prepare_review.py`：它验证预览批准与渲染版本，生成"已批准预览 vs PPTX 渲染"的逐页对照图、总览和默认未通过的 `qa-review.json`。**不再做自动逐像素比对**——对照检查由人（或按人工标准逐页看图）完成，逐项填写 `visual/content/photos/editability/preview_match`，发现差异写进 `deviations`／`notes`；审阅 `visual` 项同时表示已评审成品美观度、位置优化效果和不存在授权范围外的非预期差异。字号换算错误、字体回退或换行差异要在这步看出来，回到 deck-spec 修正后重新构建、渲染与对照。不能批量批准；重新构建或渲染后旧审阅清单与 QA 记录失效。

## 交付

把 `deck.pptx`、导出的 `deck.pdf`（如已使用 `-Pdf`）、可用的渲染图与总览图、`review-manifest.json`、`qa-review.json`、`qa-report.md` 放入 `07_delivery/`。说明渲染器版本、逐页对照检查结果、已做检查、字体或矢量限制、已批准的偏差，以及无法验证的事项。只有结构、页数、素材、计划图片填充和逐页人工审阅都通过，才标记完成；无法渲染时如实说明，不能宣称通过。

最后运行 `validate_project.py <project-dir> --mode release` 和共享 `workflow.py <project-dir> complete 3.3`。结构、准确文本和对象数量检查不能代替事实判断或图表数据核查。保留旧版本归档与构建记录。

## 分块贴合与框高适配

按[特殊分块的元素排布](../13-design/references/layout-splits.md#元素贴合特殊分块)组装和美化：文本框顺着分界排布，必要时裁切框体并保留完整原生文字；框高按文本适配，避免大片内部留白。图片可登记 boundaryMask，由构建器从同一原件生成边缘透明的独立图片对象。成品轮廓与初始计划不同则在 layoutAdjustment.from.boundaryMask 记录原值（无则 null），沿用既有授权并重新构建、渲染和逐页审阅。

## 背景与文本框底色协调

背景色与文本框填充色（框体底色，不是描边色）应有适度色差，能区分层次但避免强烈反差；优先采用协调的邻近色或轻微明度变化。描边色单独说明，不能用边框色差代替填充色差。文字与框底仍须清晰可读。设计和提示词写清填充与背景的柔和层次关系；逐页看图检查实际落地，纹理背景以框所在区域的可见底色为准。
