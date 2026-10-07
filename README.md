# academicppt-workflow

用于 Codex 的可编辑 PPTX 制作 skill。将论文、报告、照片、品牌素材和数据，按阶段整理为设计完整、可编辑的 PowerPoint 演示文稿。

项目名称为 `academicppt-workflow`，发布在 [fang628/customizable-pptx-workflow](https://github.com/fang628/customizable-pptx-workflow)；skill 名称仍为 `pptx-workflow`，调用入口为 [SKILL.md](SKILL.md)。

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

在 Codex 中使用 `$pptx-workflow` 并提供材料与制作要求。图像生成供应商、模型和凭据按需求阶段配置；凭据通过环境变量提供。其他工具、字体与渲染要求见 [执行与验收约定](shared/operations.md)。

## 生图 API 配置

**推荐使用 GPT Image 2.0 或以上版本的生图模型。** GPT Image 2.0 对应的 API 模型名称为 `gpt-image-2`，支持图像生成与参考图编辑；更高版本须使用供应商实际开放的模型 ID，并确认适配脚本兼容。模型能力与参数见 [OpenAI 官方模型说明](https://developers.openai.com/api/docs/models/gpt-image-2)及[图像生成指南](https://developers.openai.com/api/docs/guides/image-generation)。本工作流需要文生图和图生图两种能力，返工时会在已有图片基础上编辑。

### 1. 准备供应商与适配脚本

项目初始化器默认预填 VSAKURA 通道：模型 `gpt-image-2`、密钥环境变量 `VSAKURA_API_KEY`。该通道使用 OpenAI 兼容 Images API：文生图调用 `/v1/images/generations`，图生图调用 `/v1/images/edits`。

生图适配脚本需要另行安装，**本仓库不包含供应商的调用脚本**。默认会查找：

```text
~/.codex/skills/vsakura-imagegen/scripts/vsakura_imagegen.py
```

使用此方案时，先安装配套的 `vsakura-imagegen` skill；若使用其他脚本，在项目配置的 `adapterScript` 中填写它的绝对路径。可先在 PowerShell 中检查默认脚本是否存在：

```powershell
Test-Path "$env:USERPROFILE\.codex\skills\vsakura-imagegen\scripts\vsakura_imagegen.py"
```

### 2. 设置 API Key 与 API 地址

在 Windows PowerShell 中输入密钥，将它保存为用户环境变量，同时让当前终端可用：

```powershell
$apiKey = Read-Host "输入生图 API Key" -AsSecureString
$env:VSAKURA_API_KEY = [System.Net.NetworkCredential]::new('', $apiKey).Password
[Environment]::SetEnvironmentVariable('VSAKURA_API_KEY', $env:VSAKURA_API_KEY, 'User')
Remove-Variable apiKey
```

已打开的 Codex 或其他终端需要重启才能继承新的环境变量。密钥不要写入 README、项目 JSON、提示词或 Git 仓库；`credentialEnv` 只填写环境变量名称。

配套 VSAKURA 脚本默认 API 地址为 `https://apisub.vsakura.top`，可通过 `VSAKURA_BASE_URL` 覆盖。只有供应商接口兼容、且该地址与密钥属于同一供应商时才修改，例如：

```powershell
$env:VSAKURA_BASE_URL = 'https://你的供应商域名/v1'
[Environment]::SetEnvironmentVariable('VSAKURA_BASE_URL', $env:VSAKURA_BASE_URL, 'User')
```

使用其他适配脚本时，API 地址和密钥变量按该脚本说明配置。本工作流的项目 JSON 没有 `baseUrl` 字段，API 地址由适配脚本管理。

### 3. 填写项目生图配置

阶段 0 初始化后，编辑制作项目中的 `00_intake/ai-image-config.json`。最小配置示例：

```json
{
  "version": 1,
  "provider": "vsakura",
  "model": "gpt-image-2",
  "credentialEnv": "VSAKURA_API_KEY",
  "credentialsReady": false,
  "allowReferenceUpload": false,
  "referenceImageLimit": 3,
  "adapterScript": ""
}
```

| 字段 | 配置方法 |
| --- | --- |
| `provider` | 实际供应商标识；默认 `vsakura`，也可配置其他供应商。 |
| `model` | 供应商支持的精确模型 ID；推荐 GPT Image 2.0 或以上版本，示例为 `gpt-image-2`。 |
| `credentialEnv` | 适配脚本实际读取的密钥环境变量名；修改此字段不会自动改变脚本读取的变量。 |
| `credentialsReady` | 默认 `false`；确认密钥已配置、脚本可用后，在阶段 1.1 标记为 `true`。 |
| `allowReferenceUpload` | 默认 `false`；仅在同意向该供应商上传参考图后改为 `true`，材料还须逐项登记上传许可。 |
| `referenceImageLimit` | 单次允许上传的参考图上限；示例为 3，须同时符合供应商限制。 |
| `adapterScript` | 生图 CLI 脚本绝对路径；留空时按 `provider` 查找默认脚本。 |

VSAKURA 是默认示例，可使用 OpenAI 官方 API 或其他供应商，但需要匹配的适配脚本、API 地址和密钥。更换供应商、模型或适配脚本后，须重新确认配置与受影响的下游批准。

自定义适配脚本须接收 `--prompt`、`--model`、`--size`、`--n`、`--output-dir` 和可重复的 `--image` 参数；不同参数名可用 `adapterArguments` 映射。成功时标准输出须为 JSON，包含 `success: true`、实际 `model`、单张图片的 `output_files` 绝对路径列表，以及 `request_id` 或 `call_id`。实际模型须与配置一致。具体契约见 [生图适配器](shared/scripts/imagegen_adapter.py)和[配置 schema](shared/schemas/ai-image-config.schema.json)。

### 4. 检查配置并确认费用

在 skill 目录中运行：

```powershell
$env:PYTHONUTF8 = '1'
python stages/00-init/scripts/check_environment.py --project D:\Projects\my-presentation
```

检查输出中 `ai_image_config` 的 `valid_json`、`credentialPresent`、`adapterScriptExists`，配置就绪后 `credentialsReady` 也应为 `true`。此命令检查本机环境，不调用付费生图 API，也不验证账户余额、网络连通性或模型权限。

首次使用在阶段 1.1 确认供应商、模型、凭据状态、参考图上传许可和费用口径，再进入生图阶段。工作流会按需多次生成与重试，费用按供应商定价计；旧配置中的 `stageBudgets` 已废弃。API 返回尺寸可能与请求不同，整页预览先检查供应商原图是否精确16:9；不合格原图退回并保留记录，不补边、不裁切修正。合格原图仅等比缩放为1920×1080。

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
