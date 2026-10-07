# N2 A3/A5 本轮迭代

已确认：从 ced0cd5 建立 feat/charts-consistency，旧底稿提交保留于 feat/fin-workpapers。仅修改独立 worktree；不操作主目录文件、3001 或其他服务端口，不读取青岛啤酒 held-out。K2/K4 真实材料验收等待后续安排。

A3：两组共享 plot_runtime 默认 constrained layout，savefig 时修复图像/网格/柱体上的低对比文字，检测标题、文字、色条和子图的重叠；自动布局后仍有问题则精确返回文件、元素和面积。历史脚本及数据保持不变，在 Docker 回放 question6 的 24 个图版本并逐图目视核对。Docker 由主线启动和保持运行，本线只使用自己的沙箱容器。

A5：零模型观察扫描，扫描回答、Markdown 附件和 CSV 数值列/单位，与 A1 表及本轮实际查询到的来源比较，逐格对齐 Markdown 表；三组历史全部回放，分别报告已知缺陷检出和正确内容误报。任何回给模型或用户告警功能均不启用。N1 a5-adapter.py 已只读：通过 --mainline-result JSON 原样导入，不需修改适配器。

拒绝：用全局出现过同一数字证明语义正确、把无对应当作确定错误、按历史题号写检测分支、为了布局改动数据/刻度/色图，或遗漏无法自动修好的图。扫描器与历史已知缺陷评估器分开，评审答案不进入扫描算法。

初始环境：Docker Linux pipe 不存在；先完成本地实现和只读历史材料准备，Docker 可用后执行沙箱验收。必要性依据：直接启用 constrained layout 与历史 colorbar 后 tight_layout 调用存在真实的 Matplotlib 引擎切换冲突，须协调该调用，不能把绘图失败作为完成。
