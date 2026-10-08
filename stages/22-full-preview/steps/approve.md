# 2.2d：完成检查后提交用户批准

以下全篇提交要求用于首轮批准。已批准项目的局部返工先用 `workflow.py impact` 检查范围；无全篇依赖变化时，展示变化页、取得实际确认后按[增量批准规则](../../../shared/incremental-rework.md)执行 `approve preview --pages`，其余页沿用原确认。全篇变更或旧批准无页面快照时仍整体重新批准。

## 批准闸门

全篇 AI 底稿生成完后先本地插入全部登记原图；逐页实际查看插入后的完整预览，核对全图保留、原图可读性、比例、位置与遮挡情况。全部完成后才运行 `await 2.2`，展示插入原图后的整套预览、逐页结论与偏差。用户确认后用共享 `workflow.py approve preview --evidence "实际确认记录"` 写入 `04_full-preview/approval.json`（绑定预览清单、jobs、ledger 与预览 PNG 的哈希），再 `complete 2.2`，加载[元素拆解子 skill](../../31-element-audit/SKILL.md)。不得伪造确认。
