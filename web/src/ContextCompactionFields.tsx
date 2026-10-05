import { emptySettings, type Settings } from './types';

type Policy = NonNullable<Settings['runtime']['contextCompaction']>;

export default function ContextCompactionFields({ value, onChange }: { value?: Policy; onChange: (value: Policy) => void }) {
  const policy = { ...emptySettings.runtime.contextCompaction!, ...value };
  const update = (patch: Partial<Policy>) => onChange({ ...policy, ...patch });
  return <details className="advanced-settings">
    <summary>长会话 · 上下文压缩</summary>
    <p className="settings-description">Pi 使用当前主模型整理较早的对话，保留近期工作、来源索引和未完成任务。原消息与财报继续保存在项目中，压缩调用计入任务用量。</p>
    <label htmlFor="context-enabled">自动整理</label>
    <select id="context-enabled" value={policy.enabled ? 'on' : 'off'} onChange={event => update({ enabled: event.target.value === 'on' })}>
      <option value="on">开启</option><option value="off">关闭</option>
    </select>
    <label htmlFor="context-mode">窗口适配</label>
    <select id="context-mode" value={policy.mode||"manual"} onChange={event=>update({mode:event.target.value as "auto"|"manual"})}><option value="auto">按模型窗口自动调整（约 80%）</option><option value="manual">自定阈值</option></select>
    {policy.mode==='auto' && <p className="field-note">按选定模型的实际窗口计算触发位置，保留近期约 16% 的内容并预留输出余量。清洗和分析使用同一套 Pi 压缩配置。</p>}
    {policy.mode!=='auto'&&<>
    <label htmlFor="context-target">整理触发阈值 <span>tokens</span></label>
    <input id="context-target" type="number" min="4096" max="2000000" step="1024" value={policy.targetTokens} onChange={event => update({ targetTokens: Number(event.target.value) })} />
    <label htmlFor="context-recent">保留近期原文 <span>tokens</span></label>
    <input id="context-recent" type="number" min="1024" max="1000000" step="1024" value={policy.keepRecentTokens} onChange={event => update({ keepRecentTokens: Number(event.target.value) })} />
    </>}
    <p className="field-note">实际触发阈值会适配模型窗口。摘要帮助继续工作；核对财务数字时，模型仍可读取原页和已保存的成果。</p>
  </details>;
}
