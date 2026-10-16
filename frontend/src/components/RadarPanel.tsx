import { Empty, Row, Col, Progress } from 'antd'

/**
 * 能力画像雷达图组件（纯 SVG，无第三方依赖）
 * 规则：
 *  - 维度数量 ≥ 3：用雷达图（八边形 / N边形）+ 右侧标签列表
 *  - 维度数量 < 3：用横向进度条（雷达图至少需要 3 个轴才有视觉意义）
 *  - 维度数量 = 0：Empty 占位
 * 分数配色：≥ 80 绿 / ≥ 60 橙 / < 60 红（与原 Progress 一致）
 */
export default function RadarPanel({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data || {})
    .map(([k, v]) => [k, Number(v) || 0] as [string, number])
  if (entries.length === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无维度数据" />
  }

  // < 3 个维度：退化为横向进度条列表
  if (entries.length < 3) {
    return (
      <Row gutter={[12, 8]}>
        {entries.map(([k, v]) => (
          <Col span={24} key={k}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
              <span>{k}</span>
              <strong>{v.toFixed(1)}</strong>
            </div>
            <Progress
              percent={Math.min(v, 100)} showInfo={false} size="small"
              strokeColor={v >= 80 ? '#52c41a' : v >= 60 ? '#f59e0b' : '#ef4444'}
            />
          </Col>
        ))}
      </Row>
    )
  }

  // ≥ 3 个维度：纯 SVG 雷达图
  const size = 280
  const cx = size / 2
  const cy = size / 2
  const radius = 100
  const n = entries.length
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n

  // 网格圈（4 层：25/50/75/100）
  const rings = [0.25, 0.5, 0.75, 1.0].map((scale) => {
    const pts = entries
      .map((_, i) => {
        const a = angle(i)
        return `${cx + Math.cos(a) * radius * scale},${cy + Math.sin(a) * radius * scale}`
      })
      .join(' ')
    return { scale, pts }
  })

  // 数据多边形
  const dataPts = entries
    .map(([, v], i) => {
      const a = angle(i)
      const r = (Math.min(v, 100) / 100) * radius
      return `${cx + Math.cos(a) * r},${cy + Math.sin(a) * r}`
    })
    .join(' ')

  // 轴线 + 标签
  const axes = entries.map(([k, v], i) => {
    const a = angle(i)
    const x2 = cx + Math.cos(a) * radius
    const y2 = cy + Math.sin(a) * radius
    // 标签位置：再外推 18px
    const lx = cx + Math.cos(a) * (radius + 18)
    const ly = cy + Math.sin(a) * (radius + 18)
    // 文字垂直对齐
    const dy = ly > cy + 6 ? 18 : ly < cy - 6 ? -4 : 6
    const anchor = lx > cx + 6 ? 'start' : lx < cx - 6 ? 'end' : 'middle'
    const color = v >= 80 ? '#52c41a' : v >= 60 ? '#f59e0b' : '#ef4444'
    return { x1: cx, y1: cy, x2, y2, lx, ly, label: k, score: v.toFixed(1), anchor, dy, color }
  })

  return (
    <Row gutter={16} align="middle">
      <Col flex="280px">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block', margin: '0 auto' }}>
          {/* 网格圈 */}
          {rings.map((r) => (
            <polygon
              key={r.scale}
              points={r.pts}
              fill="none"
              stroke="#e5e7eb"
              strokeWidth={1}
            />
          ))}
          {/* 轴线 */}
          {axes.map((a, i) => (
            <line key={i} x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2} stroke="#e5e7eb" strokeWidth={1} />
          ))}
          {/* 数据多边形 */}
          <polygon
            points={dataPts}
            fill="rgba(67, 97, 238, 0.18)"
            stroke="#4361ee"
            strokeWidth={2}
          />
          {/* 数据点 */}
          {entries.map(([, v], i) => {
            const a = angle(i)
            const r = (Math.min(v, 100) / 100) * radius
            const px = cx + Math.cos(a) * r
            const py = cy + Math.sin(a) * r
            const color = v >= 80 ? '#52c41a' : v >= 60 ? '#f59e0b' : '#ef4444'
            return <circle key={i} cx={px} cy={py} r={3.5} fill={color} stroke="#fff" strokeWidth={1.5} />
          })}
          {/* 标签 + 分数 */}
          {axes.map((a, i) => (
            <g key={`l${i}`}>
              <text
                x={a.lx} y={a.ly}
                textAnchor={a.anchor as any}
                fontSize={12}
                fill="#333"
                dy={a.dy}
              >
                {a.label}
              </text>
              <text
                x={a.lx} y={a.ly}
                textAnchor={a.anchor as any}
                fontSize={11}
                fill={a.color}
                fontWeight={600}
                dy={a.dy + 14}
              >
                {a.score}
              </text>
            </g>
          ))}
        </svg>
      </Col>
      <Col flex="auto">
        {/* 文字清单（雷达图区域小，文字清单保证可读性） */}
        <div style={{ fontSize: 12 }}>
          {entries.map(([k, v]) => (
            <div key={k} style={{
              display: 'flex', justifyContent: 'space-between',
              padding: '4px 0', borderBottom: '1px dashed #f0f0f0',
            }}>
              <span>{k}</span>
              <strong style={{
                color: v >= 80 ? '#52c41a' : v >= 60 ? '#f59e0b' : '#ef4444',
              }}>{v.toFixed(1)}</strong>
            </div>
          ))}
        </div>
      </Col>
    </Row>
  )
}