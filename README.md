# customizable-pptx-workflow

用于 Codex 的可编辑 PPTX 制作 skill。将论文、报告、照片、品牌素材和数据，按阶段整理为设计完整、可编辑的 PowerPoint 演示文稿。

项目名称为 `customizable-pptx-workflow`，发布在 [fang628/customizable-pptx-workflow](https://github.com/fang628/customizable-pptx-workflow)；skill 名称仍为 `pptx-workflow`，调用入口为 [SKILL.md](SKILL.md)。

## 工作流程与阶段产出

工作流从材料整理开始，先确认文字与设计，再生成视觉预览，最后逐个重建为可编辑PPTX。下文中的产出路径均相对于**演示文稿项目目录**，不是skill仓库目录；例如项目为 `D:\Projects\my-presentation` 时，设计稿位于该项目的 `02_design/design-spec.md`。

初始化时会创建部分空模板；文件存在不表示该阶段已经完成。执行者会填写、检查并绑定当前文件版本，再更新项目状态。

### 阶段0：初始化项目与检查环境

创建标准目录和模板，检查Python、Node.js、依赖、渲染工具以及标题／正文所需字体。已有项目只补缺失文件，不覆盖用户内容。

- `workflow-state.json`：贯穿全流程的阶段状态、完成记录和产物版本，用于恢复任务及判断后续阶段能否继续。
- `00_intake/font-report.json`：实际字体检查结果，记录所需字体族与常规、粗体字面的可用性。
- `00_intake/ai-image-config.json`：默认生图通道配置模板；仍需在1.1确认可用性及参考图许可。

阶段说明：[项目初始化](stages/00-init/SKILL.md)。

### 阶段1.1：读材料、澄清需求与确认生图配置

读遍材料的文字与图片，分类登记来源，识别缺失内容和冲突版本；确认用途、受众、语言、页数或时长、目录、致谢、进度条、讲稿、品牌及保密要求。默认使用imagegen内置工具，确认工具可用性和参考图上传许可；用户明确选择外部API时再配置对应接口。

- `00_intake/project-brief.md`：需求说明，记录制作目标、默认选项、用户回答、仍待补充的材料及确认依据。
- `01_inventory/material-inventory.md`：供人阅读的材料清单，说明每份材料的内容、候选用途和需要核实的问题。
- `01_inventory/materials.json`：供脚本使用的原件登记表，记录材料编号、实际路径、文件哈希与上传许可。
- `00_intake/ai-image-config.json`：已确认的生图通道、就绪状态、参考图许可及数量上限。
- `00_intake/requirements-approval.json`：需求批准记录，绑定实际确认的需求与配置版本。

**用户确认节点：**需求与材料、页面开关、生图通道和上传许可确认后，才进入内容与素材生成。阶段说明：[材料与需求](stages/11-intake/SKILL.md)。

### 阶段1.2：挑选候选内容与生成独立素材

按需求选出文字、事实图片与数据，整理为有叙述顺序的内容清单。此时保留足够的候选内容，下一阶段再精简为最终文案。为a／b／c三种设计方向分别准备封面大图、内容页背景底图；需要目录时，每个方向另备目录大图，致谢页可复用背景底图。生成素材只能补充非事实视觉表达，不能替代真实照片、数据或证据。

- `02_design/content-plan.md`：先于实质性设计稿完成的候选文字与图片清单，含《文案与材料原文索引》，逐条记录文案编号、PPT候选文案、材料ID、原文位置、原文摘录与整理方式；用于查回候选文案依据，阶段1.3据此精简定稿。
- `02_design/image-intent-plan.json`：图片的初步用途、归属、大致区域及相对大小，后续在1.3随设计稿确认。
- `02_design/generated-assets/GEN-###.png`：实际生成的独立底图、主题图或其他候选素材。
- `02_design/generated-assets.json`：候选素材登记表，记录设计方向、用途、事实边界、文件路径与哈希。
- `02_design/generation-jobs.json`、`generation-ledger.json`、`generation-prompts.md`：生成任务、真实结果证据及提示词记录，含义见下文“生成记录”。

候选素材不自动进入成品；采用哪些素材由后续设计与预览确认。阶段说明：[内容与素材清单](stages/12-content/SKILL.md)。

### 阶段1.3：编写逐页设计稿与定稿文案

确定页面顺序、章节逻辑、每页目的、最终上屏文字和素材身份。设计稿用Markdown嵌套排版树表达宏观分块、内部子分块及所属文字、文本框、图片与装饰；并列文字逐段拆开，由小标题统领各分点，实际文案加粗便于阅读。文本框形状与颜色在风格要求中按角色集中说明一次；排版树的文字条目只写文案、文段类型、位置和文本关系。特殊分块的造型语言在风格要求中概括，实际形态与组合在分块树交代，轮廓、曲率和局部比例保留合理创意空间，不照搬参考图。逐页只写实际差异。此阶段确认内容与设计意图，具体视觉效果在2.1／2.2落实。

- `02_design/design-spec.md`：主要复核文件，包含全篇逻辑、三种风格意图、逐页最终文案与嵌套排版树，可直接阅读并提出修改。
- `02_design/content.json`：页面顺序、页型、逐字定稿文案及章节导航的结构化来源；后续成品文字以它为准。
- `02_design/claim-map.json`：事实主张与材料依据的对应关系，帮助核对数字、结论和证据。
- `02_design/image-intent-plan.json`：与设计稿一致的粗略图片意图，确认“用哪张图、服务什么内容、大致放哪里”；精确图片框在2.2定稿。

**用户确认节点：**设计稿写完后交用户复核或修改，重新读取修改稿并同步相关JSON后才完成本阶段。阶段说明：[设计稿](stages/13-design/SKILL.md)。

### 阶段2.1：生成三种风格的代表页预览

依据已确认设计稿，为a／b／c三种方向生成同一组代表页，比较配色、构图、图文关系和视觉语言。通常包含封面、目录（需要时）和一张有代表性的内容页；内容页不固定选第一页。三个方案保持文案与材料身份一致。

封面和目录在原底图上构建，不要求底图图注或图片占位框；其他页型的计划图片保留等比占位块，此时主要审阅设计方向。

- `03_concepts/option-a/`、`option-b/`、`option-c/`：用户查看的三版代表页PNG及各自的 `preview.json`；本地修框后的派生预览可保存在方案目录的 `repairs/` 中。
- 各方案的 `preview.json`：登记页面、生成任务、预览文件及哈希、设计摘要和适用的占位框记录。
- `03_concepts/assets/GEN-###.png`、`raw/`：规范化生成输出与保留的原始工具输出。
- `03_concepts/generation-jobs.json`、`generation-ledger.json`：本阶段的生成任务与结果证据。
- `03_concepts/concept-review.md`：三版逐页审阅、问题与修订记录。
- `03_concepts/approval.json`：用户选择的方向及批准版本。

**用户确认节点：**选择一个方向或提出修改后再继续全篇预览。阶段说明：[三版方案](stages/21-concepts/SKILL.md)。

### 阶段2.2：生成全篇底稿、插入原图并批准完整预览

把选定风格同步进设计稿，生成全部页面底稿，落实精确图片计划；随后在本地插入登记原图、应用已规划的边缘轮廓，逐页实际查看，再交用户确认。AI不能重画事实图片，只有占位框的页面不能作为完整预览提交批准。

- `02_design/image-plan.json`：精确图片计划，记录图片来源、框位、比例、适配、焦点、裁剪及边缘轮廓，保留1.3确认的图片身份。
- `04_full-preview/assets/GEN-###.png`、`raw/`：AI生成的整页底稿与原始输出，保留生成证据，不能被本地插图覆盖。
- `04_full-preview/slides/Sxx.png`：已经本地插入登记原图的完整页面预览，这是用户确认全篇设计时主要查看的图片。
- `04_full-preview/previews.json`：全篇页序、风格约束、底稿与最终预览的路径／哈希、占位框、实际原图插入记录及逐页review。
- `04_full-preview/generation-jobs.json`、`generation-ledger.json`、`generation-log.md`：全篇生成任务、证据及修订过程。
- `04_full-preview/approval.json`：完整预览批准记录，作为元素重建的视觉基线。

同一图片位至少两轮真实比例修订仍无效时，允许[本地修正空白图框](shared/preview-contract.md#多次修订后的本地空白图框修正)，记录修正前后框位，保留原始输出，修正后重新插图并复看。

**用户确认节点：**全部完整预览生成、原图插入并实际查看后，等待用户批准；批准前不进入元素重建。阶段说明：[完整预览](stages/22-full-preview/SKILL.md)。

### 阶段3.1：逐页识别元素与制定还原方式

拆解已批准完整预览，识别文字、色块、线条、图标、装饰、背景和图片，记录位置、样式、来源与叠放关系，并决定用原生对象、SVG还是独立位图还原。事实图片沿用登记原件，不从扁平预览里裁出近似图替代。

- `05_reconstruction/element-inventory.md`：先列出非文字视觉元素、服务的内容及计划分离方式，防止重建遗漏。
- `05_reconstruction/slide-elements.md`：全部页面元素的详细记录，包含文字几何／样式及非文字元素信息，为重建与组装提供依据。

本阶段只识别与登记；准确文字仍取自 `content.json`，不从AI预览OCR后重新定稿。阶段说明：[元素拆解](stages/31-element-audit/SKILL.md)。

### 阶段3.2：重建非文字素材

按元素清单逐项准备素材：简单图形采用PowerPoint原生对象，复杂平面元素重绘为SVG，需要时生成局部透明位图或抠图。登记实际采用的背景素材与来源，保留渐变、轮廓和装饰细节。

- `05_reconstruction/photos/`、`vectors/`、`rasters/`、`cutouts/`：加工后的照片、独立SVG、位图和抠图素材；原始材料保留不动。
- `05_reconstruction/assets.json`：进入组装的素材登记表，记录来源、路径、哈希及与原生成素材的对应关系。

本阶段准备非文字视觉素材；文字本体不会转成SVG或位图，也不把文字与事实原图提前扁平化进整页背景。阶段说明：[素材重建](stages/32-asset-rebuild/SKILL.md)。

### 阶段3.3：组装可编辑PPTX、渲染与验收

按定稿文字、元素记录和素材组装PPTX，独立插入登记原件。**准确文字在本阶段逐字重建为PowerPoint原生文本框**；简单形状、表格与图表按可编辑对象构建。SVG与局部位图作为独立对象插入，其内部内容不一定原生可编辑，不能用整页预览贴图叠字替代交付。

构建后渲染全部页面，逐页对照已批准预览检查文字、版式、图片、元素完整性和可编辑性；必要时按既有授权优化位置、对齐和间距，再重新渲染与验收。

- `06_build/deck-spec.json`：PPTX组装规格，记录对象、准确文字、素材路径、样式、几何及允许的位置调整。
- `06_build/build-log.md`：构建模式、页面数量与成品版本等日志。
- `07_delivery/deck.pptx`：正式交付的可编辑演示文稿。
- `07_delivery/preview/`、`render-manifest.json`：成品渲染图及对应PPTX版本、文件哈希。
- `07_delivery/review/`、`review-manifest.json`：已批准预览与成品渲染的逐页对照图、总览及审阅版本绑定。
- `07_delivery/qa-review.json`、`qa-report.md`：逐页审阅结论、差异说明及结构／内容／图片／可编辑性校验结果。
- `07_delivery/deck.pdf`：使用渲染脚本的PDF导出选项时生成，作为展示备份；不替代可编辑PPTX。

试构建成功不等于正式交付通过，须完成当前版本的逐页审阅与发布校验。未要求讲稿时，工作流在此交付结束。阶段说明：[组装与验收](stages/33-build/SKILL.md)。

### 阶段4（可选）：生成逐页讲稿与演讲备注

仅在需求阶段确认需要时执行，根据最终内容与成品写逐页讲述、转场和建议时长，不引入材料以外的新事实。

- `08_speaker-notes/notes.json`：逐页备注、建议时长与证据依据，可用于后续写入PPTX原生备注栏。
- `08_speaker-notes/speaker-script.md`：供演讲者阅读的完整讲稿，覆盖各页标题、正文讲述与转场。

默认提供独立讲稿文件。需要嵌入PPTX备注栏时，通过构建规格重新构建，并更新3.3的渲染与验收版本后才完成。阶段说明：[演讲稿](stages/40-speaker-script/SKILL.md)。

## 中途复核与生成记录

### 用户主要查看哪些文件

| 节点 | 主要查看内容 | 确认后继续做什么 |
| --- | --- | --- |
| 1.1需求确认 | `project-brief.md`、材料清单及生图／上传许可结论 | 选材与生成候选素材 |
| 1.3设计稿复核 | `02_design/design-spec.md`中的最终文案、叙述逻辑和嵌套排版树 | 生成三方向代表页 |
| 2.1方向选择 | `03_concepts/option-a/`、`option-b/`、`option-c/`的代表页 | 按选定方向生成全篇 |
| 2.2完整预览批准 | `04_full-preview/slides/`中的全部插图后页面 | 拆解、重建并组装PPTX |
| 成品交付 | `07_delivery/deck.pptx`、渲染图与质检结果，及可选PDF／讲稿 | 使用成品或提出后续修改 |

Markdown用于阅读与修改意图，JSON用于脚本执行、来源追溯和验收。执行者负责同步两者，用户不需要手填JSON。AI预览中的文字用于看语义、层级和体量；成品准确文字以1.3确认的 `content.json` 为准。

### 生成记录分别做什么

1.2、2.1、2.2各有独立的任务与账本；所有提示词集中记录在 `02_design/generation-prompts.md`，按阶段组织。

| 文件或目录 | 用途 |
| --- | --- |
| `generation-jobs.json` | 调用前的任务计划：实际提示词、输出位置、参考图／编辑源、页面绑定和素材用途。内部编号留在本地元数据，不写进生图提示词。 |
| `generation-ledger.json` | 调用后的真实结果证据：通道、模型路由或实际模型、结果标识、提示词与文件哈希、规范化记录、尝试次数和状态；它不是提示词清单。 |
| `raw/` | 保留工具原始输出；内置模式另保存工具结果回执，用于核对来源和版本。 |
| `generated-assets/`或`assets/` | 项目稳定引用的素材或规范化页面底稿；与本地插图后的完整预览分开保存。 |
| `preflight.json`（适用阶段） | 生成任务与提示词自检记录；不代替每轮规范阅读、实际看图或用户批准。 |

### 中断恢复与修改

在项目根目录执行以下只读检查，了解当前阶段与可继续的位置；命令中的skill路径替换为实际安装位置：

```powershell
python <skill>/shared/scripts/workflow.py <project> status
python <skill>/shared/scripts/workflow.py <project> stop-point
```

修改需求、最终文案、图片身份或风格方向时，回到最早受影响的阶段，更新工件并重新检查下游批准绑定；未改变的素材与页面可以复用。仅按既有授权调整成品位置时，在3.3记录差异并重新渲染验收。完整规则见[阶段边界与返工路由](shared/artifact-contract.md#阶段边界与返工路由)，不要手工改状态或旧哈希来跳过检查。

## 安装与使用

将仓库克隆到 Codex 的 skills 目录，目录名保留 `pptx-workflow`。Windows PowerShell 示例：

```powershell
git clone https://github.com/fang628/customizable-pptx-workflow.git "$env:USERPROFILE\.codex\skills\pptx-workflow"
```

若该目录已有 skill，请在已有目录中使用 Git 更新，避免覆盖现有文件。

在 skill 目录中安装依赖：

```powershell
python -m pip install -r shared/requirements.txt
npm ci
```

初始化演示文稿项目：

```powershell
python stages/00-init/scripts/init_project.py D:\Projects\my-presentation
```

在 Codex 中使用 `$pptx-workflow` 并提供材料与制作要求。默认生图通道为 `imagegen` skill 的内置 `image_gen` 工具，无需 API Key；外部 API 仅在用户明确选择时配置。其他工具、字体与渲染要求见 [执行与验收约定](shared/operations.md)。

## 生图通道

默认使用 Codex 自带的 `imagegen` skill（通常位于 `~/.codex/skills/.system/imagegen/SKILL.md`），由代理调用内置 `image_gen` 工具生成和编辑图片，无需安装供应商脚本或配置 API Key。阶段1.1确认工具可用性、用户需求及参考图许可；初始化默认值不等于需求批准，已有项目的已确认通道不自动覆盖。

新项目默认配置：

```json
{
  "version": 1,
  "provider": "imagegen",
  "model": "builtin-auto",
  "credentialEnv": "",
  "credentialsReady": false,
  "allowReferenceUpload": false,
  "referenceImageLimit": 3,
  "adapterScript": ""
}
```

`builtin-auto` 是内置工具路由标记，不宣称实际模型；工具返回具体模型时另记 `tool_model`。内置通道的 `credentialsReady` 表示代理已确认工具可用，不能靠终端脚本证明；不要求设置密钥。

生成前仍运行原有自检，生成后用 `--import-result` 将真实工具结果复制进项目并登记调用回执、提示词／参考图／原图／输出哈希。项目素材不得仅留在 Codex 默认生成目录。工具模式与回执格式详见[生图通道与结果登记](shared/image-generation.md)。

内置工具不可用时说明情况；仅用户明确选择或确认 CLI/API 通道后，才填写外部供应商、实际模型、凭据环境变量及兼容适配脚本。官方 imagegen CLI 按其 skill 指令使用，不自行改写其脚本；其他供应商复用或适配已有调用脚本，不要求用户编写配置或脚本。原有 CLI JSON 契约仍见[生图适配器](shared/scripts/imagegen_adapter.py)与[配置 schema](shared/schemas/ai-image-config.schema.json)，不得静默切换通道。

生图按需尝试，保留真实失败记录；内置工具按当前账户额度与使用规则，外部 API 按供应商定价说明费用。整页实际原图必须精确16:9，合格后仅等比缩放为1920×1080，不补边、不裁切修正比例。

## 仓库目录

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 总流程入口与编排规则 |
| `agents/` | Codex skill 配置 |
| `stages/` | 各阶段说明、脚本与模板 |
| `shared/` | 共享规范、校验脚本、schema 与参考图 |
| `tests/` | 现有工作流测试 |
| `package.json` / `package-lock.json` | Node.js 依赖及版本锁定 |

依赖目录、缓存、测试覆盖率报告、凭据和 `work/` 临时产物由 `.gitignore` 排除，不随仓库发布。误初始化到仓库根目录的 PPT 项目目录（`00_intake/` 至 `08_speaker-notes/`）、状态与运行锁也被排除；建议把制作项目放在仓库外，例如 `D:\Projects\my-presentation`。skill 自带的参考图、模板、测试和 `package-lock.json` 保留版本管理。
