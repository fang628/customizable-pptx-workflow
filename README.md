# customizable-pptx-workflow

用于 Codex 的可编辑 PPTX 制作 skill。将论文、报告、照片、品牌素材和数据，按阶段整理为设计完整、可编辑的 PowerPoint 演示文稿。

项目名称为 `customizable-pptx-workflow`，发布在 [fang628/customizable-pptx-workflow](https://github.com/fang628/customizable-pptx-workflow)；skill 名称仍为 `pptx-workflow`，调用入口为 [SKILL.md](SKILL.md)。

## 工作流程

1. 初始化项目目录，检查依赖与字体。
2. 整理材料并确认需求。
3. 编写内容清单和逐页设计稿。
4. 提供三种视觉方向，确认后生成完整预览。
5. 拆解元素、重建素材并组装可编辑 PPTX。
6. 渲染、逐页检查并交付；可按需生成演讲稿。

需求、设计稿、视觉方向和完整预览均设有用户确认节点。详细要求以 `SKILL.md` 和各阶段说明为准。

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

## 目录

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 总流程入口与编排规则 |
| `agents/` | Codex skill 配置 |
| `stages/` | 各阶段说明、脚本与模板 |
| `shared/` | 共享规范、校验脚本、schema 与参考图 |
| `tests/` | 现有工作流测试 |
| `package.json` / `package-lock.json` | Node.js 依赖及版本锁定 |

依赖目录、缓存、测试覆盖率报告、凭据和 `work/` 临时产物由 `.gitignore` 排除，不随仓库发布。误初始化到仓库根目录的 PPT 项目目录（`00_intake/` 至 `08_speaker-notes/`）、状态与运行锁也被排除；建议把制作项目放在仓库外，例如 `D:\Projects\my-presentation`。skill 自带的参考图、模板、测试和 `package-lock.json` 保留版本管理。
