# 初赛介绍视频 · 制作脚本

成片：`submission/初赛提交包/02_项目介绍视频.mp4`（3:36，1920×1080，30fps，H.264 + AAC 48kHz）。

画面全部来自 3001 上的真实产品；卡片和执行轨迹叠加层用 HTML 逐帧渲染；旁白用 edge-tts（zh-CN-YunyangNeural），背景音由脚本合成，不存在授权问题。

## 流程

1. 录制（`rec/`）。用 Playwright 驱动 Chrome，通过 CDP screencast 抓取 1080p 帧，再用 `frames2mp4.py <take>` 合成 `raw.mp4`。
   - `take_tour.py`：附件看板 → 资产看板 → 现金流量表 → 跳回原文 → 估值模型。
   - `take_live.py`：现场提问并等待回答完成，同时记录会话 ID。这一步要调用一次真实模型，约 5 分钟。
   - `take_review.py --report`：回看同一会话，依次展示结论、现金桥、原文依据、能否持续、交付文件、工具记录，最后导出报告。
   - 录制时只在展示层过滤项目和会话列表，不展示 held-out 项目。
2. 卡片（`cards/`）。
   - 片头片尾和各说明卡：`render_cards.py <scene> <秒数>`。
   - 现场演示的执行轨迹叠加层：`render_trace.py`，由 `assemble.py` 自动调用。时间点取自该次运行的审计日志。
3. 旁白（`tts/`）。文案在 `narration.json`，运行 `gen_tts.py [id...]` 生成 mp3 和逐句时间轴。`d_review_core` 是 `d_review` 去掉最后一句后的版本。
4. 剪辑（`edit/assemble.py`）。按切点表剪辑、加速、叠加，再混入旁白和背景音，做响度归一（-16 LUFS），烧录字幕。

脚本里的路径按临时工作目录写成（`rec/takes`、`cards/frames` 等）。重做之前，请先把这几个目录和 ffmpeg 路径改成本机实际位置。
