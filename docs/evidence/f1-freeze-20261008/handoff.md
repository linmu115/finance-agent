# F1 正式评测冻结交接

本目录保存 F1 合并验收。精确提交与部署结果在提交后写入 **`data/evaluation/f1-freeze-20261008/manifest.json` 与 `handoff.md`**；现用冻结交接 `data/evaluation/analyst-freeze-20261008/` 同步为 F1，旧 58a903c 记录归档保留。提交前文档不预填未知的 SHA/PID，也不把构建成功称为已上线。

## 冻结范围与窗口

以 main `28cf04b` 合入精确 `2e27a108793babb2d1aca6ac54f54beb0ff8c84e`，包括 N4 采用修复、e2c1f46 评测隔离及 N3 按表搁置/末尾 high 修复、标识数字排除、来源维度、同表记录归档替换和准则重新应用。未移除功能，未增加模型确认轮次或固定任务总调用次数。

**F1 上线冻结起至第二期评测结束，main 不再合并会改变 3001 行为的代码。** 确需修改时先报告协调方，获准后记为新版本；保留 F1 commit/tree、产物和原始评测证据，不原地覆盖。继续入库属于本冻结版本下的资料准备，由 N3/N1 记录各批资料状态、费用和截止时间，不混入分析费用。

## N1：隔离键

每次 `POST /api/conversations/{id}/messages` 在现有 evaluation 增加：

```json
{
  "profile": "financial",
  "budget_group_id": "沿用本链已批准预算组",
  "isolation_key": "F1_batchUUID_D2_financial_r1",
  "budget": "沿用已批准的完整 budget 对象"
}
```

以上只展示字段位置；budget 需传原接口的对象，不是该说明字符串。完整可执行 JSON 形状见 [隔离键接口说明](../evaluation-isolation-20261008/handoff.md)。本轮没有新增付费预算授权。

- 每个批次、独立题链、组别、重复次序分配新键；键为 1–120 个 ASCII 字母、数字、下划线或连字符。不要复用彩排键。
- D2→D3、H1→H2 各自沿用本链的同一个键；所有续题和 steer/followUp 都显式携带。换组、换重复实验就换键和会话。
- 会话已有消息后改键或漏键返回 `409 evaluation_conversation_isolation_conflict`，不会追加消息或发模型请求；同键新会话允许读取本链成果。预算组独立于成果归属。
- 模型、报告、分析运行及交付 ID 的读取只见同键成果，旧无键成果不可见；跨键与不存在返回相同错误，不泄露文件清单或最新版本。无键产品会话仍按项目共享。
- 文档、原文页表、财务事实和研报记录共享。普通用户资产看板和下载 API 仍是产品项目级共享，不把评测范围说成用户账户权限隔离。
- 每题审计留存 `run_config.isolation_key`、请求中的 `evaluation`、实际工具序列与动态上下文。冻结哈希是空项目的静态模型说明；不替代正式项目资源/资料与真实请求留档。

## 验收与边界

首轮 Python 143/145 通过，原失败日志保留；补齐旧夹具 rows 后相关两模块复测 35/35 通过，最终各项均有通过记录，唯一 145 项。Node 19/19、类型检查、构建通过。部署产物在隔离空项目另跑 2/2 原生 Pi＋MCP 隔离回放，无真实模型请求、无新开测试 HTTP 端口，不操作生产事实和 Docker。

**保留已知问题：**FCFF 关键词检索可误匹配 record_json 中的来源哈希。此查询文件与合并前 28cf04b 完全相同；确定性合成复现返回两条 FCFF 加一条无关净利润记录，精确 metric 查询不受该复现影响。首次失败的临时库已清理，不能确认它的具体误匹配字段；不得以复测通过声称该问题消失。复现脚本和 JSON 均在本目录，留待协调方安排新版本修复。

N3 的复制库恢复、33 组维度重判与负面回放按原报告保留，不称为生产完整入库或模型续跑成功。本轮不执行年报续跑和第一期评测、不读取 held-out 材料、不发付费请求。

## 静态说明快照

| 配置 | 工具数 | 完整字符 | 粗估 token | 工具及说明组合 SHA-256（cwd 归一） |
|---|---:|---:|---:|---|
| financial | 40 | 30,869 | 10,116 | d5bef83ba05b5e87c32ba1bf29e71bc21fce6ccc81e619ea089a1665069830f5 |
| prepared | 13 | 9,521 | 3,011 | 14de7a45b1333602890ef258d00a1dc1aba5711b3394194a9056d87548a0452a |

`context-digests.json` 给出独立系统/工具哈希与完整工具列表。UTF-8 SHA-256；tools 保留顺序及 description/schema，组合为 JSON.stringify({system,tools})；仅归一化末尾随机 cwd。字符按 Unicode 码点，token=ceil(ASCII/4 + 非 ASCII)，不是账单。源码与部署产物快照完全匹配；advance_cleaning_round 宿主专用，financial_workpaper 只在金融组，prepared 共享入口完整。
