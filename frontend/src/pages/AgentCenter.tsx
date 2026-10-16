import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Row, Col, Button, Input, Select, Upload, message, Space,
  Tag, Typography, Statistic, Progress, Table, Empty, notification, Alert,
  List, Modal, Descriptions, Spin,
} from 'antd'
import {
  InboxOutlined, TeamOutlined, AimOutlined, BarChartOutlined,
  ThunderboltOutlined, RocketOutlined, DatabaseOutlined,
  CheckCircleFilled, ArrowRightOutlined, HistoryOutlined, UserOutlined, BookOutlined,
} from '@ant-design/icons'
import type { UploadRequestOption } from 'rc-upload/lib/interface'
import {
  parseResumeFile, listTalents, listPositions, listAssessmentResults,
  agentMatchPosition, agentMatchTalent, agentRecommendTraining, agentNl2sql,
  agentAnalyzeAssessment, getTalent,
} from '../api'
import ModuleBanner from '../components/ModuleBanner'
import RadarPanel from '../components/RadarPanel'
import DifyReportCard from '../components/DifyReportCard'

const { Dragger } = Upload

/** 业务场景定义（对标北森/理聘：以"业务场景"包装 AI 能力） */
const SCENARIOS = [
  {
    key: 'recruit',
    icon: <RocketOutlined />,
    color: '#4361ee',
    title: '招聘新员工',
    desc: '上传一份简历，系统自动帮你建档、研判能力、推荐岗位、规划培养，一条龙出报告',
    primary: true,
  },
  {
    key: 'find',
    icon: <AimOutlined />,
    color: '#06b6d4',
    title: '快速找人',
    desc: '描述岗位需求（技能/经验/学历），系统从人才库中推荐最匹配的人选，附匹配分和理由',
    primary: false,
  },
  {
    key: 'assess',
    icon: <BarChartOutlined />,
    color: '#7b5ce6',
    title: '盘点人才库',
    desc: '批量分析人才能力分布，识别高潜/核心/待发展梯队，为人才规划提供依据',
    primary: false,
  },
  {
    key: 'ask',
    icon: <DatabaseOutlined />,
    color: '#f59e0b',
    title: '数据参谋',
    desc: '一句话问数（"本月新进多少本科人才？"），自动查库出报告，免去手工做表',
    primary: false,
  },
]

export default function AgentCenter() {
  const navigate = useNavigate()
  const [activeKey, setActiveKey] = useState<string>('recruit')

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><TeamOutlined /> AI 智能场景中心</Space>
      </Typography.Title>

      <ModuleBanner
        value="AI 帮你做四件事：招人时一键从简历到岗位推荐，盘点人才时看梯队，做决策时一句话问数。底层是 5 个协同的 AI 智能体，前台按业务场景包装——你怎么方便怎么用。"
        relation="它驱动各业务板块的智能能力："
        nextLabel="岗位匹配"
        nextPath="/matching"
      />

      {/* 业务场景卡组 */}
      <Row gutter={16}>
        {SCENARIOS.map((s) => (
          <Col xs={24} sm={12} lg={6} key={s.key}>
            <Card
              hoverable
              onClick={() => setActiveKey(s.key)}
              style={{
                height: '100%',
                borderColor: activeKey === s.key ? s.color : '#f0f0f0',
                borderWidth: activeKey === s.key ? 2 : 1,
                background: activeKey === s.key ? `${s.color}08` : '#fff',
                cursor: 'pointer',
              }}
              styles={{ body: { padding: 16 } }}
            >
              <Space direction="vertical" size={8} style={{ width: '100%' }}>
                <Space>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 40, height: 40, borderRadius: 10,
                    background: `${s.color}15`, color: s.color, fontSize: 20,
                  }}>{s.icon}</span>
                  <Typography.Text strong style={{ fontSize: 15 }}>{s.title}</Typography.Text>
                </Space>
                <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0, minHeight: 48 }}>
                  {s.desc}
                </Typography.Paragraph>
                <Button
                  type={activeKey === s.key ? 'primary' : 'default'}
                  size="small"
                  block
                  style={activeKey === s.key ? { background: s.color, borderColor: s.color } : undefined}
                  icon={activeKey === s.key ? <CheckCircleFilled /> : <ArrowRightOutlined />}
                >
                  {activeKey === s.key ? '正在使用' : '开始使用'}
                </Button>
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 当前场景的展开面板 */}
      {activeKey === 'recruit' && <RecruitPanel />}
      {activeKey === 'find' && <FindPanelReal navigate={navigate} />}
      {activeKey === 'assess' && <AssessPanelReal />}
      {activeKey === 'ask' && <AskPanel />}

      {/* 平台能力透传 */}
      <Card
        size="small"
        title={<Space><HistoryOutlined /> 平台底层能力（5 大智能体协同）</Space>}
        style={{ background: '#fafafa' }}
      >
        <Row gutter={[12, 8]}>
          {[
            { name: '简历建档', color: '#4361ee', desc: '多格式解析 + 字段提取 + 标签画像' },
            { name: '能力研判', color: '#7b5ce6', desc: '测评结果 + 能力维度 + 短板分析' },
            { name: '岗位匹配', color: '#06b6d4', desc: '基本条件初筛 + 智能匹配 + 匹配分' },
            { name: '培养规划', color: '#f59e0b', desc: '缺口诊断 + 课程推荐 + 学习路径' },
            { name: '数据参谋', color: '#ef4444', desc: '自然语言问数 + 自动报告' },
          ].map((c) => (
            <Col xs={12} sm={8} md={4} lg={4} key={c.name}>
              <div style={{ padding: 6 }}>
                <Tag color={c.color} style={{ marginBottom: 2 }}>{c.name}</Tag>
                <div style={{ fontSize: 11, color: '#94a3b8' }}>{c.desc}</div>
              </div>
            </Col>
          ))}
        </Row>
      </Card>
    </Space>
  )
}

