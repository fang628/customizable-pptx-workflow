# academicppt-workflow

用于 Codex 的可编辑 PPTX 制作 skill。将论文、报告、照片、品牌素材和数据，按阶段整理为设计完整、可编辑的 PowerPoint 演示文稿。

项目名称为 `academicppt-workflow`，发布在 [fang628/pptskill](https://github.com/fang628/pptskill)；skill 名称仍为 `pptx-workflow`，调用入口为 [SKILL.md](SKILL.md)。

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
git clone https://github.com/fang628/pptskill.git "$env:USERPROFILE\.codex\skills\pptx-workflow"
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

## 目录

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | 总流程入口与编排规则 |
| `agents/` | Codex skill 配置 |
| `stages/` | 各阶段说明、脚本与模板 |
| `shared/` | 共享规范、校验脚本、schema 与参考图 |
| `tests/` | 现有工作流测试 |
| `package.json` / `package-lock.json` | Node.js 依赖及版本锁定 |

依赖目录、缓存、凭据和 `work/` 临时产物由 `.gitignore` 排除，不随仓库发布。
