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

**推荐使用 GPT Image 2.0 或以上版本的生图模型。** 选定模型须支持文生图和参考图编辑，模型 ID 与可用参数以供应商接口为准。模型能力见 [OpenAI 官方图像生成指南](https://developers.openai.com/api/docs/guides/image-generation)。

生图配置默认置空。阶段 1.1 会集中询问以下信息，并在获得回答后直接完成配置：

- 生图供应商及 API 地址；
- 具体模型；
- API Key 是否已配置，以及现有凭据环境变量；
- 是否允许上传参考图，以及单次上传上限。

Codex 会按确认结果配置 API 地址与凭据接入、写入项目的 `00_intake/ai-image-config.json`，准备兼容的调用脚本，并检查凭据是否存在、脚本是否可用及参数是否匹配。缺少调用脚本时，由 Codex 根据所选接口在项目内创建或适配；已有可用配置则直接复用。用户提供必要信息即可完成这一步。

API Key 通过环境变量或本地隐藏输入配置，不在聊天、项目 JSON、提示词或 Git 仓库中保存明文。仅在实际检查或用户确认就绪后，才将配置标记为可用。

阶段 1.1 同时说明会按需多次生成与重试，费用按供应商定价计，并确认参考图上传许可。完成配置与需求确认后才进入生图阶段；更换供应商、模型或调用脚本时重新确认。

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
