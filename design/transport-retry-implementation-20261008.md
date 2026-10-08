# 宿主瞬时传输重试：独立分支实施记录

状态：已在 `feat/transport-retry` 实现并通过离线验收；基线 F1.2 `3df658f`。未合并、未部署，未改变 3001、主库、Docker 或正式评测冻结版本。验收见 `docs/evidence/transport-retry-20261008/README.md`。

## 已确认

- N3 待办 `design/post-freeze-transport-retry-20261008.md` 的实际错误为 `stream error: stream disconnected before completion: stream closed before response.completed`，另有 TLS/500、上游 overloaded。最新授权覆盖该待办原先“冻结期间不实现”的时间安排，部署仍待评测后决定。
- 安装的 Pi 1.0.0 已有原生指数退避、失败尝试持久化、失败消息从模型上下文投影中移除及取消功能，但其分类器漏识别上述 stream 错误和部分 TLS 错误；无边界匹配 `500` 也过宽。
- 宿主现有每次 `streamSimple` 的 requestId、用量结算和预算需保留。失败无用量保持 unknown，不补零、不把准备成本当分析成本。

## 本轮实现范围

用宿主的原生 `message_end` 扩展分类主循环错误，公开 SettingsManager API 决定是否允许 Pi 重试。对 Pi 漏识别的明确传输错误加可识别的 `Network error` 前缀，保留完整原始错误；不改 Pi 私有方法。仍由 Pi 管理重试、会话和退避。主循环关闭 provider 内部不可逐次审计的隐式重试，每次原生尝试通过现有宿主用量管道。

连续同一模型步骤失败最多重试 3 次，等待 2/4/8 秒；成功响应后由 Pi 重置。该限制只针对未完成的模型步骤，不截断文档总长度。已完成工具结果继续复用；文档级无推进仍由已有入库机制独立判断。

## 验收与边界

新增验收使用纯本地脚本化 provider + Pi 原生 session + MCP stdio + 临时资料目录；覆盖成功、耗尽、业务错误不重试、用量未知、已完成工具不重放、预算停止和取消。新增测试不监听 HTTP。相关生命周期/绑定/用量/评测回归、类型检查与独立 worktree 构建；已有部分回归内部使用临时 loopback provider mock，随测试关闭，未启动另一产品服务。无付费调用和真实文档数据。

不另造外层 prompt 循环，不让模型判断网络重试，不将逻辑不推进视为传输故障。F1.3 合并、暂停、重新应用资料不属于本项；等协调通知后单独执行。
