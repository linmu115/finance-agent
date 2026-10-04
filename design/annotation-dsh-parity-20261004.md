# DSH 引用交互补齐与完整年报样本

## 用户要求

用户指出上一版只做了引用气泡，没有落实 dsh-annotation-core 的交互；要求模仿本机插件的真实交互，并提供典型、完整的财报 PDF 和可用于亲自验收的分析提问。

## 对照对象

- Launcher 正在运行的 DSH 0.2.0-rc.2，端口 9288（本轮只读确认，未修改）。
- 安装包：`C:/Users/19717/AppData/Roaming/in.dsh-plug.dsh-launcher/homes/0.2.0-rc.2/profiles/web/node_modules/dsh-annotation-core`，版本 **0.3.12-dsh02.2**。
- 对照源码：`D:/AI/DeepSeekHarness-Plugin/worktrees/dsh02rc2-20260929/dsh-annotation-core/src/client` 中 selection-toolbar、reference-rail、reference-dialog、reference-highlights、reference-badges、reference-text-index、conversation-node 和样式。
- 上一版参考的 repositories 目录 0.3.6 过旧。本轮改为当前安装版本对应代码。MIT 归属保留在 `THIRD_PARTY_NOTICES.md`。

## 已落实

- 选文菜单“添加到当前会话”，添加后直接打开输入框上方靠左的紧凑注释卡片，聚焦注释输入。
- 输入区收敛为一个数量气泡；悬停、点击或键盘聚焦展开逐条摘要，每条有编辑、跳转、删除。
- 多条引用在卡片内切换；Enter 保存并收起、Shift+Enter 换行；Esc/点击外部收起。中文输入法和长按回车不触发保存后的消息发送或数据库授权。
- 注释草稿持续保留，关闭卡片不丢字；按项目/会话隔离，刷新可恢复，发送失败保留。
- 原文精确选段高亮及角标，点角标打开同一编辑卡片。通过可选 occurrence 定位同文中的重复选段；旧历史缺少该字段仍兼容。
- 同一选段重复添加打开已有引用，不重复增加数量；不同出现位置可独立引用。
- 已发送消息只显示一个引用数量入口，回看只读，支持重新添加到当前提问。
- CSS Highlight + 外置角标，不改写 Markdown 消息 DOM。范围索引按消息缓存，滚动按可见区域测量，事件监听、观察器与缓存均随卸载释放。
- 长段落选择菜单钳制在会话可见范围内；附件右栏保持覆盖自己的区域。
- 轻量模仿只接入本应用会话引用；跨会话导入、Obsidian 回链和 DSH 其他插件扩展没有移植。

## 验证

- 类型检查、生产构建通过。原有大包体提醒仍在，无编译错误。
- `tests/annotations.test.ts` 三项通过，覆盖原引用约束、可选 occurrence 的合法性及旧消息兼容。
- `web/tests/annotation-dsh-parity.cjs` 隔离真实浏览器通过：自动打开/聚焦/位置、数量气泡及悬停列表、精确重复选段、卡片切换、草稿恢复、重复添加、流式及跨消息拒绝、失败发送保留、发送后回看/复用、移动端、与授权快捷键隔离。
- 隔离 DeepSeek 真实调用返回两条注释及其换行、追加内容；请求与落库记录保留 occurrence。首次浏览器检查在只读详情文本选择器上报严格匹配错误（与模型回复同文）；修正为限定详情卡片后复测通过。
- 正式 3001 只读浏览器检查通过：唯一附件流向入口、通高并列右栏、原 PDF 图片、新引用链路；没有向生产发送消息或写数据。
- 证据：`data/acceptance-annotation-dsh-20261004/` 中 checks.json、annotation-live-evidence.json、production-checks.json 和截图。
- 生产 PID 更新为 64808；更新前核对无 activeRunId 和待授权。用户原有内嵌页未重载，避免影响正在编写的内容。

## 完整年报

`samples/native-pdf/` 共 5 份、1220 个 PDF 页面：茅台 2024（143）、伊利 2023（265）/2024（270）、海尔智家 2024（247）、美的集团 2024（295）。美的从已有 benchmark 原始来源目录按字节复制，SHA-256 一致。其余四份复核原有哈希。

已检查原生文本、经营讨论、审计、财务主表与附注及代表性页面。美的三表为合并/公司并列、人民币千元，适合作口径压力测试。各文件完整性与页码见 pdf-inventory.json，原始披露来源在 samples/native-pdf/manifest.json。

分析题保存为 `samples/native-pdf/验收提问.md`：入库覆盖、茅台现金支持、伊利盈利质量与比较数、海尔供应链/现金周期、美的复杂表格、Python/CSV DCF、供应冲击和引用回查。未对五份完整报告重新执行全量模型入库，不以文件检查或引用 UI 通过宣称财务分析正确。

## 回退和隔离

- 源码备份 `data/backups/20261004-160346-before-dsh-reference-parity.zip`。
- SHA-256：444C4802071D77939040D4CEA8DCF49207FC84A2337B611730195B770FF1D635。
- 隔离目录 `data/acceptance-confirmed-annotation-20261004`；测试结束关闭独立 3003/5173 服务并删除该目录中临时复制的加密设置文件。保留测试记录，生产配置不动。

重新运行交互验收时，用 `web/tests/seed-annotation.py` 初始化新的 acceptance-confirmed 路径，按既有隔离启动方法启动 3003 后端和 5173 候选前端，再执行 annotation-dsh-parity.cjs。该测试包含一条明确限定不调用工具的真实模型请求。
