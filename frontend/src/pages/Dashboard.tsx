import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Col, Row, Statistic, List, Tag, Typography, Space, Empty, Alert, Progress, Badge, Pagination } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import {
  TeamOutlined,
  CheckCircleOutlined,
  SolutionOutlined,
  FileTextOutlined,
  WarningOutlined,
  BookOutlined,
  AimOutlined,
} from '@ant-design/icons'
import { Pie, Bar, Column, Gauge } from '@ant-design/charts'
import {
  dashboardOverview,
  dashboardTalentStructure,
  dashboardAlerts,
  dashboardSkillDistribution,
  dashboardAssessmentStatistics,
  dashboardTrainingStatistics,
  dashboardMatchingStatistics,
} from '../api'
import ModuleBanner from '../components/ModuleBanner'

const ALERT_TAG_COLORS: Record<string, string> = {  critical: 'red',
  warning: 'orange',
  info: 'blue',
}
const ALERT_LABELS: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '提示',
}

// 状态中英文映射
const STATUS_LABELS: Record<string, string> = {
  active: '在岗',
  reserve: '储备',
  resigned: '离职',
  on_leave: '休假',
}
const GENDER_LABELS: Record<string, string> = {
  male: '男',
  female: '女',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<any>(null)
  const [structure, setStructure] = useState<any>(null)
  const [alertsData, setAlertsData] = useState<any>(null)
  const [skillDist, setSkillDist] = useState<any>(null)
  const [assessStat, setAssessStat] = useState<any>(null)
  const [trainStat, setTrainStat] = useState<any>(null)
  const [matchStat, setMatchStat] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [alertPage, setAlertPage] = useState(1)
  const alertPageSize = 20

  useEffect(() => {
    Promise.all([
      dashboardOverview(),
      dashboardTalentStructure(),
      dashboardAlerts(),
      dashboardSkillDistribution(),
      dashboardAssessmentStatistics(),
      dashboardTrainingStatistics(),
      dashboardMatchingStatistics(),
    ])
      .then(([o, s, a, sk, as, tr, ms]) => {
        setOverview(o)
        setStructure(s)
        setAlertsData(a)
        setSkillDist(sk)
        setAssessStat(as)
        setTrainStat(tr)
        setMatchStat(ms)
      })
      .catch((e) => {
        setError(e?.message || '数据加载失败')
      })
      .finally(() => setLoading(false))
  }, [])

  // ── 学历结构饼图数据 ──
  const eduData: { type: string; value: number }[] = (() => {
    const byEdu = structure?.by_education || {}
    return Object.entries(byEdu).map(([k, v]) => ({ type: k, value: Number(v) || 0 }))
  })()

  // ── 人才状态分布饼图 ──
  const statusData: { type: string; value: number }[] = (() => {
    const byStatus = structure?.by_status || {}
    return Object.entries(byStatus).map(([k, v]) => ({
      type: STATUS_LABELS[k] || k,
      value: Number(v) || 0,
    }))
  })()

  // ── 性别分布饼图 ──
  const genderData: { type: string; value: number }[] = (() => {
    const byGender = structure?.by_gender || {}
    return Object.entries(byGender).map(([k, v]) => ({
      type: GENDER_LABELS[k] || k,
      value: Number(v) || 0,
    }))
  })()

  // ── 工作年限分布柱状图 ──
  const expData: { category: string; value: number }[] = (() => {
    const byExp = structure?.by_experience || {}
    return Object.entries(byExp).map(([k, v]) => ({ category: k, value: Number(v) || 0 }))
  })()

  // ── 技能分布 TOP10 横向柱状图 ──
  const SKILL_COLORS = [
    '#4361ee', '#52c41a', '#faad14', '#eb2f96', '#722ed1',
    '#13c2c2', '#f5222d', '#2f54eb', '#a0d911', '#fa8c16',
  ]
  const skillData: { skill: string; count: number; color: string }[] = (() => {
    const list = skillDist?.skill_distribution || []
    return list.slice(0, 10).map((s: any, i: number) => ({
      skill: s.skill,
      count: s.count,
      color: SKILL_COLORS[i % SKILL_COLORS.length],
    }))
  })()

  // 在岗占比
  const totalTalents = overview?.total_talents ?? 0
  const activeTalents = overview?.active_talents ?? 0
  const activePercent = totalTalents > 0 ? Math.round((activeTalents / totalTalents) * 100) : 0

  const alerts = alertsData?.alerts || []

  // 智能预警前端分页（每页 20 条）
  const alertTotal = alerts.length
  const alertPageData = alerts.slice((alertPage - 1) * alertPageSize, alertPage * alertPageSize)

  // 培训完成率（用于 Gauge）
  const trainCompletionRate = trainStat?.completion_rate ?? 0
  const examPassRate = trainStat?.exam_pass_rate ?? 0

  // 测评合格率（用于 Gauge）
  const assessPassRate = assessStat?.pass_rate ?? 0

  // 匹配平均分
  const avgMatchScore = matchStat?.average_match_score ?? 0

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        全局工作台
      </Typography.Title>

      <ModuleBanner
        value="管理者的全局视图：总览人才结构、测评/培训/匹配运行情况，并自动预警人才风险（断层、短板、流失）。"
        relation="从这里出发，可下钻到人才管理的每个环节："
        nextLabel="人才档案"
        nextPath="/talents"
      />

      {error && <Alert type="error" message={error} showIcon closable onClose={() => setError(null)} />}

      {/* 第一行：核心统计卡片 */}
      <Row gutter={16}>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable loading={loading}>
            <Statistic
              title="人才总量"
              value={totalTalents}
              prefix={<TeamOutlined style={{ color: '#4361ee' }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable loading={loading}>
            <Statistic
              title="在岗人才"
              value={activeTalents}
              valueStyle={{ color: '#22c55e' }}
              prefix={<CheckCircleOutlined />}
            />
            <Progress percent={activePercent} size="small" status="active" />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable loading={loading}>
            <Statistic
              title="岗位数量"
              value={overview?.total_positions ?? 0}
              prefix={<SolutionOutlined style={{ color: '#f59e0b' }} />}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              招聘中 {overview?.open_positions ?? 0} 个
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card hoverable loading={loading}>
            <Statistic
              title="测评完成"
              value={overview?.total_assessments ?? 0}
              prefix={<FileTextOutlined style={{ color: '#9333ea' }} />}
            />
          </Card>
        </Col>
      </Row>

      {/* 第二行：学历结构 + 人才状态 + 性别分布（三个饼图） */}
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="人才学历结构" bordered={false} loading={loading}>
            {eduData.length > 0 ? (
              <Pie
                data={eduData}
                angleField="value"
                colorField="type"
                radius={0.8}
                innerRadius={0.5}
                label={{
                  text: (d: any) => `${d.type}: ${d.value}`,
                  position: 'outside',
                } as any}
                legend={{ position: 'right' }}
                height={280}
              />
            ) : (
              <Empty description="暂无学历结构数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="人才状态分布" bordered={false} loading={loading}>
            {statusData.length > 0 ? (
              <Pie
                data={statusData}
                angleField="value"
                colorField="type"
                radius={0.8}
                innerRadius={0.5}
                label={{
                  text: (d: any) => `${d.type}: ${d.value}`,
                  position: 'outside',
                } as any}
                legend={{ position: 'right' }}
                height={280}
              />
            ) : (
              <Empty description="暂无状态数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="性别比例" bordered={false} loading={loading}>
            {genderData.length > 0 ? (
              <Pie
                data={genderData}
                angleField="value"
                colorField="type"
                radius={0.8}
                innerRadius={0.5}
                label={{
                  text: (d: any) => `${d.type}: ${d.value}`,
                  position: 'outside',
                } as any}
                legend={{ position: 'right' }}
                height={280}
              />
            ) : (
              <Empty description="暂无性别数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 第三行：工作年限分布 + 技能分布 TOP10 */}
      <Row gutter={16}>
        <Col xs={24} lg={10}>
          <Card title="工作年限分布" bordered={false} loading={loading}>
            {expData.length > 0 ? (
              <Column
                data={expData}
                xField="category"
                yField="value"
                label={{ text: 'value', position: 'top' } as any}
                color="#4361ee"
                height={300}
              />
            ) : (
              <Empty description="暂无年限数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card title="技能分布 TOP 10" bordered={false} loading={loading}>
            {skillData.length > 0 ? (
              <Bar
                data={skillData}
                xField="count"
                yField="skill"
                color={({ skill }: any) => {
                  const idx = skillData.findIndex((d) => d.skill === skill)
                  return SKILL_COLORS[idx % SKILL_COLORS.length]
                }}
                legend={false}
                label={{ text: 'count', position: 'right', style: { fontWeight: 600 } } as any}
                height={300}
                style={{
                  radius: [0, 6, 6, 0],
                  opacity: 0.92,
                } as any}
              />
            ) : (
              <Empty description="暂无技能数据" />
            )}
          </Card>
        </Col>
      </Row>

      {/* 第四行：测评统计 + 培训完成率 + 匹配统计（三个 Gauge 仪表盘） */}
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card
            title={<Space><FileTextOutlined style={{ color: '#9333ea' }} />测评合格率</Space>}
            bordered={false}
            loading={loading}
          >
            <Row gutter={8} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic title="测评总数" value={assessStat?.total_assessments ?? 0} />
              </Col>
              <Col span={8}>
                <Statistic title="合格人数" value={assessStat?.passed_count ?? 0} valueStyle={{ color: '#22c55e' }} />
              </Col>
              <Col span={8}>
                <Statistic title="平均分" value={assessStat?.average_score ?? 0} valueStyle={{ color: '#4361ee' }} />
              </Col>
            </Row>
            <Gauge
              percent={assessPassRate / 100}
              range={{ color: ['#ef4444', '#f59e0b', '#22c55e'] }}
              style={{ height: 200 }}
            />
            <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center' }}>
              合格率 {assessPassRate}%
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            title={<Space><BookOutlined style={{ color: '#f59e0b' }} />培训完成率</Space>}
            bordered={false}
            loading={loading}
          >
            <Row gutter={8} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic title="学习记录" value={trainStat?.total_learning ?? 0} />
              </Col>
              <Col span={8}>
                <Statistic title="已完成" value={trainStat?.completed_learning ?? 0} valueStyle={{ color: '#22c55e' }} />
              </Col>
              <Col span={8}>
                <Statistic title="课程数" value={trainStat?.total_courses ?? 0} valueStyle={{ color: '#4361ee' }} />
              </Col>
            </Row>
            <Gauge
              percent={trainCompletionRate / 100}
              range={{ color: ['#ef4444', '#f59e0b', '#22c55e'] }}
              style={{ height: 200 }}
            />
            <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center' }}>
              完成率 {trainCompletionRate}% ｜ 考核通过率 {examPassRate}%
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card
            title={<Space><AimOutlined style={{ color: '#4361ee' }} />岗位匹配统计</Space>}
            bordered={false}
            loading={loading}
          >
            <Row gutter={8} style={{ marginBottom: 12 }}>
              <Col span={8}>
                <Statistic title="匹配总数" value={matchStat?.total_matches ?? 0} />
              </Col>
              <Col span={8}>
                <Statistic title="高匹配数" value={matchStat?.high_match_count ?? 0} valueStyle={{ color: '#22c55e' }} />
              </Col>
              <Col span={8}>
                <Statistic title="平均分" value={avgMatchScore} valueStyle={{ color: '#4361ee' }} />
              </Col>
            </Row>
            <Gauge
              percent={Math.min(avgMatchScore / 100, 1)}
              range={{ color: ['#ef4444', '#f59e0b', '#22c55e'] }}
              style={{ height: 200 }}
            />
            <Typography.Text type="secondary" style={{ display: 'block', textAlign: 'center' }}>
              平均匹配度 {avgMatchScore} 分
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      {/* 第五行：智能预警（带严重程度统计） */}
      <Row gutter={16}>
        <Col xs={24}>
          <Card
            title={
              <Space>
                <WarningOutlined style={{ color: '#ef4444' }} />
                智能预警
                {alertsData && (
                  <Space size="small">
                    {alertsData.critical_count > 0 && (
                      <Badge count={alertsData.critical_count} style={{ backgroundColor: '#ef4444' }} />
                    )}
                    {alertsData.warning_count > 0 && (
                      <Badge count={alertsData.warning_count} style={{ backgroundColor: '#f59e0b' }} />
                    )}
                    {alertsData.info_count > 0 && (
                      <Badge count={alertsData.info_count} style={{ backgroundColor: '#3b82f6' }} />
                    )}
                  </Space>
                )}
              </Space>
            }
            bordered={false}
            extra={
              alertsData ? (
                <Typography.Text type="secondary">共 {alertsData.total ?? 0} 条预警</Typography.Text>
              ) : null
            }
          >
            <List
              loading={loading}
              dataSource={alertPageData}
              locale={{ emptyText: <Empty description="暂无预警" /> }}
              renderItem={(item: any) => {
                const level = (item.level || item.type || 'info').toLowerCase()
                const goMap: Record<string, string> = {
                  position_gap: '/positions',
                  training_lag: '/training',
                  assessment_anomaly: '/assessments',
                }
                const target = goMap[item.type]
                return (
                  <List.Item
                    actions={target ? [
                      <Typography.Link key="go" onClick={() => navigate(target)} style={{ whiteSpace: 'nowrap' }}>
                        去处理 <RightOutlined style={{ fontSize: 10 }} />
                      </Typography.Link>,
                    ] : []}
                  >
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <Space>
                        <Tag color={ALERT_TAG_COLORS[level] || 'default'}>
                          {ALERT_LABELS[level] || level}
                        </Tag>
                        <Typography.Text strong style={{ marginRight: 8 }}>
                          {item.title || ''}
                        </Typography.Text>
                        <span>{item.detail || item.message || ''}</span>
                      </Space>
                      {item.created_at && (
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {item.created_at}
                        </Typography.Text>
                      )}
                    </Space>
                  </List.Item>
                )
              }}
            />
            {alertTotal > alertPageSize && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                <Pagination
                  current={alertPage}
                  pageSize={alertPageSize}
                  total={alertTotal}
                  showSizeChanger={false}
                  onChange={(p) => setAlertPage(p)}
                  showTotal={(t) => `共 ${t} 条`}
                />
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
