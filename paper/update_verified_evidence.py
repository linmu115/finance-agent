"""Add verified runtime evidence to the editable manuscript; never read benchmark gold."""
import json
from pathlib import Path

root=Path(__file__).resolve().parent
path=root/'manuscript.json'
data=json.loads(path.read_text(encoding='utf-8'))
blocks=data['blocks']
if not any(b.get('key')=='model_configuration' for b in blocks):
    index=next(i for i,b in enumerate(blocks) if b.get('text','').startswith('Node 控制层处理'))
    blocks.insert(index+1,{'type':'paragraph','key':'model_configuration','text':'本系统选用 DeepSeek 官方 DeepSeek-V4.1-Flash，API 标识为 deepseek-flash，服务地址为 https://api.deepseek.com，支持工具调用与思考模式[11]。模型名称依据官方文档和实际模型列表核验，密钥由 Node 加密保存并在运行时注入，不进入文档、数据库事实或分析容器。模型承担任务组织和文字解释，精确数字仍必须来自项目内的查询与计算工具。'})
for b in blocks:
    if b.get('key')=='integration_tests':
        b['text']='应用集成测试实际连接 Pi 与 MCP 服务，并使用模型协议测试桩检查工具调用、结果回传和运行事件；该检查证明接口协作，不衡量模型能力。前端另完成 14 项夹具检查与 10 项真实 API 检查。随后以官方 deepseek-flash 贯通浏览器、Node/Pi、Python 服务的真实测试通过 9 项检查，一次任务记录 6 次模型调用、9 次工具调用、耗时 13.432 秒，覆盖 Excel 上传、解析、对话、SSE、证据及持久化等行为。该输入为合成开发夹具，不属于回归集成绩。'
    if b.get('key')=='verification_layers':
        b['rows'][3][1]='14项夹具、10项API、9项真实模型交互'
        b['rows'][-1]=['运行与边界','实际容器及应用分项证据','按测试场景判断，不能外推所有攻击']
if not any(b.get('key')=='runtime_result' for b in blocks):
    index=next(i for i,b in enumerate(blocks) if b.get('key')=='model_result')
    blocks[index:index]=[
        {'type':'heading','level':2,'text':'6.3 隔离运行与故障恢复'},
        {'type':'paragraph','key':'runtime_result','text':'自由分析使用本机 Linux 虚拟机内的真实 Docker 运行，环境为 QEMU 10.2.0 与 WHPX 加速、Alpine 3.22、Linux 6.12.81、Docker 28.3.3。科学计算镜像以 SHA-256 标识固化。容器层 S01 至 S07 与 S10 共 8 项通过，覆盖依赖和中文字体、只读输入、受限写入、默认断网、超时和取消、资源限制、产物校验及制图。120 秒无限循环在 120.221 秒被终止；取消探针记录的容器执行时间为 0.559 秒。内存探针确实触发 OOMKilled，进程数限制为 64，超过 50 MiB 的输出和符号链接产物被拒绝。Linux 宿主的 11 项边界单测全部通过。'},
        {'type':'paragraph','text':'S10 的三家公司、每家公司两个年度营业收入，均来自解析服务导出的事实及其来源；容器产出的图表数据再由宿主独立对照标准答案，6 个数值全部一致，3 张中文图均完成目视检查。该实验验证确定性导出到真实容器制图的链路，不把参考数据库作为被测分析代码的输入，也不将绘图成功计为语言模型推理正确。'},
        {'type':'paragraph','key':'boundary_result','text':'项目隔离与恢复分别保留应用层和运行器证据。S08 中，跨项目文档、页面、表格、查询和财务计算的 9 个请求均被服务拒绝；容器运行、产物读取与取消也拒绝跨项目访问并留下审计记录。S11 实际终止解析进程后重新启动，任务能够从失败状态重新提交，143 页报告完成解析且未重复入库；另以 SIGKILL 终止宿主运行器验证容器任务的恢复处理。S09 使用真实 DeepSeek 读到含恶意指令的文档文本，任务完成，实际调用仍限制在白名单且项目由宿主绑定。单个注入探针通过仅支持这一场景，不意味着抵御所有提示注入。'},
        {'type':'heading','level':2,'text':'6.4 真实模型问答状态'},
    ]
if not any(b.get('text','').startswith('[11]') for b in blocks):
    blocks.append({'type':'reference','text':'[11] DeepSeek. 模型与价格；Models API. https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ ; https://api-docs.deepseek.com/api/list-models/ （访问日期 2026年10月3日；实际 API 标识 deepseek-flash）'})
path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated verified evidence; no model accuracy entered.')
