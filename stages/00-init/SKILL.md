---
name: 00-init
description: "为可编辑 PPTX 项目创建标准目录、模板和流程状态。用于 pptx-workflow 的阶段 0，或补齐该工作流缺失的项目骨架。"
---

# 阶段 0：项目初始化

**停机点：无。** 本阶段不暂停：环境与目录检查完直接进入 1.1，中途不得结束任务进程。

**开工前先读规范库**：先读[执行与验收约定](../../shared/operations.md)的《规范库索引（按步骤）》里「0 建立环境」一行与它列出的章节，再读[共享工件约定](../../shared/artifact-contract.md)的对应小节；每进入一个新步骤都重读该步骤的章节，不要凭记忆。

阅读[共享工件约定](../../shared/artifact-contract.md)。将以下路径占位符替换为本子 skill 和项目的实际绝对路径后运行：

```powershell
python <subskill-dir>/scripts/init_project.py <project-dir>
```

初始化器只增加缺失目录和模板，不覆盖已有文件。项目外的原始材料保留在原位置；除非用户要求，不自行移动或复制到 `00_intake/materials/`。它会创建默认标注为“待确认”的 `00_intake/ai-image-config.json`，供应商、模型、凭据环境变量和适配脚本均置空，参考图上限为 0；阶段 1.1 必须询问并按用户确认填写生图配置，不得自动选择供应商或模型。推荐 GPT Image 2.0 或以上版本。

先用本阶段 `scripts/check_environment.py` 检查 Python、Node、字体、渲染器和项目 AI 适配脚本，命令见[执行约定](../../shared/operations.md)。字体检查用 `--font "<族名>"` 给出本项目必须可用的字体族（正文、标题、粗体字面各一项），缺失时脚本返回非零退出码并把清单写入 `00_intake/font-report.json`；清单同时记录每个字体族的常规体与粗体是否可用。发生字体回退会让预览与交付的字面、字号和换行不一致，必须在阶段 1.1 前换成已安装字体，或明确记录回退方案。该检查只报告环境变量是否存在，不读取或保存密钥，也不证明账号额度可用。依赖声明位于根目录 `package.json` 和 `shared/requirements.txt`；不擅自全局安装。初始化器同时建立机器可读材料、定稿、素材和生成任务清单，不替用户批准需求或方案。

确认 `workflow-state.json`、阶段目录和起始工件均存在，依赖与字体检查已通过（或回退方案已记录），将阶段 0 标记完成。接着加载[材料与需求子 skill](../11-intake/SKILL.md)。
