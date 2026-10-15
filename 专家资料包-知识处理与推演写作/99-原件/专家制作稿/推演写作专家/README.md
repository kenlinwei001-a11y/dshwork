# 推演写作专家

Corpus-grounded deductive report writer. Consumes semantic graph plus desensitized corpus via inject/tool/work-package channels; borrows form never values; binds numbers to node refs; conflicts stay pending-review; prose back-readable to graph nodes.

## 使用

在 WorkDSH「我的专家」导入此专家包，预览整套内容并确认发布。选择示例开始新任务。导入不授予权限，不运行脚本，不安装依赖；缺少技能会在发布校验中指出。

## 修改

编辑 agents/ 中的 Markdown 专业内容，保留文档头部和区段标记。在制作对话中让 AI 读取修改后的文件，通过 workdsh_expert_save_documents 保存整套文档为草稿，再统一预览发布。原 ZIP 的 manifest 校验不可手工绕过；保存后从界面重新导出。

## 版本

expert.json 是此交付包的结构化快照；Markdown 是同一份内容的可编辑制作稿。已有任务保持原修订。团队成员来自内容快照，不随来源专家自动更新。
