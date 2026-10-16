import { useEffect, useState } from 'react'
import {
  Table, Button, Select, InputNumber, message, Space, Card, Tag, Row, Col,
  Typography, Statistic,
} from 'antd'
import {
  ThunderboltOutlined, ReloadOutlined, AimOutlined, TeamOutlined,
} from '@ant-design/icons'
import { listPositions, matchPosition, getPositionCandidates } from '../api'
import ModuleBanner from '../components/ModuleBanner'

export default function Matching() {
  const [positions, setPositions] = useState<any[]>([])
  const [positionId, setPositionId] = useState<number | undefined>()
  const [topN, setTopN] = useState(10)
  const [matching, setMatching] = useState(false)
  const [candidates, setCandidates] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [lastTotal, setLastTotal] = useState<number | undefined>()

  const loadPositions = async () => {
    try {
      const res = await listPositions({ page: 1, page_size: 100 })
      setPositions(res.items || [])
    } catch (e: any) {
      message.error(e.message || '加载岗位失败')
    }
  }

  const loadCandidates = async (pid = positionId, n = topN) => {
    if (!pid) return
    setLoading(true)
    try {
      const res = await getPositionCandidates(pid, n)
      setCandidates(res.items || [])
    } catch (e: any) {
      message.error(e.message || '加载候选人才失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPositions() }, [])  // eslint-disable-line

  const handleMatch = async () => {
    if (!positionId) { message.warning('请先选择岗位'); return }
    setMatching(true)
    try {
      const res = await matchPosition(positionId, topN)
      setLastTotal(res.total_candidates)
      message.success(`匹配完成，共评估 ${res.total_candidates} 名候选人`)
      loadCandidates()
    } catch (e: any) {
      message.error(e.message || '匹配失败')
    } finally {
      setMatching(false)
    }
  }

  const scoreColor = (s: number) => s >= 80 ? 'green' : s >= 60 ? 'orange' : 'red'

  const columns = [
    { title: '人才ID', dataIndex: 'talent_id', key: 'talent_id', width: 90 },
    {
      title: '姓名', dataIndex: 'talent_name', key: 'talent_name', width: 100,
      render: (v: string) => v || '-',
    },
    {
      title: '当前职位', dataIndex: 'current_position', key: 'current_position', ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '匹配分', dataIndex: 'match_score', key: 'match_score', width: 110,
      sorter: (a: any, b: any) => (a.match_score || 0) - (b.match_score || 0),
      defaultSortOrder: 'descend' as const,
      render: (s: number) => s != null ? <Tag color={scoreColor(s)}>{s}</Tag> : '-',
    },
    {
      title: '优势', dataIndex: 'strengths', key: 'strengths', ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '短板', dataIndex: 'weaknesses', key: 'weaknesses', ellipsis: true,
      render: (v: string) => v || '-',
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><AimOutlined /> 岗位匹配</Space>
      </Typography.Title>

      <ModuleBanner
        value="把「谁适合哪个岗位」讲清楚：自动对人才与岗位做匹配评估，输出匹配分、匹配依据与优势短板，招人用人有据可循。"
        relation="匹配承接档案与岗位，是人才配置的关键一步："
        prevLabel="人才档案"
        prevPath="/talents"
        nextLabel="测评管理"
        nextPath="/assessments"
      />

      <Card bordered={false} size="small">
        <Row gutter={12} align="middle">
          <Col flex="300px">
            <Select
              placeholder="选择岗位"
              value={positionId}
              onChange={(v) => { setPositionId(v); setLastTotal(undefined); if (v) loadCandidates(v) }}
              options={Array.from(
                positions
                  .reduce((m, p) => {
                    // 按 position_name 去重，保留第一个出现的 id
                    const name = p.position_name || p.position_code || `岗位#${p.id}`
                    if (!m.has(name)) m.set(name, { value: p.id, label: name })
                    return m
                  }, new Map<string, { value: number; label: string }>())
                  .values()
              ) as Array<{ value: number; label: string }>}
              showSearch
              optionFilterProp="label"
              style={{ width: '100%' }}
            />
          </Col>
          <Col>
            <Space align="center">
              <span style={{ lineHeight: '32px' }}>TopN:</span>
              <InputNumber min={1} max={50} value={topN} onChange={(v) => setTopN(v || 10)} style={{ width: 80 }} />
            </Space>
          </Col>
          <Col>
            <Space>
              <Button type="primary" icon={<ThunderboltOutlined />} loading={matching} onClick={handleMatch}>
                触发匹配
              </Button>
              <Button icon={<ReloadOutlined />} onClick={() => loadCandidates()} disabled={!positionId}>
                刷新结果
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {lastTotal !== undefined && (
        <Row gutter={16}>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic title="本次评估候选人数" value={lastTotal} prefix={<TeamOutlined />} />
            </Card>
          </Col>
          <Col span={6}>
            <Card bordered={false}>
              <Statistic title="当前展示" value={candidates.length} suffix={`/ Top${topN}`} />
            </Card>
          </Col>
        </Row>
      )}

      <Card bordered={false}>
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          匹配方式：先按学历、经验等基本条件初筛，再综合技能匹配度评分（满分100）。点击「触发匹配」即可对全部在岗/储备人才进行评估并记录结果。
        </Typography.Text>
        <Table
          rowKey="talent_id"
          loading={loading}
          dataSource={candidates}
          columns={columns}
          scroll={{ x: 800 }}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
          locale={{ emptyText: positionId ? '暂无匹配数据，请点击「触发匹配」' : '请先选择岗位' }}
        />
      </Card>
    </Space>
  )
}