// ==================== 场景① 招聘新员工 ====================
function RecruitPanel() {
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<any>(null)
  const [autoAssess, setAutoAssess] = useState<any>(null)
  const [autoMatch, setAutoMatch] = useState<any>(null)
  const [autoTraining, setAutoTraining] = useState<any>(null)
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [talentId, setTalentId] = useState<number | undefined>()

  const handleUpload = async (options: UploadRequestOption) => {
    const { file, onSuccess, onError } = options
    const f = file as File
    // 前端预校验：仅支持 PDF / Word / 图片
    const ext = (f.name || '').toLowerCase().match(/\.[^.]+$/)?.[0] || ''
    const ALLOWED = ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg']
    if (!ALLOWED.includes(ext)) {
      const hint = `不支持的简历格式「${ext || '无扩展名'}」\n仅支持 PDF / Word / 图片（PNG / JPG）`
      notification.warning({ message: '简历格式不支持', description: hint, placement: 'topRight', duration: 5 })
      onError && onError(new Error(hint))
      return
    }
    setUploading(true); setProgress(0)
    setResult(null); setAutoAssess(null); setAutoMatch(null); setAutoTraining(null)
    setTalentId(undefined)
    try {
      const res = await parseResumeFile(f, (pct) => setProgress(pct))
      setResult(res)
      const tid = res?.created_talent_id
      if (tid) {
        setTalentId(tid)
        message.success('简历已建档，AI 正在自动跑完画像/匹配/培养方案…')
        setPipelineRunning(true)
        // 三件套并发：测评/匹配/培训（测评若无结果会降级，不阻塞其他）
        let latestResultId: number | undefined
        try {
          const r = await listAssessmentResults({ talent_id: tid, page: 1, page_size: 1 })
          latestResultId = r?.items?.[0]?.id
        } catch {}
        const tasks: [Promise<any>, string][] = []
        if (latestResultId) tasks.push([agentAnalyzeAssessment(latestResultId), 'assess'])
        tasks.push([agentMatchTalent(tid), 'match'])
        tasks.push([agentRecommendTraining(tid), 'training'])
        const results = await Promise.allSettled(tasks.map(([p]) => p))
        for (let i = 0; i < tasks.length; i++) {
          const [, name] = tasks[i]
          const r = results[i]
          const v = r.status === 'fulfilled' ? r.value : { success: false, message: (r as any).reason?.message || '失败' }
          if (name === 'assess') setAutoAssess(v)
          else if (name === 'match') setAutoMatch(v)
          else if (name === 'training') setAutoTraining(v)
        }
        setPipelineRunning(false)
        if (!latestResultId) {
          message.info('该人才暂无测评记录，能力研判暂不可用。匹配/培养方案已生成。', 5)
        }
      } else {
        message.warning('简历解析完成，但未生成人才档案（可能手机号已存在或解析失败）')
      }
      onSuccess?.(res, f)
    } catch (e: any) {
      setResult({ success: false, message: e.message })
      message.error(e.message || '解析失败')
      onError?.(e)
    } finally {
      setUploading(false)
    }
  }

  const td = result?.talent_data || {}
  const portrait = result?.portrait || {}
  const portraitDims = [
    ['technical_ability', '技术'], ['management_ability', '管理'],
    ['communication_ability', '沟通'], ['innovation_ability', '创新'],
    ['teamwork_ability', '协作'], ['learning_ability', '学习'],
  ].filter(([k]) => portrait[k] !== undefined).map(([k, label]) => ({ k, label, score: portrait[k] }))

  return (
    <Row gutter={16}>
      <Col xs={24} lg={10}>
        <Card title={<Space><RocketOutlined /> 招聘新员工 · 一条龙研判</Space>}>
          <Dragger
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            multiple={false}
            showUploadList={false}
            customRequest={handleUpload}
            disabled={uploading}
            style={{ padding: '24px 0', background: '#fafbff' }}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined style={{ color: '#4361ee', fontSize: 48 }} /></p>
            <p className="ant-upload-text" style={{ fontSize: 15, fontWeight: 500 }}>拖拽简历到这里，或点击上传</p>
            <p className="ant-upload-hint" style={{ color: '#999', fontSize: 12 }}>支持 PDF / Word / 图片；上传后系统自动建档+画像+匹配+培养方案</p>
          </Dragger>
          {uploading && <Progress percent={progress} status="active" strokeColor="#4361ee" style={{ marginTop: 12 }} />}
          {talentId && (
            <Alert style={{ marginTop: 12 }} type="success" showIcon
              message={`已为 "${td.name || '人才'}" (ID: ${talentId}) 生成完整研判报告`} />
          )}
        </Card>
      </Col>

      <Col xs={24} lg={14}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {pipelineRunning && (
            <Card><Space><ThunderboltOutlined spin style={{ color: '#4361ee' }} /><span>AI 正在跑完画像/匹配/培养方案（约 30-60 秒）…</span></Space></Card>
          )}

          {/* 首屏空态引导：未上传简历时，告诉用户这里将展示什么 */}
          {!td.name && !pipelineRunning && (
            <Card style={{ background: 'linear-gradient(120deg,#f6f8ff,#f0f5ff)', border: '1px dashed #b3c6ff' }}>
              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                <Typography.Text strong><CheckCircleFilled style={{ color: '#4361ee' }} /> 上传简历后，这里会为你依次生成：</Typography.Text>
                <Space size={12} wrap>
                  {[
                    { ic: <UserOutlined />, t: '① 人才画像', c: '#4361ee' },
                    { ic: <BarChartOutlined />, t: '② 能力研判', c: '#7b5ce6' },
                    { ic: <AimOutlined />, t: '③ 岗位匹配', c: '#06b6d4' },
                    { ic: <BookOutlined />, t: '④ 培养规划', c: '#f59e0b' },
                  ].map((x) => (
                    <Tag key={x.t} style={{ padding: '6px 12px', background: '#fff', borderRadius: 8, fontSize: 13 }}>
                      <span style={{ color: x.c, marginRight: 4 }}>{x.ic}</span>{x.t}
                    </Tag>
                  ))}
                </Space>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  仅需一份简历（PDF / Word / 图片），系统自动完成从建档到培养的完整人才研判报告。
                </Typography.Text>
              </Space>
            </Card>
          )}

          {/* 人才档案与画像 */}
          {td.name && (
            <Card size="small" title={<Space><UserOutlined /> 人才画像</Space>}>
              <Row gutter={[8, 6]}>
                <Col span={8}><Statistic title="姓名" value={td.name} valueStyle={{ fontSize: 14 }} /></Col>
                <Col span={8}><Statistic title="工作年限" value={`${td.experience_years || 0} 年`} valueStyle={{ fontSize: 14 }} /></Col>
                <Col span={8}><Statistic title="学历" value={td.education || '-'} valueStyle={{ fontSize: 14 }} /></Col>
                <Col span={12}><Statistic title="当前职位" value={td.current_position || '-'} valueStyle={{ fontSize: 14 }} /></Col>
                <Col span={12}><Statistic title="当前公司" value={td.current_company || '-'} valueStyle={{ fontSize: 14 }} /></Col>
              </Row>
              {result?.tags && result.tags.length > 0 && (
                <div style={{ marginTop: 10 }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>人才标签：</Typography.Text>
                  <div style={{ marginTop: 4 }}><Space wrap size={4}>{result.tags.slice(0, 12).map((t: string, i: number) => <Tag key={i} color="blue">{t}</Tag>)}</Space></div>
                </div>
              )}
              {portraitDims.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>AI 六维能力画像：</Typography.Text>
                  <Row gutter={[8, 6]} style={{ marginTop: 6 }}>
                    {portraitDims.map((d: any) => (
                      <Col span={12} key={d.k}>
                        <div style={{ fontSize: 12, display: 'flex', justifyContent: 'space-between' }}>
                          <span>{d.label}能力</span><strong>{d.score}</strong>
                        </div>
                        <Progress percent={Math.min(Number(d.score) || 0, 100)} showInfo={false} size="small" />
                      </Col>
                    ))}
                  </Row>
                </div>
              )}
              {portrait.summary && (
                <Alert style={{ marginTop: 8 }} type="info" showIcon={false}
                  message="综合评价" description={portrait.summary} />
              )}
            </Card>
          )}

          {/* 能力研判 */}
          {autoAssess && <ResultBlock title="能力研判" icon={<BarChartOutlined />} color="#7b5ce6" data={autoAssess} render={(d) => {
            const lvl = d.ability_level
            const levelLabels: Record<string, string> = { core: '核心人才', backbone: '骨干', senior: '高级', intermediate: '中级', junior: '初级', entry: '入门' }
            const lvlLabel = levelLabels[String(lvl)] || lvl
            return (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <div><Tag color="purple">{lvlLabel || d.ability_level || '暂无结果'}</Tag> <span style={{ color: '#999', fontSize: 12 }}>综合能力评级</span></div>
                {d.total_score !== undefined && <div style={{ fontSize: 12, color: '#666' }}>得分 {d.total_score} · 正确率 {d.correct_rate?.toFixed?.(0) || d.correct_rate}%</div>}
                {d.strengths && d.strengths.length > 0 && <div style={{ fontSize: 12 }}><span style={{ color: '#52c41a' }}>优势：</span>{d.strengths.slice(0, 3).join('、')}</div>}
                {d.weaknesses && d.weaknesses.length > 0 && <div style={{ fontSize: 12 }}><span style={{ color: '#fa8c16' }}>短板：</span>{d.weaknesses.slice(0, 3).join('、')}</div>}
                {(!d.ability_level && (d.errors || d.message)) && <Alert type="warning" showIcon message={d.errors?.[0] || d.message || '暂无测评结果'} description="可到「测评管理」为该人才创建测评任务" />}
              </Space>
            )
          }} />}

          {/* 岗位匹配 */}
          {autoMatch && <ResultBlock title="岗位匹配" icon={<AimOutlined />} color="#06b6d4" data={autoMatch} render={(d) => {
            const results: any[] = Array.isArray(d.match_results) ? d.match_results : []
            return results.length > 0 ? (
              <Table size="small" pagination={false} dataSource={results.slice(0, 5)} rowKey={(r) => String(r.position_id || r.id)}
                columns={[
                  { title: '岗位', dataIndex: 'position_name', key: 'position_name' },
                  { title: '分', dataIndex: 'final_score', key: 'score', width: 60,
                    render: (v) => v !== undefined ? <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}</Tag> : '-' },
                  { title: '理由', dataIndex: 'match_reason', key: 'reason', ellipsis: true },
                ]} />
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可匹配岗位" />
          }} />}

          {/* 培养规划 */}
          {autoTraining && <ResultBlock title="培养规划" icon={<BarChartOutlined />} color="#f59e0b" data={autoTraining} render={(d) => {
            const courses = d.recommended_courses || []
            return courses.length > 0 ? (
              <Space wrap size={4}>{courses.slice(0, 6).map((c: any, i: number) => <Tag key={i} color="orange">{c.course_name}</Tag>)}</Space>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无培训建议" />
          }} />}

          {/* Dify 智能体深度报告叠加（按需触发，本地三件套之上再生成深度报告） */}
          {talentId && (
            <>
              <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
                由 Dify 工作流智能体生成更完整的岗位匹配与培养方案深度报告（约 30~60 秒）：
              </Typography.Text>
              <DifyReportCard
                agent="matching"
                title="岗位匹配深度报告"
                hint="Dify 岗位匹配智能体"
                buildInputs={() => ({ talent_id: String(talentId) })}
              />
              <DifyReportCard
                agent="training"
                title="个人培养深度报告"
                hint="Dify 培训赋能智能体"
                buildInputs={() => ({ talent_id: String(talentId) })}
              />
            </>
          )}
        </Space>
      </Col>
    </Row>
  )
}

// ==================== 场景④ 数据参谋 ====================
function AskPanel() {
  const [q, setQ] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [history, setHistory] = useState<{ q: string; result: any }[]>([])
  // 最近一次问数成功的问题（供 Dify 数据决策深度报告输入）
  const [lastAskQ, setLastAskQ] = useState('')
  // 问数分阶段提示文案（轮换显示，缓解"无反馈干等"）
  const [stageIdx, setStageIdx] = useState(0)
  const STAGES = ['正在理解你的问题…', '正在检索数据表结构…', '正在生成查询并执行…', '正在整理分析结果…']

  useEffect(() => {
    if (!running) return
    setStageIdx(0)
    const timer = setInterval(() => setStageIdx((i) => (i + 1) % STAGES.length), 8000)
    return () => clearInterval(timer)
  }, [running])

  const handleAsk = async (question: string) => {
    if (!question.trim()) {
      notification.warning({
        message: '请先输入要问的问题',
        description: '在输入框里写下你的问题再点「问数」',
        placement: 'topRight', duration: 3,
      })
      return
    }
    setRunning(true)
    setResult(null)
    try {
      const res = await agentNl2sql(question)
      setResult(res)
      setLastAskQ(question)
      setHistory((h) => [{ q: question, result: res }, ...h].slice(0, 5))
    } catch (e: any) { message.error(e.message || '问数失败') }
    finally { setRunning(false) }
  }

  const suggestions = [
    '统计本科及以上学历的人才数量',
    '本月新进了多少人才',
    '各岗位平均匹配分是多少',
    '哪些人才测评合格',
  ]

  // 后端 NL2SQL 返回结构：
  // {success, nl2sql: {success, sql, columns, rows, message}, suggestions, errors}
  // 兼容历史扁平格式：{data: {sql, rows}} 或 {sql, rows}
  const flat: any = (() => {
    if (!result) return null
    const nl = result.nl2sql || (result.data && result.data.nl2sql) || (result.data && result.data) || result
    const inner = nl?.nl2sql || nl
    return {
      success: inner?.success !== false,
      sql: inner?.sql || result.data?.sql || result.sql,
      columns: inner?.columns || [],
      rows: inner?.rows || result.data?.rows || [],
      message: inner?.message || inner?.error,
      suggestions: result.suggestions || result.data?.suggestions,
      errors: result.errors || [],
    }
  })()

  const hasResult = flat && flat.sql && (flat.rows?.length > 0 || flat.success)

  /**
   * 把 SQL 结果包装为"人话"标题：
   *  - 单行单列 COUNT/SUM/AVG → "共 X 条" / "平均 X" / "合计 X"
   *  - 单行多列 → 也用大横幅（标题来自首列值 + 副标题）
   *  - 默认多行 → "已查到 X 条数据"
   */
  const humanizeResults = (flat: any) => {
    const rows = flat?.rows || []
    const cols = flat?.columns || []
    if (rows.length === 0) return null
    const first = rows[0]
    const firstCol = cols[0] || Object.keys(first)[0] || ''
    const colName = (firstCol || '').toLowerCase()
    const value = first[firstCol]
    // 单行单列
    if (rows.length === 1 && cols.length === 1) {
      if (/count\(\*?\)/.test(colName)) {
        return { headline: `共 ${value} 条`, sub: '（系统统计的人才数量）' }
      }
      if (/total|sum/.test(colName)) {
        return { headline: `共 ${value}`, sub: '' }
      }
      if (/avg|平均/.test(colName)) {
        return { headline: `平均 ${value}`, sub: '' }
      }
      return { headline: `查询结果：${value}`, sub: '' }
    }
    // 单行多列：直接显示数字组合（e.g. 测评合格名单）
    if (rows.length === 1 && cols.length > 1) {
      return { headline: '查询结果', sub: '系统已返回以下明细' }
    }
    // 多行：典型场景"按 X 维度统计"
    return { headline: `已查到 ${rows.length} 条数据`, sub: '系统从数据库中检索出以下记录' }
  }

  /**
   * 把 SQL 字段名翻译为中文表头（避免出现 total/cnt/count(*) 等技术词）
   */
  const _humanizeColumnName = (key: string): string => {
    const k = (key || '').toLowerCase().trim()
    if (/^(total|sum|count|cnt|number|quantity)$/.test(k)) return '总数'
    if (/^(avg|average)$/.test(k)) return '平均'
    if (/^max$/.test(k)) return '最大值'
    if (/^min$/.test(k)) return '最小值'
    if (/^(name|姓名)$/.test(k)) return '姓名'
    if (/position_name/.test(k)) return '岗位'
    if (/^id$/.test(k)) return '编号'
    if (/^(score|分数)$/.test(k)) return '分数'
    if (/^count_/.test(k)) return k.replace(/^count_/, '').replace(/^/, (c) => c.toUpperCase()) + '数量'
    return key
  }

  return (
    <Card title={<Space><DatabaseOutlined /> 数据参谋 · 一句话问数</Space>}>
      <Space.Compact style={{ width: '100%' }} size="large">
        <Input.Search
          size="large"
          placeholder="问一个业务问题，如：统计本科及以上学历的人才数量"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onSearch={handleAsk}
          enterButton={<><ThunderboltOutlined /> 问数</>}
          loading={running}
          style={{ marginBottom: 12 }}
        />
      </Space.Compact>
      <div style={{ marginBottom: 12 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>试试问：</Typography.Text>
        <Space wrap size={4} style={{ marginTop: 4 }}>
          {suggestions.map((s) => <Tag key={s} style={{ cursor: 'pointer' }} onClick={() => { setQ(s); handleAsk(s) }}>{s}</Tag>)}
        </Space>
      </div>
      {running && (
        <Card size="small" style={{ marginBottom: 12, background: '#f0f5ff' }}>
          <Space>
            <ThunderboltOutlined spin style={{ color: '#4361ee' }} />
            <Typography.Text>{STAGES[stageIdx]}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>（复杂问数可能需要 30~60 秒，请稍候）</Typography.Text>
          </Space>
        </Card>
      )}
      {!running && result && hasResult && (
        <Card size="small" type="inner" style={{ background: '#f9f9ff' }}>
          {flat.suggestions && (
            <Alert style={{ marginBottom: 8 }} type="info" showIcon
              message="AI 建议"
              description={flat.suggestions} />
          )}
          {(() => {
            const human = humanizeResults(flat)
            return human && (
              <div style={{
                background: 'linear-gradient(90deg,#4361ee,#06b6d4)',
                color: '#fff', padding: '14px 18px', borderRadius: 8, marginBottom: 12,
              }}>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{human.headline}</div>
                {human.sub && <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>{human.sub}</div>}
              </div>
            )
          })()}
          {/* 单行单列（聚合查询）只显示大横幅，明细折叠；多行才直接展示表格 */}
          {flat.rows && flat.rows.length > 1 ? (
            <Table
              size="small"
              pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
              dataSource={flat.rows.map((r: any, i: number) => ({ ...r, __key: i }))}
              rowKey="__key"
              columns={(flat.columns && flat.columns.length > 0
                ? flat.columns
                : Object.keys(flat.rows[0] || {})
              ).map((k: string) => ({ title: _humanizeColumnName(k), dataIndex: k, key: k }))}
            />
          ) : flat.rows && flat.rows.length === 1 && (flat.columns && flat.columns.length > 1) ? (
            <Table
              size="small"
              pagination={false}
              dataSource={flat.rows.map((r: any, i: number) => ({ ...r, __key: i }))}
              rowKey="__key"
              columns={flat.columns.map((k: string) => ({ title: _humanizeColumnName(k), dataIndex: k, key: k }))}
            />
          ) : null}
          {/* SQL 默认折叠：业务用户不需要看 SQL，仅排查/演示时展开 */}
          <details style={{ marginTop: 8 }}>
            <summary style={{ cursor: 'pointer', color: '#999', fontSize: 12 }}>查看查询明细（仅供技术人员参考）</summary>
            <pre style={{ margin: '8px 0 0', fontSize: 12, background: '#f0f0f0', padding: 8, borderRadius: 4, overflow: 'auto' }}>
              {flat.sql}
            </pre>
          </details>
        </Card>
      )}
      {!running && result && !hasResult && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 12 }}
          message="暂时没能查到想要的数据"
          description={
            <Space direction="vertical" size={4}>
              <span>当前问题没能匹配到可执行的查询，你可以换个问法再试：</span>
              <span style={{ fontSize: 12, color: '#666' }}>
                「人才总数」「」「」「人才总量」「在岗人才数」「已入库课程」「测评合格人次」。
              </span>
              {flat.sql && (
                <details style={{ marginTop: 4 }}>
                  <summary style={{ cursor: 'pointer', fontSize: 12, color: '#999' }}>查看技术细节</summary>
                  <pre style={{ margin: '4px 0 0', fontSize: 11, background: '#f0f0f0', padding: 6, borderRadius: 4, overflow: 'auto' }}>
                    {flat.sql}
                  </pre>
                </details>
              )}
            </Space>
          }
        />
      )}
      {history.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>最近问数：</Typography.Text>
          {history.map((h, i) => <Tag key={i} style={{ marginLeft: 4, marginTop: 4 }}>{h.q}</Tag>)}
        </div>
      )}
      {/* Dify 数据决策深度报告（异步，链路较长需耐心等待） */}
      {lastAskQ && !running && (
        <DifyReportCard
          agent="data_decision"
          title="AI 数据洞察报告"
          hint="由 Dify 数据决策智能体生成，约需 1~3 分钟"
          buildInputs={() => ({ analysis_type: 'nl2sql', question: lastAskQ })}
        />
      )}
    </Card>
  )
}

