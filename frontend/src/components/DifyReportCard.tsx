/**
 * DifyReportCard —— Dify 深度报告叠加层（通用组件，异步任务模式）
 *
 * 用途：在各 AI 业务场景结果区提供"AI 深度报告"按钮，点击后：
 * 1) 提交 Dify 报告任务（后端立即返回 task_id，后台线程跑 Dify 工作流）
 * 2) 前端定时轮询任务状态，完成后展示 markdown 报告
 *
 * 设计：
 * - 不改变主结果（本地 Agent 结构化数据仍驱动表格/雷达图）；
 * - Dify 工作流链路长（约 30s~数分钟），异步化避免阻塞用户操作；
 * - 失败/不可用仅隐藏报告，不影响本地功能。
 */
import { useState, useRef, useEffect } from 'react'
import { Card, Button, Alert, Spin, Typography } from 'antd'
import { ThunderboltOutlined, FileTextOutlined } from '@ant-design/icons'
import { agentDifyReportSubmit, agentDifyReportQuery } from '../api'

const { Text } = Typography

/** 轻量 markdown → HTML 片段（无第三方依赖；Dify 报告为 markdown）。 */
function mdToHtml(md: string): string {
  if (!md) return ''
  let text = md
  // 剥离 <think> 思考链（不展示给业务用户）
  text = text.replace(/<think>[\s\S]*?<\/think>/gi, '')
  const lines = text.split(/\r?\n/)
  const out: string[] = []
  let inList = false
  let inTable = false
  let inCode = false
  const esc = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\*\*/g, '')

  for (const rawLine of lines) {
    const line = rawLine.trimEnd()
    if (/^```/.test(line)) {
      inCode = !inCode
      continue
    }
    if (inCode) {
      out.push(`<div style="font-family:monospace;background:#f6f6f6;padding:2px 6px;border-radius:3px;font-size:12px">${esc(line)}</div>`)
      continue
    }
    if (!line.trim()) {
      if (inList) { out.push('</ul>'); inList = false }
      if (inTable) { out.push('</table>'); inTable = false }
      continue
    }
    if (/^#{1,4}\s/.test(line)) {
      if (inList) { out.push('</ul>'); inList = false }
      const lvl = line.match(/^(#+)/)![1].length
      const txt = esc(line.replace(/^#+\s*/, ''))
      out.push(`<div style="font-weight:600;font-size:${lvl === 1 ? 16 : lvl === 2 ? 14 : 13}px;margin:8px 0 4px">${txt}</div>`)
      continue
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      if (!inList) { out.push('<ul style="margin:4px 0;padding-left:18px">'); inList = true }
      out.push(`<li style="font-size:13px;line-height:1.7">${esc(line.replace(/^\s*[-*•]\s+/, ''))}</li>`)
      continue
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (!inList) { out.push('<ol style="margin:4px 0;padding-left:18px">'); inList = true }
      out.push(`<li style="font-size:13px;line-height:1.7">${esc(line.replace(/^\s*\d+\.\s+/, ''))}</li>`)
      continue
    }
    if (line.includes('|') && line.trim().startsWith('|')) {
      const cells = line.split('|').filter((c) => c.trim() !== '').map((c) => esc(c.trim()))
      const isSep = cells.every((c) => /^:?-+:?$/.test(c))
      if (isSep) continue
      if (!inTable) {
        out.push('<table style="border-collapse:collapse;margin:6px 0;width:100%;font-size:12px">')
        out.push('<tr>' + cells.map((c) => `<th style="border:1px solid #ddd;padding:4px 8px;background:#f5f5f5;text-align:left">${c}</th>`).join('') + '</tr>')
        inTable = true
      } else {
        out.push('<tr>' + cells.map((c) => `<td style="border:1px solid #eee;padding:4px 8px">${c}</td>`).join('') + '</tr>')
      }
      continue
    }
    if (inList) { out.push('</ul>'); inList = false }
    out.push(`<div style="font-size:13px;line-height:1.8;margin:2px 0">${esc(line)}</div>`)
  }
  if (inList) out.push('</ul>')
  if (inTable) out.push('</table>')
  return out.join('')
}

interface DifyReportCardProps {
  /** Dify agent 类型：assessment | matching | training | data_decision */
  agent: string
  /** 生成 Dify 工作流入参（本地结果就绪后调用） */
  buildInputs: () => Record<string, any>
  /** 展示用文案，如 'AI 深度研判报告' */
  title?: string
  /** 按钮前置说明 */
  hint?: string
}

export default function DifyReportCard({
  agent,
  buildInputs,
  title = 'AI 深度报告',
  hint = '由 Dify 工作流自动生成更详细的分析结论',
}: DifyReportCardProps) {
  const [loading, setLoading] = useState(false)
  const [report, setReport] = useState<string>('')
  const [error, setError] = useState<string>('')
  const [expanded, setExpanded] = useState(false)
  const timerRef = useRef<any>(null)

  // 清理轮询定时器（组件卸载时）
  const clearPolling = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }

  const handleGenerate = async () => {
    setLoading(true)
    setError('')
    setReport('')
    setExpanded(false)
    let taskId = ''
    try {
      const inputs = buildInputs()
      const res = await agentDifyReportSubmit(agent, inputs)
      if (!res?.task_id) {
        setError('Dify 报告任务提交失败，请稍后重试')
        setLoading(false)
        return
      }
      taskId = res.task_id
      // 轮询任务状态：每 5s 查一次，最多约 8 分钟
      let tries = 0
      const poll = async () => {
        tries += 1
        try {
          const q = await agentDifyReportQuery(taskId)
          if (q?.status === 'success' && q?.report) {
            clearPolling()
            setReport(q.report)
            setExpanded(true)
            setLoading(false)
          } else if (q?.status === 'failed') {
            clearPolling()
            setError(q?.message || 'Dify 深度报告生成失败')
            setLoading(false)
          } else if (tries >= 96) {
            // 8 分钟未完成，放弃
            clearPolling()
            setError('深度报告生成超时，请稍后重试')
            setLoading(false)
          }
        } catch (e: any) {
          // 单次轮询失败不中断，继续等；连续太多次才放弃
          if (tries >= 96) {
            clearPolling()
            setError('深度报告生成超时，请稍后重试')
            setLoading(false)
          }
        }
      }
      timerRef.current = setInterval(poll, 5000)
      poll() // 立即查一次
    } catch (e: any) {
      setError(e?.message || '深度报告生成失败')
      setLoading(false)
    }
  }

  // 组件卸载时清理轮询定时器
  useEffect(() => {
    return () => clearPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <Card
      size="small"
      type="inner"
      style={{ marginTop: 12, background: '#fafbff' }}
      title={
        <span style={{ fontSize: 13 }}>
          <FileTextOutlined style={{ color: '#7b5ce6', marginRight: 6 }} />
          {title}
          <span style={{ color: '#aaa', fontWeight: 400, marginLeft: 8, fontSize: 12 }}>{hint}</span>
        </span>
      }
      extra={
        <Button
          size="small"
          type="primary"
          ghost
          icon={<ThunderboltOutlined />}
          loading={loading}
          onClick={handleGenerate}
        >
          {loading ? 'Dify 深度分析中…' : '生成深度报告'}
        </Button>
      }
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <Spin />
          <div style={{ color: '#7b5ce6', marginTop: 8, fontSize: 13 }}>
            AI 正在深度研判，Dify 工作流约需 30~60 秒，请稍候…
          </div>
        </div>
      )}
      {error && !loading && <Alert type="warning" showIcon message={error} description="不影响上方本地结果，可稍后重试。" />}
      {report && !loading && expanded && (
        <div style={{ marginTop: 4 }}>
          <div
            style={{
              background: '#fff', border: '1px solid #e8e8f5', borderRadius: 6,
              padding: '10px 12px', maxHeight: 360, overflow: 'auto', color: '#333',
            }}
            dangerouslySetInnerHTML={{ __html: mdToHtml(report) }}
          />
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
            以上报告由 Dify 工作流智能体生成
          </Text>
        </div>
      )}
    </Card>
  )
}
