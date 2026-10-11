# 聊天中文加粗渲染修复

- 已确认：只在网页 Markdown 渲染入口规范化，不修改消息存储、复制内容或模型上下文；不重启 3001，不 push，提交到当前 `fix/report-package-pdf-overflow` 分支。
- 规则与 `service/report_package.py` 一致：正文中 `**内容**` 后紧跟非空白字符时，在闭合标记后补一个空格。共用网页已有的代码区识别，保留行内代码、围栏代码及流式未闭合代码块；缩进代码原样保留。
- 验收直接检查 ReactMarkdown 生成的 `<strong>`，覆盖用户原句、中文标点、列表/表格、代码保护，并回归 TeX 与附件渲染。随后运行 typecheck、build；用户自行重启。

## 验收结果

- `node --import tsx --test tests/markdown-bold.test.ts tests/markdown-math.test.ts tests/artifact-links.test.ts`：10/10 通过。
- `npm run typecheck`、`npm run build` 均通过；构建仅提示现有主 JS 包大于 500 kB，不影响生成。
- 只修改渲染入口，消息存储与复制路径未改动。3001 未重启，监听 PID 保持 9592。