// ==================== 复用：结果摘要块 ====================
function ResultBlock({ title, icon, color, data, render }: { title: string; icon: any; color: string; data: any; render: (d: any) => any }) {
  return (
    <Card size="small" title={<Space style={{ color }}>{icon}<span>{title}</span></Space>}>
      {render(data)}
    </Card>
  )
}

export function ResultSummary({ data: _data, total, filtered, items, renderItem }: { data: any; total?: number; filtered?: number; items: any[]; renderItem?: (d: any) => any }) {
  return (
    <div>
      {total !== undefined && (
        <Space size={20} style={{ marginBottom: 12 }}>
          <Statistic title="评估候选人数" value={total || 0} valueStyle={{ fontSize: 16, color: '#4361ee' }} />
          <Statistic title="通过初筛" value={filtered || 0} valueStyle={{ fontSize: 16, color: '#06b6d4' }} />
          <Statistic title="推荐数" value={items.length} valueStyle={{ fontSize: 16, color: '#22c55e' }} />
        </Space>
      )}
      {items.length > 0 && renderItem ? (
        <Table size="small" pagination={false} dataSource={items.slice(0, 5)}
          rowKey={(r) => String(r.position_id || r.talent_id || r.id || Math.random())}
          columns={[
            { title: '岗位/对象', dataIndex: 'position_name', render: (v, r: any) => v || r.name || '-' },
            { title: '匹配分', dataIndex: 'final_score', width: 80, render: (v) => v !== undefined ? <Tag color={v >= 80 ? 'green' : v >= 60 ? 'orange' : 'red'}>{v}</Tag> : '-' },
            { title: '说明', dataIndex: 'match_reason', ellipsis: true },
            { title: '', key: 'op', width: 60, render: (_: any, r: any) => renderItem ? renderItem(r) : null },
          ]} />
      ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无结果" />}
    </div>
  )
}

// ==================== 加载下拉数据 ====================
async function loadTalents(setList: (l: any[]) => void) {
  try {
    const r = await listTalents({ page: 1, page_size: 50 })
    setList((r.items || []).map((t: any) => ({ value: t.id, label: t.name || `人才 #${t.id}` })))
  } catch {}
}
async function loadPositions(setList: (l: any[]) => void) {
  try {
    const r = await listPositions({ page: 1, page_size: 100 })
    setList((r.items || []).map((p: any) => ({ value: p.id, label: p.position_name || p.name })))
  } catch {}
}

// 占位（避免构建错误，组件内通过 useEffect 替代）
// 选下拉需要 positionList/ talentList 真正注入到 select
function FindPanelReal({ navigate }: { navigate: any }) {
  const [positionList, setPositionList] = useState<any[]>([])
  useEffect(() => { loadPositions(setPositionList) }, [])
  const [posId, setPosId] = useState<number | undefined>()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [positionName, setPositionName] = useState<string>('')
  // 人才档案 Modal 状态
  const [profileOpen, setProfileOpen] = useState(false)
  const [profileLoading, setProfileLoading] = useState(false)
  const [profile, setProfile] = useState<any>(null)
  const handleRun = async () => {
    if (!posId) { message.warning('请先选择岗位'); return }
    setRunning(true)
    try {
      const sel = positionList.find((p: any) => p.value === posId)
      setPositionName(sel?.label || '')
      const res = await agentMatchPosition(posId)
      setResult(res)
    } catch (e: any) { message.error(e.message || '匹配失败') }
    finally { setRunning(false) }
  }
  const openProfile = async (talentId: number) => {
    setProfileOpen(true)
    setProfileLoading(true)
    setProfile(null)
    try {
      const data = await getTalent(talentId)
      setProfile(data)
    } catch (e: any) {
      message.error('加载人才档案失败：' + e.message)
    } finally {
      setProfileLoading(false)
    }
  }
  const matches = (result?.match_results || []) as any[]
  return (
    <Card title={<Space><AimOutlined /> 快速找人 · 按岗位推荐人才</Space>}>
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col flex="300px">
          <Select placeholder="选择岗位" value={posId} onChange={setPosId} showSearch optionFilterProp="label" style={{ width: '100%' }} options={positionList} />
        </Col>
        <Col><Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun}>推荐人才</Button></Col>
        <Col><Button type="link" onClick={() => navigate('/positions')}>去岗位管理 →</Button></Col>
      </Row>
      {!result && (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择岗位后点击「推荐人才」，系统会从人才库中筛选并按匹配度排序" />
      )}
      {result && (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {/* 顶部数字仪表 */}
          <Row gutter={12}>
            <Col span={8}>
              <Card size="small" style={{ background: '#f0f4ff', border: 'none' }}>
                <Statistic title="人才库总量" value={result.total_candidates || 0}
                  valueStyle={{ fontSize: 22, color: '#4361ee' }} suffix="人" />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ background: '#ecfeff', border: 'none' }}>
                <Statistic title="通过硬条件初筛" value={result.filtered_candidates || 0}
                  valueStyle={{ fontSize: 22, color: '#06b6d4' }} suffix="人" />
              </Card>
            </Col>
            <Col span={8}>
              <Card size="small" style={{ background: '#f0fdf4', border: 'none' }}>
                <Statistic title="推荐人选" value={matches.length}
                  valueStyle={{ fontSize: 22, color: '#22c55e' }} suffix="人" />
              </Card>
            </Col>
          </Row>

          {/* 推荐名单：人话卡片而非干表 */}
          {matches.length === 0 ? (
            <Empty description="暂无符合条件的人选" />
          ) : (
            <>
              <Typography.Text strong style={{ fontSize: 13 }}>
                「{positionName || '该岗位'}」推荐人选（按匹配分从高到低）：
              </Typography.Text>
              <List
                size="small"
                dataSource={matches.slice(0, 10)}
                renderItem={(t: any, idx: number) => (
                  <List.Item key={t.id || idx}
                    actions={[
                      <Tag color={t.final_score >= 80 ? 'green' : t.final_score >= 60 ? 'orange' : 'red'} key="score">
                        匹配分 {t.final_score ?? '-'}
                      </Tag>,
                      <Button key="view" type="link" size="small" onClick={() => openProfile(t.id)}>查看档案</Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Typography.Text strong style={{ fontSize: 14 }}>{idx + 1}. {t.name || '-'}</Typography.Text>
                          <Tag>{t.education || '-'}</Tag>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t.experience_years || 0} 年经验</Typography.Text>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={2} style={{ width: '100%' }}>
                          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                            {(t.skills_certificates || []).slice(0, 5).map((s: any) =>
                              typeof s === 'object' ? s.name : s
                            ).join('、') || '暂无技能标签'}
                          </Typography.Text>
                          {t.match_reason && (
                            <Typography.Text style={{ fontSize: 12, color: '#666' }}>
                              <CheckCircleFilled style={{ color: '#06b6d4', marginRight: 4 }} />
                              {t.match_reason}
                            </Typography.Text>
                          )}
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            </>
          )}
        </Space>
      )}

      {/* 人才档案 Modal（"查看档案"按钮触发） */}
      <Modal
        title={<Space><UserOutlined /> 人才档案</Space>}
        open={profileOpen}
        onCancel={() => setProfileOpen(false)}
        footer={<Button onClick={() => setProfileOpen(false)}>关闭</Button>}
        width={680}
      >
        {profileLoading && (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip="加载中..." /></div>
        )}
        {!profileLoading && profile && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="姓名">{profile.name}</Descriptions.Item>
            <Descriptions.Item label="编号">{profile.talent_code}</Descriptions.Item>
            <Descriptions.Item label="性别">{profile.gender === 'male' ? '男' : profile.gender === 'female' ? '女' : '-'}</Descriptions.Item>
            <Descriptions.Item label="工作年限">{profile.experience_years ?? 0} 年</Descriptions.Item>
            <Descriptions.Item label="学历">{profile.education || '-'}</Descriptions.Item>
            <Descriptions.Item label="专业">{profile.major || '-'}</Descriptions.Item>
            <Descriptions.Item label="当前公司" span={2}>{profile.current_company || '-'}</Descriptions.Item>
            <Descriptions.Item label="当前职位" span={2}>{profile.current_position || '-'}</Descriptions.Item>
            <Descriptions.Item label="联系方式" span={2}>
              {profile.phone || '-'} {profile.email ? ` / ${profile.email}` : ''}
            </Descriptions.Item>
            <Descriptions.Item label="状态">{profile.status === 'active' ? '在岗' : profile.status === 'reserve' ? '储备' : profile.status}</Descriptions.Item>
            <Descriptions.Item label="能力评级">
              {(() => {
                const r = profile.capability_rating
                if (!r) return '未评'
                // 兜底：能力评级可能是字符串、也可能是对象（后端 JSON 字段未规范化）
                if (typeof r === 'string') return r
                if (typeof r === 'object') {
                  return r.ability_level || r.level || r.name || JSON.stringify(r)
                }
                return String(r)
              })()}
            </Descriptions.Item>
            <Descriptions.Item label="技能标签" span={2}>
              {Array.isArray(profile.skills_certificates) && profile.skills_certificates.length > 0 ? (
                <Space wrap size={[4, 4]}>
                  {profile.skills_certificates.map((s: any, i: number) => (
                    <Tag key={i} color="blue">{typeof s === 'object' ? s.name : s}</Tag>
                  ))}
                </Space>
              ) : '暂无'}
            </Descriptions.Item>
            {profile.self_introduction && (
              <Descriptions.Item label="自我介绍" span={2}>{profile.self_introduction}</Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </Card>
  )
}

function AssessPanelReal() {
  const [talentList, setTalentList] = useState<any[]>([])
  useEffect(() => { loadTalents(setTalentList) }, [])
  const [talentId, setTalentId] = useState<number | undefined>()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [talentName, setTalentName] = useState<string>('')
  const [talentProfile, setTalentProfile] = useState<any>(null)
  // 最近一次深度研判用的测评结果 id（供 Dify 深度报告输入）
  const [lastResultId, setLastResultId] = useState<number | undefined>()
  const handleRun = async () => {
    if (!talentId) { message.warning('请选择人才'); return }
    setRunning(true)
    setResult(null)
    setLastResultId(undefined)
    try {
      const sel = talentList.find((t: any) => t.value === talentId)
      setTalentName(sel?.label || '')
      // 拉取人才基本档案（用于"暂无测评结果"时的兜底展示）
      try {
        const profile = await getTalent(talentId)
        setTalentProfile(profile)
      } catch {}
      const r = await listAssessmentResults({ talent_id: talentId, page: 1, page_size: 1 })
      const rid = r?.items?.[0]?.id
      if (!rid) {
        setResult({ success: false, no_assessment: true, message: '该人才暂无测评档案' })
        setRunning(false)
        return
      }
      setLastResultId(rid)
      const res = await agentAnalyzeAssessment(rid)
      setResult(res)
    } catch (e: any) { message.error(e.message || '分析失败') }
    finally { setRunning(false) }
  }
  // 能力等级中文映射
  const LEVEL_LABELS: Record<string, string> = {
    '核心人才': '核心人才', '骨干': '骨干', '高级': '高级', '中级': '中级',
    '初级': '初级', 'core': '核心人才', 'backbone': '骨干', 'senior': '高级',
    'intermediate': '中级', 'junior': '初级', 'entry': '入门',
  }
  return (
    <Card title={<Space><BarChartOutlined /> 盘点人才库 · 单人能力深度研判</Space>}>
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col flex="300px">
          <Select placeholder="选择人才" value={talentId} onChange={setTalentId} showSearch optionFilterProp="label" style={{ width: '100%' }} options={talentList} />
        </Col>
        <Col><Button type="primary" icon={<ThunderboltOutlined />} loading={running} onClick={handleRun}>深度研判</Button></Col>
      </Row>
      {!result && (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择人才后点击「深度研判」，系统会基于其测评结果输出能力短板与发展建议" />
      )}
      {result && (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {!result.success && (
            <>
              <Alert type="info" showIcon
                message="该人才暂无测评档案"
                description={result.no_assessment
                  ? '尚未对该人才创建测评任务，下面是 TA 的基本档案信息。可到「测评管理」创建测评任务后再次深度研判。'
                  : (result.errors?.[0] || '请先到「测评管理」创建测评任务')} />
              {talentProfile && (
                <Card size="small" type="inner" title={<Space><UserOutlined /> 人才基本档案</Space>}>
                  <Row gutter={[12, 6]}>
                    <Col span={6}><Statistic title="姓名" value={talentProfile.name || '-'} valueStyle={{ fontSize: 14 }} /></Col>
                    <Col span={6}><Statistic title="学历" value={talentProfile.education || '-'} valueStyle={{ fontSize: 14 }} /></Col>
                    <Col span={6}><Statistic title="工作年限" value={`${talentProfile.experience_years || 0} 年`} valueStyle={{ fontSize: 14 }} /></Col>
                    <Col span={6}><Statistic title="当前职位" value={talentProfile.current_position || '-'} valueStyle={{ fontSize: 14 }} /></Col>
                  </Row>
                  {Array.isArray(talentProfile.skills_certificates) && talentProfile.skills_certificates.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>技能标签：</Typography.Text>
                      <div style={{ marginTop: 4 }}>
                        <Space wrap size={4}>
                          {talentProfile.skills_certificates.slice(0, 8).map((s: any, i: number) => (
                            <Tag key={i} color="blue">{typeof s === 'object' ? s.name : s}</Tag>
                          ))}
                        </Space>
                      </div>
                    </div>
                  )}
                </Card>
              )}
            </>
          )}
          {result.success && (
            <>
              <Card size="small" type="inner" style={{ background: '#fafbff' }}>
                <Row gutter={16}>
                  <Col span={6}>
                    <Statistic title="研判对象"
                      value={talentName || `人才 #${result.talent_id || talentId}`}
                      valueStyle={{ fontSize: 14, color: '#7b5ce6' }} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="能力评级"
                      value={LEVEL_LABELS[result.ability_level] || result.ability_level || '-'}
                      valueStyle={{ fontSize: 16, color: '#7b5ce6', fontWeight: 600 }} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="综合得分"
                      value={Math.round(result.total_score ?? 0)}
                      suffix="分（满分100）"
                      valueStyle={{ fontSize: 14, color: '#7b5ce6' }} />
                  </Col>
                  <Col span={6}>
                    <Statistic title="得分率"
                      value={result.correct_rate?.toFixed ? Math.round(result.correct_rate) : (result.correct_rate || 0)}
                      suffix="%"
                      valueStyle={{ fontSize: 14, color: '#7b5ce6', fontWeight: 600 }} />
                  </Col>
                </Row>
              </Card>

              {result.category_scores && Object.keys(result.category_scores).length > 0 && (
                <Card size="small" title="能力画像" type="inner">
                  <RadarPanel data={result.category_scores} />
                </Card>
              )}

              <Row gutter={12}>
                <Col span={12}>
                  <Card size="small" type="inner" title={<span style={{ color: '#52c41a' }}>优势</span>}>
                    {result.strengths?.length
                      ? <ul style={{ paddingLeft: 18, margin: 0 }}>{result.strengths.map((s: string, i: number) => <li key={i} style={{ fontSize: 12 }}>{s}</li>)}</ul>
                      : <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无明显优势维度</Typography.Text>}
                  </Card>
                </Col>
                <Col span={12}>
                  <Card size="small" type="inner" title={<span style={{ color: '#fa8c16' }}>短板</span>}>
                    {result.weaknesses?.length
                      ? <ul style={{ paddingLeft: 18, margin: 0 }}>{result.weaknesses.map((s: string, i: number) => <li key={i} style={{ fontSize: 12 }}>{s}</li>)}</ul>
                      : <Typography.Text type="secondary" style={{ fontSize: 12 }}>暂无明显短板</Typography.Text>}
                  </Card>
                </Col>
              </Row>

              {result.development_suggestions?.length > 0 && (
                <Card size="small" type="inner" title="发展建议">
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    {result.development_suggestions.map((s: string, i: number) => (
                      <div key={i} style={{ fontSize: 12 }}>
                        <CheckCircleFilled style={{ color: '#1677ff', marginRight: 4 }} />{s}
                      </div>
                    ))}
                  </Space>
                </Card>
              )}

              {result.recommended_courses?.length > 0 && (
                <Card size="small" type="inner" title="推荐课程">
                  <Space wrap size={6}>
                    {result.recommended_courses.map((c: any, i: number) => (
                      <Tag key={i} color="orange" style={{ padding: '2px 8px' }}>
                        <BookOutlined style={{ marginRight: 4 }} />{c.course_name}
                      </Tag>
                    ))}
                  </Space>
                </Card>
              )}

              {/* Dify 深度报告叠加层（按需触发，不影响上方本地结构化展示） */}
              {lastResultId ? (
                <DifyReportCard
                  agent="assessment"
                  title="AI 深度研判报告"
                  hint="由 Dify 测评分析智能体基于测评结果生成图文结论"
                  buildInputs={() => ({
                    talent_id: String(result?.talent_id || talentId || ''),
                    assessment_result_id: String(lastResultId),
                  })}
                />
              ) : null}
            </>
          )}
        </Space>
      )}
    </Card>
  )
}
