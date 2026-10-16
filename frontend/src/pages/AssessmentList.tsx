import { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message, Space, Card,
  Tag, Row, Col, Typography, Badge, Slider, Empty, Radio, Checkbox, Spin, Tabs, Tooltip, Popconfirm,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, FileTextOutlined,
  FileAddOutlined, ExperimentOutlined, ThunderboltOutlined, DeleteOutlined,
} from '@ant-design/icons'
import { listQuestions, createQuestion, listPapers, autoGeneratePaper, simulateAnswer, listTalents, listAssessmentTasks, listAssessmentResults, getPaperQuestions, gradeRealAnswer, batchDeleteQuestions, batchDeletePapers, batchDeleteAssessmentTasks, deleteAssessmentTask } from '../api'
import ModuleBanner from '../components/ModuleBanner'

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单选' },
  { value: 'multiple_choice', label: '多选' },
  { value: 'true_false', label: '判断' },
  { value: 'fill_blank', label: '填空' },
  { value: 'short_answer', label: '简答' },
  { value: 'essay', label: '论述' },
]
const TYPE_TAG: Record<string, string> = {
  single_choice: 'blue',
  multiple_choice: 'purple',
  true_false: 'cyan',
  fill_blank: 'orange',
  short_answer: 'gold',
  essay: 'magenta',
}
const TYPE_LABEL = TYPE_OPTIONS.reduce((acc, o) => { acc[o.value] = o.label; return acc }, {} as Record<string, string>)

// 能力等级标签
const LEVEL_TAG: Record<string, string> = {
  entry: 'default', junior: 'blue', intermediate: 'cyan',
  senior: 'purple', expert: 'gold', backbone: 'geekblue', core: 'magenta',
}
const LEVEL_LABEL: Record<string, string> = {
  entry: '入门', junior: '初级', intermediate: '中级',
  senior: '高级', expert: '专家', backbone: '骨干', core: '核心',
}
// 测评任务状态
const TASK_STATUS: Record<string, { color: string; text: string }> = {
  draft: { color: 'default', text: '草稿' },
  published: { color: 'blue', text: '已发布' },
  in_progress: { color: 'processing', text: '进行中' },
  completed: { color: 'green', text: '已完成' },
  cancelled: { color: 'red', text: '已取消' },
}

const DIFFICULTY_COLORS = ['#22c55e', '#84cc16', '#f59e0b', '#f97316', '#ef4444']
const renderDifficulty = (v: number) => {
  const level = Math.min(Math.max(v || 1, 1), 5)
  return (
    <Space size={4}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span
          key={i}
          style={{
            width: 10, height: 10, borderRadius: '50%',
            background: i < level ? DIFFICULTY_COLORS[level - 1] : '#e5e7eb',
          }}
        />
      ))}
      <span style={{ marginLeft: 4, fontSize: 12, color: DIFFICULTY_COLORS[level - 1] }}>{level}</span>
    </Space>
  )
}

export default function AssessmentList() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState({ keyword: '', question_type: '', difficulty: '' })
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  // 自动组卷 + 模拟答题
  const [paperOpen, setPaperOpen] = useState(false)
  const [paperSubmitting, setPaperSubmitting] = useState(false)
  const [paperForm] = Form.useForm()
  const [papers, setPapers] = useState<any[]>([])
  const [simulating, setSimulating] = useState<number | null>(null)
  const [simulateResult, setSimulateResult] = useState<any>(null)

  // 模拟答题弹窗（选择人才 + 正确率）
  const [simulateOpen, setSimulateOpen] = useState(false)
  const [assessTab, setAssessTab] = useState<string>('papers')
  // 题目/试卷批量选择
  const [qSelected, setQSelected] = useState<number[]>([])
  const [selectedTaskKeys, setSelectedTaskKeys] = useState<React.ReactText[]>([])
  const [batchTaskDeleting, setBatchTaskDeleting] = useState(false)
  const [paperSelected, setPaperSelected] = useState<number[]>([])
  const [batchBusy, setBatchBusy] = useState(false)
  const [simulatePaperId, setSimulatePaperId] = useState<number | null>(null)
  const [simulatePaperName, setSimulatePaperName] = useState('')
  const [simulateForm] = Form.useForm()
  const [talents, setTalents] = useState<any[]>([])

  // 真实作答：题目 + 每题作答
  const [realOpen, setRealOpen] = useState(false)
  const [realPaperId, setRealPaperId] = useState<number | null>(null)
  const [realPaperName, setRealPaperName] = useState('')
  const [realQuestions, setRealQuestions] = useState<any[]>([])
  const [realAnswers, setRealAnswers] = useState<Record<number, string>>({})
  const [realLoading, setRealLoading] = useState(false)
  const [realGrading, setRealGrading] = useState(false)
  const [realResult, setRealResult] = useState<any>(null)

  // 测评任务 + 测评结果
  const [tasks, setTasks] = useState<any[]>([])
  const [results, setResults] = useState<any[]>([])
  const [tasksLoading, setTasksLoading] = useState(false)
  const [resultsLoading, setResultsLoading] = useState(false)

  const loadTasks = async () => {
    setTasksLoading(true)
    try {
      const res = await listAssessmentTasks({ page: 1, page_size: 20 })
      setTasks(res.items || [])
    } catch (e: any) {
      console.error('加载测评任务失败', e)
    } finally {
      setTasksLoading(false)
    }
  }

  const loadResults = async () => {
    setResultsLoading(true)
    try {
      const res = await listAssessmentResults({ page: 1, page_size: 20 })
      setResults(res.items || [])
    } catch (e: any) {
      console.error('加载测评结果失败', e)
    } finally {
      setResultsLoading(false)
    }
  }

  useEffect(() => { loadTasks(); loadResults() }, [])  // eslint-disable-line

  const load = async (p = page, ps = pageSize, filters = search) => {
    setLoading(true)
    try {
      const res = await listQuestions({ page: p, page_size: ps, ...filters })
      setData(res.items || [])
      setTotal(res.total || 0)
    } catch (e: any) {
      message.error(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1, 10, search) }, [])  // eslint-disable-line

  const onSearch = () => {
    setPage(1)
    load(1, pageSize, search)
  }

  const onReset = () => {
    const empty = { keyword: '', question_type: '', difficulty: '' }
    setSearch(empty)
    setPage(1)
    load(1, pageSize, empty)
  }

  const loadPapers = async () => {
    try {
      const res = await listPapers({ page: 1, page_size: 50 })
      setPapers(res.items || [])
    } catch (e: any) {
      message.error('加载试卷失败：' + e.message)
    }
  }

  useEffect(() => { loadPapers() }, [])  // eslint-disable-line

  // 自动组卷
  const handleAutoGenerate = async () => {
    try {
      const values = await paperForm.validateFields()
      const strategy: Record<string, number> = {}
      ;(['single_choice', 'multiple_choice', 'true_false', 'fill_blank', 'short_answer', 'essay'] as const).forEach((t) => {
        const v = values[t]
        if (v && Number(v) > 0) strategy[t] = Number(v)
      })
      if (Object.keys(strategy).length === 0) {
        message.warning('请至少设置一种题型的抽题数量')
        return
      }
      setPaperSubmitting(true)
      const res = await autoGeneratePaper({
        paper_name: values.paper_name,
        paper_type: values.paper_type || '综合测评',
        paper_description: values.paper_description,
        duration_minutes: values.duration_minutes,
        category: values.category || undefined,
        difficulty: values.difficulty || undefined,
        strategy,
      })
      message.success(`自动组卷成功：共 ${res.question_count} 题，总分 ${res.total_score}`)
      setPaperOpen(false)
      paperForm.resetFields()
      await loadPapers()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '自动组卷失败')
    } finally {
      setPaperSubmitting(false)
    }
  }

  // 打开模拟答题弹窗
  const openSimulate = async (paperId: number, paperName: string) => {
    setSimulatePaperId(paperId)
    setSimulatePaperName(paperName)
    setSimulateOpen(true)
    simulateForm.resetFields()
    // 懒加载人才列表
    if (talents.length === 0) {
      try {
        const res = await listTalents({ page: 1, page_size: 100 })
        setTalents(res.items || [])
      } catch (e: any) {
        // 人才列表加载失败不阻断
        console.error('人才列表加载失败', e)
      }
    }
  }

  // 批量删除题目
  const handleBatchDeleteQuestions = async () => {
    if (qSelected.length === 0) { message.warning('请先勾选题目'); return }
    Modal.confirm({
      title: `确认删除 ${qSelected.length} 道题目?`,
      content: '删除后无法恢复，已从引用试卷中自动清理',
      okType: 'danger',
      onOk: async () => {
        setBatchBusy(true)
        try {
          const res = await batchDeleteQuestions(qSelected)
          message.success(res?.message || '删除成功')
          setQSelected([])
          load()
        } catch (e: any) {
          message.error(e?.message || '删除失败')
        } finally {
          setBatchBusy(false)
        }
      },
    })
  }

  // 批量删除测评任务
  const handleBatchDeleteTasks = async () => {
    if (selectedTaskKeys.length === 0) { message.warning('请先勾选要删除的测评任务'); return }
    try {
      setBatchTaskDeleting(true)
      const res: any = await batchDeleteAssessmentTasks(selectedTaskKeys.map((k: any) => Number(k)))
      message.success(res?.message || `批量删除成功：共删除 ${res?.deleted ?? selectedTaskKeys.length} 条`)
      setSelectedTaskKeys([])
      loadTasks()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchTaskDeleting(false)
    }
  }

  // 删除单个测评任务
  const handleDeleteTask = async (id: number) => {
    try {
      await deleteAssessmentTask(id)
      message.success('测评任务已删除')
      setSelectedTaskKeys([])
      loadTasks()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 批量删除试卷
  const handleBatchDeletePapers = async () => {
    if (paperSelected.length === 0) { message.warning('请先勾选试卷'); return }
    Modal.confirm({
      title: `确认删除 ${paperSelected.length} 份试卷?`,
      content: '删除后无法恢复',
      okType: 'danger',
      onOk: async () => {
        setBatchBusy(true)
        try {
          const res = await batchDeletePapers(paperSelected)
          message.success(res?.message || '删除成功')
          setPaperSelected([])
          loadPapers()
        } catch (e: any) {
          message.error(e?.message || '删除失败')
        } finally {
          setBatchBusy(false)
        }
      },
    })
  }

  // 真实作答弹框：拉题目 + 题目作答
  const openReal = async (paperId: number, paperName: string) => {
    setRealPaperId(paperId)
    setRealPaperName(paperName)
    setRealOpen(true)
    setRealQuestions([])
    setRealAnswers({})
    setRealResult(null)
    setRealLoading(true)
    try {
      const res = await getPaperQuestions(paperId, false)
      setRealQuestions(res?.items || [])
      if (!res?.items?.length) message.warning('该试卷暂无题目')
    } catch (e: any) {
      message.error(e?.message || '题目加载失败')
      setRealOpen(false)
    } finally {
      setRealLoading(false)
    }
  }
  const handleRealSubmit = async () => {
    if (!realPaperId) return
    const answered = Object.keys(realAnswers).length
    const total = realQuestions.length
    if (answered < total) {
      message.warning(`还有 ${total - answered} 题未作答，确认提交吗？`)
    }
    setRealGrading(true)
    try {
      const answers = realQuestions.map((q) => ({ question_id: q.id, answer: realAnswers[q.id] ?? '' }))
      const res = await gradeRealAnswer(realPaperId, { talent_id: 1, answers })
      setRealResult(res)
    } catch (e: any) {
      message.error(e?.message || '判分失败')
    } finally {
      setRealGrading(false)
    }
  }

  // 模拟答题弹窗确认（使用用户选择的人才与正确率）
  const handleSimulateSubmit = async () => {
    if (simulatePaperId == null) return
    try {
      const values = await simulateForm.validateFields()
      setSimulating(simulatePaperId)
      setSimulateResult(null)
      setSimulateOpen(false)
      const res = await simulateAnswer(simulatePaperId, {
        talent_id: values.talent_id,
        correct_rate: values.correct_rate,
      })
      setSimulateResult({ ...res, paper_name: simulatePaperName })
      message.success('模拟答题完成')
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '模拟答题失败')
    } finally {
      setSimulating(null)
    }
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      const options = (values.options || '').split('\n').map((s: string) => s.trim()).filter(Boolean)
      setSubmitting(true)
      await createQuestion({ ...values, options })
      message.success('创建成功')
      setOpen(false)
      form.resetFields()
      load(1)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    {
      title: '题目', dataIndex: 'question_content', key: 'question_content',
      ellipsis: true,
    },
    {
      title: '题型', dataIndex: 'question_type', key: 'question_type', width: 90,
      render: (v: string) => v ? <Tag color={TYPE_TAG[v] || 'default'}>{TYPE_LABEL[v] || v}</Tag> : '-',
    },
    { title: '分类', dataIndex: 'category', key: 'category', width: 120 },
    {
      title: '分值', dataIndex: 'score', key: 'score', width: 80,
      render: (v: any) => v ?? 0,
    },
    {
      title: '难度', dataIndex: 'difficulty', key: 'difficulty', width: 160,
      render: (v: number) => renderDifficulty(v || 1),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><FileTextOutlined /> 测评管理</Space>
      </Typography.Title>

      <ModuleBanner
        value="用标准化的能力测评，客观看清人才的真实水平与短板，替代「凭感觉用人」。"
        relation="测评结果是培训的起点："
        prevLabel="人才档案"
        prevPath="/talents"
        nextLabel="培训管理"
        nextPath="/training"
      />

      <Card bordered={false} size="small">
        <Row gutter={12}>
          <Col flex="240px">
            <Input
              placeholder="题目内容/编号"
              value={search.keyword}
              onChange={(e) => setSearch({ ...search, keyword: e.target.value })}
              onPressEnter={onSearch}
              allowClear
            />
          </Col>
          <Col flex="140px">
            <Select
              placeholder="题型"
              value={search.question_type || undefined}
              onChange={(v) => setSearch({ ...search, question_type: v || '' })}
              options={TYPE_OPTIONS}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col flex="140px">
            <Select
              placeholder="难度"
              value={search.difficulty || undefined}
              onChange={(v) => setSearch({ ...search, difficulty: v ? String(v) : '' })}
              options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n} 星` }))}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={onSearch}>搜索</Button>
              <Button onClick={onReset}>重置</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 4-tab 导航：让测评管理分场景查看，避免下方卡片堆叠过长 */}
      <Card bordered={false} size="small" style={{ marginBottom: 16 }}>
        <Tabs
          activeKey={assessTab}
          onChange={(k) => {
            setAssessTab(k as string);
            // 按需懒加载
            if (k === 'tasks') loadTasks();
            else if (k === 'results') loadResults();
            else if (k === 'qbuild') load();
          }}
          items={[
            { key: 'papers',  label: <span><FileAddOutlined /> 试卷列表</span> },
            { key: 'results', label: <span><FileTextOutlined /> 测评结果</span> },
            { key: 'tasks',   label: <span><ExperimentOutlined /> 测评任务</span> },
            { key: 'qbuild',  label: <span><PlusOutlined /> 新增题目/自动组卷</span> },
          ].map((t) => ({ ...t, children: null as any }))}
        />
      </Card>

      {/* 题目库 + 自动组卷（新增题目 Tab 内容） */}
      <div style={{ display: assessTab === 'qbuild' ? 'block' : 'none' }}>
      <Card bordered={false}>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增题目</Button>
          <Button icon={<FileAddOutlined />} onClick={() => setPaperOpen(true)}>自动组卷</Button>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          <Badge count={total} overflowCount={9999} style={{ backgroundColor: '#9333ea' }} />
          {qSelected.length > 0 && (
            <Button danger size="small" icon={<DeleteOutlined />} loading={batchBusy}
              onClick={handleBatchDeleteQuestions}>
              批量删除 ({qSelected.length})
            </Button>
          )}
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          rowSelection={{
            selectedRowKeys: qSelected,
            onChange: (keys) => setQSelected(keys as number[]),
          }}
          columns={columns}
          locale={{ emptyText: <Empty description="暂无测评题目" /> }}
          scroll={{ x: 1000 }}
          pagination={{
            total,
            current: page,
            pageSize,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p); setPageSize(ps); load(p, ps)
            },
          }}
        />
      </Card>
      <Modal
        title="新增测评题目"
        open={open}
        onOk={handleCreate}
        onCancel={() => { setOpen(false); form.resetFields() }}
        confirmLoading={submitting}
        width={680}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" preserve={false} initialValues={{ score_value: 5, difficulty: 3 }}>
          <Form.Item name="question_content" label="题目内容" rules={[{ required: true, message: '请输入题目内容' }]}>
            <Input.TextArea rows={3} placeholder="如：请描述你对数字化转型中数据治理的理解。" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="question_type" label="题型" rules={[{ required: true, message: '请选择题型' }]}>
                <Select options={TYPE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="question_category" label="分类">
                <Input placeholder="如：技术/管理/综合" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="score_value" label="分值">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="options" label="选项(每行一个)">
                <Input.TextArea rows={4} placeholder="A. 选项一&#10;B. 选项二&#10;C. 选项三" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="correct_answer" label="正确答案">
                <Input placeholder="如：A 或 多选以逗号分隔" />
              </Form.Item>
              <Form.Item name="difficulty" label="难度">
                <Slider min={1} max={5} marks={{ 1: '易', 2: '', 3: '中', 4: '', 5: '难' }} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 自动组卷 Modal */}
      <Modal
        title="自动组卷（按题型随机抽题拼装试卷）"
        open={paperOpen}
        onOk={handleAutoGenerate}
        onCancel={() => { setPaperOpen(false); paperForm.resetFields() }}
        confirmLoading={paperSubmitting}
        width={680}
        okText="生成试卷"
        cancelText="取消"
      >
        <Form form={paperForm} layout="vertical" preserve={false} initialValues={{ paper_type: '综合测评', duration_minutes: 60, single_choice: 10, multiple_choice: 5, true_false: 5 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="paper_name" label="试卷名称" rules={[{ required: true, message: '请输入试卷名称' }]}>
                <Input placeholder="如：技术岗综合测评卷" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="paper_type" label="试卷类型">
                <Input placeholder="如：综合测评 / 专业技能" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="single_choice" label="单选题数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="multiple_choice" label="多选题数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="true_false" label="判断题数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="fill_blank" label="填空题数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="short_answer" label="简答题数">
                <InputNumber min={0} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="duration_minutes" label="时长(分钟)">
                <InputNumber min={10} max={300} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="category" label="题目分类（可选）">
                <Input placeholder="如：技术 / 综合" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="difficulty" label="难度（可选）">
                <Select
                  allowClear
                  placeholder="不限"
                  options={[1, 2, 3, 4, 5].map((n) => ({ value: n, label: `${n} 星` }))}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="paper_description" label="试卷描述（可选）">
            <Input placeholder="自动拼装试卷" />
          </Form.Item>
        </Form>
      </Modal>

      </div>

      {/* 试卷列表 + 模拟答题 */}
      <div style={{ display: assessTab === 'papers' ? 'block' : 'none' }}>
      <Card title={<Space><FileAddOutlined /> 试卷列表（模拟答题）</Space>} bordered={false}>
        {papers.length === 0 ? (
          <Empty description="暂无试卷，点击上方「自动组卷」生成" />
        ) : (
          <>
            {paperSelected.length > 0 && (
              <Button danger size="small" icon={<DeleteOutlined />} loading={batchBusy}
                onClick={handleBatchDeletePapers} style={{ marginBottom: 8 }}>
                批量删除 ({paperSelected.length})
              </Button>
            )}
            <Table
              rowKey="id"
              dataSource={papers}
              size="small"
              rowSelection={{
                selectedRowKeys: paperSelected,
                onChange: (keys) => setPaperSelected(keys as number[]),
              }}
              pagination={false}
              columns={[
                { title: '编号', dataIndex: 'paper_code', key: 'paper_code', width: 160 },
                { title: '名称', dataIndex: 'paper_name', key: 'paper_name', ellipsis: true },
                { title: '类型', dataIndex: 'paper_type', key: 'paper_type', width: 120 },
                { title: '总分', dataIndex: 'total_score', key: 'total_score', width: 80, render: (v: any) => v ?? 0 },
                {
                  title: '状态', dataIndex: 'status', key: 'status', width: 90,
                  render: (v: any) => {
                    const map: Record<string, { color: string; text: string }> = {
                      draft: { color: 'blue', text: '草稿' },
                      published: { color: 'green', text: '已发布' },
                    }
                    const cfg = map[v] || { color: 'default', text: v || '-' }
                    return <Tag color={cfg.color}>{cfg.text}</Tag>
                  },
                },
                {
                  title: '操作', key: 'action', width: 210,
                  render: (_: any, r: any) => (
                    <Space size={2}>
                      <Tooltip title="弹出试卷，让员工本人逐题真实作答（单选/多选/填空/简答），提交后自动判分">
                        <Button type="link" size="small" icon={<ExperimentOutlined />}
                          onClick={() => openReal(r.id, r.paper_name)}>
                          开始答题
                        </Button>
                      </Tooltip>
                      <Tooltip title="系统模拟某位人才按设定正确率作答该卷，用于快速生成/演示一份测评结果（无需员工本人参与）">
                        <Button type="link" size="small" icon={<ThunderboltOutlined />}
                          loading={simulating === r.id}
                          onClick={() => openSimulate(r.id, r.paper_name)}>
                          AI 模拟
                        </Button>
                      </Tooltip>
                    </Space>
                  ),
                },
              ]}
            />
            {simulateResult && (
              <Card size="small" style={{ marginTop: 12, background: '#f6f8ff' }}>
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Typography.Text strong>
                    模拟答题结果 —— {simulateResult.paper_name}
                  </Typography.Text>
                  <Row gutter={12}>
                    <Col span={6}><StatisticCard label="总分" value={simulateResult.total_score} color="#4361ee" /></Col>
                    <Col span={6}><StatisticCard label="正确" value={simulateResult.correct_count} color="#22c55e" /></Col>
                    <Col span={6}><StatisticCard label="错误" value={simulateResult.wrong_count} color="#ef4444" /></Col>
                    <Col span={6}><StatisticCard label="正确率" value={simulateResult.correct_rate + '%'} color="#f59e0b" /></Col>
                  </Row>
                </Space>
              </Card>
            )}
          </>
        )}
      </Card>
      </div>

      {/* 测评任务 */}
      <div style={{ display: assessTab === 'tasks' ? 'block' : 'none' }}>
      <Card title={<Space><ExperimentOutlined /> 测评任务</Space>} bordered={false}>
        <Space style={{ marginBottom: 16 }}>
          <Button icon={<ReloadOutlined />} onClick={loadTasks}>刷新</Button>
          <Button danger icon={<DeleteOutlined />}
            disabled={selectedTaskKeys.length === 0}
            loading={batchTaskDeleting}
            onClick={handleBatchDeleteTasks}>
            批量删除{selectedTaskKeys.length > 0 ? ` (${selectedTaskKeys.length})` : ''}
          </Button>
          <Badge count={tasks.length} overflowCount={9999} style={{ backgroundColor: '#9333ea' }} />
        </Space>
        <Table
          rowKey="id"
          loading={tasksLoading}
          dataSource={tasks}
          size="small"
          pagination={false}
          rowSelection={{
            selectedRowKeys: selectedTaskKeys,
            onChange: (keys) => setSelectedTaskKeys(keys as React.ReactText[]),
            preserveSelectedRowKeys: false,
          }}
          locale={{ emptyText: <Empty description="暂无测评任务" /> }}
          columns={[
            { title: '编号', dataIndex: 'task_code', key: 'task_code', width: 140 },
            { title: '任务名称', dataIndex: 'task_name', key: 'task_name', ellipsis: true },
            {
              title: '状态', dataIndex: 'status', key: 'status', width: 100,
              render: (v: string) => {
                const cfg = TASK_STATUS[v] || { color: 'default', text: v || '-' }
                return <Tag color={cfg.color}>{cfg.text}</Tag>
              },
            },
            { title: '对象人数', dataIndex: 'talent_count', key: 'talent_count', width: 90 },
            {
              title: '测评对象', dataIndex: 'talent_names', key: 'talent_names',
              ellipsis: true,
              render: (v: string[]) => v ? v.join('、') : '-',
            },
            {
              title: '操作', key: 'op', width: 100, fixed: 'right' as const,
              render: (_: any, r: any) => (
                <Popconfirm title="确定删除该测评任务？" onConfirm={() => handleDeleteTask(r.id)} okText="删除" cancelText="取消">
                  <Button danger type="link" size="small" icon={<DeleteOutlined />}>删除</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>
      </div>

      {/* 测评结果 */}
      <div style={{ display: assessTab === 'results' ? 'block' : 'none' }}>
      <Card title={<Space><FileTextOutlined /> 测评结果</Space>} bordered={false}>
        <Table
          rowKey="id"
          loading={resultsLoading}
          dataSource={results}
          size="small"
          pagination={false}
          locale={{ emptyText: (
                <Empty description="暂无测评结果">
                  <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                    去「试卷列表」点「开始答题」让员工真实作答，或点「AI 模拟」为某人才快速生成一份测评结果
                  </Typography.Text>
                  <div style={{ marginTop: 10 }}>
                    <Button size="small" type="primary" ghost icon={<ExperimentOutlined />}
                      onClick={() => setAssessTab('papers')}>
                      去试卷列表
                    </Button>
                  </div>
                </Empty>
              ) }}
          columns={[
            { title: '人才', dataIndex: 'talent_name', key: 'talent_name', width: 110 },
            {
              title: '总分', dataIndex: 'total_score', key: 'total_score', width: 90,
              sorter: (a: any, b: any) => (a.total_score || 0) - (b.total_score || 0),
              render: (v: any) => v != null ? v.toFixed(2) : '-',
            },
            { title: '正确/总题', key: 'count', width: 110,
              render: (_: any, r: any) => `${r.correct_count}/${r.total_count}`,
            },
            {
              title: '能力等级', dataIndex: 'capability_level', key: 'capability_level', width: 100,
              render: (v: string) => v ? <Tag color={LEVEL_TAG[v] || 'default'}>{LEVEL_LABEL[v] || v}</Tag> : '-',
            },
            {
              title: '提交时间', dataIndex: 'submitted_at', key: 'submitted_at', width: 170,
              render: (v: string) => v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '-',
            },
          ]}
        />
      </Card>
      </div>

      {/* 模拟答题弹窗 */}
      <Modal
        title={`模拟答题 —— ${simulatePaperName}`}
        open={simulateOpen}
        onOk={handleSimulateSubmit}
        onCancel={() => setSimulateOpen(false)}
        confirmLoading={simulating === simulatePaperId}
        okText="开始模拟"
        cancelText="取消"
        width={480}
      >
        <Form form={simulateForm} layout="vertical" preserve={false} initialValues={{ correct_rate: 0.8 }}>
          <Form.Item name="talent_id" label="选择人才" rules={[{ required: true, message: '请选择人才' }]}>
            <Select
              placeholder="请选择参与模拟答题的人才"
              showSearch
              optionFilterProp="label"
              options={talents.map((t) => ({
                value: t.id,
                label: `${t.name}（${t.talent_code || t.id}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="correct_rate" label="正确率（模拟正确答题占比）">
            <Slider min={0} max={1} step={0.05} marks={{ 0: '0%', 0.5: '50%', 1: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 真实答题弹框 */}
      <Modal
        title={realResult ? `${realPaperName} - 答题结果` : `真实作答 —— ${realPaperName}`}
        open={realOpen}
        onOk={() => { if (realResult) { setRealOpen(false); setRealResult(null) } else handleRealSubmit() }}
        // 单一 onCancel：同时关闭弹窗 + 清空答案，避免 React 取最后一个 props 时漏关
        onCancel={() => { setRealOpen(false); setRealResult(null) }}
        confirmLoading={realGrading}
        okText={realResult ? '关闭' : '提交答卷'}
        cancelText={realResult ? '再答一次' : '取消'}
        maskClosable={true}
        keyboard={true}
        width={720}
        destroyOnClose
      >
        {realLoading && <Spin />}
        {!realLoading && realResult && (
          <Space direction="vertical" style={{ width: '100%' }} size={12}>
            <Row gutter={12}>
              <Col span={6}><StatisticCard label="正确" value={realResult.correct_count} color="#22c55e" /></Col>
              <Col span={6}><StatisticCard label="错误" value={realResult.wrong_count} color="#ef4444" /></Col>
              <Col span={6}><StatisticCard label="得分" value={`${realResult.correct_score} / ${realResult.total_score}`} color="#4361ee" /></Col>
              <Col span={6}><StatisticCard label="正确率" value={`${realResult.accuracy}%`} color="#f59e0b" /></Col>
            </Row>
            <Card size="small" style={{ background: '#f6f8ff' }}>
              <Space><span>综合能力评级</span><Tag color="purple" style={{ fontSize: 16, padding: '2px 12px' }}>{realResult.ability_level_label}</Tag></Space>
            </Card>
            <Typography.Title level={5} style={{ marginBottom: 4 }}>逐题作答</Typography.Title>
            {(realResult.per_question || []).map((p: any, i: number) => {
              const q = realQuestions.find((x: any) => x.id === p.question_id)
              return (
                <Card key={p.question_id} size="small" style={{ background: p.correct ? '#f6ffed' : '#fff1f0' }}>
                  <div style={{ fontSize: 13 }}><b>第 {i + 1} 题</b>（{p.max_score}分）{p.correct ? <Tag color="green" style={{ marginLeft: 8 }}>正确</Tag> : <Tag color="red" style={{ marginLeft: 8 }}>错误</Tag>}</div>
                  <div style={{ color: '#666', marginTop: 4 }}>题干：{q?.question_content}</div>
                  <div style={{ marginTop: 4 }}>你的作答：<b>{p.user_answer || '（未答）'}</b></div>
                </Card>
              )
            })}
          </Space>
        )}
        {!realLoading && !realResult && (
          <Spin spinning={realLoading}>
            <div style={{ maxHeight: '55vh', overflowY: 'auto', paddingRight: 8 }}>
              {realQuestions.length === 0 ? (
                <Empty description="该试卷暂无题目" />
              ) : realQuestions.map((q: any, i: number) => {
                const qtype = q.question_type
                return (
                  <Card key={q.id} size="small" style={{ marginBottom: 12 }}>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>
                      <Tag color="blue" style={{ marginRight: 6 }}>{TYPE_LABEL[qtype] || qtype}</Tag>
                      第 {i + 1} 题（{q.score}分）
                    </div>
                    <div style={{ marginBottom: 8, whiteSpace: 'pre-wrap' }}>{q.question_content}</div>
                    {(qtype === 'single_choice' || qtype === 'true_false') && (
                      <Radio.Group
                        value={realAnswers[q.id]}
                        onChange={(e) => setRealAnswers({ ...realAnswers, [q.id]: e.target.value })}
                      >
                        <Space direction="vertical">
                          {renderOptions(q).map((o: any) => (
                            <Radio key={o.label} value={o.label}>{o.text}</Radio>
                          ))}
                        </Space>
                      </Radio.Group>
                    )}
                    {qtype === 'multiple_choice' && (
                      <Checkbox.Group
                        value={(realAnswers[q.id] || '').split(',').filter(Boolean)}
                        onChange={(v: any) => setRealAnswers({ ...realAnswers, [q.id]: v.join(',') })}
                      >
                        <Space direction="vertical">
                          {renderOptions(q).map((o: any) => (
                            <Checkbox key={o.label} value={o.label}>{o.text}</Checkbox>
                          ))}
                        </Space>
                      </Checkbox.Group>
                    )}
                    {qtype === 'fill_blank' && (
                      <Input.TextArea
                        rows={2}
                        placeholder="请输入答案"
                        value={realAnswers[q.id] || ''}
                        onChange={(e) => setRealAnswers({ ...realAnswers, [q.id]: e.target.value })}
                      />
                    )}
                    {(qtype === 'short_answer' || qtype === 'essay') && (
                      <Input.TextArea
                        rows={4}
                        placeholder="请作答"
                        value={realAnswers[q.id] || ''}
                        onChange={(e) => setRealAnswers({ ...realAnswers, [q.id]: e.target.value })}
                      />
                    )}
                    <div style={{ color: '#999', fontSize: 11, marginTop: 6 }}>
                      <Tag style={{ marginRight: 4 }}>{realAnswers[q.id] ? '已答' : '未答'}</Tag>
                    </div>
                  </Card>
                )
              })}
            </div>
          </Spin>
        )}
      </Modal>
    </Space>
  )
}

// 判断题没有 options 时兜底"正确/错误"
function renderOptions(q: any): { label: string; text: string }[] {
  const qtype = q?.question_type
  if (qtype === 'true_false') {
    const defs = [{ label: '正确', text: '正确' }, { label: '错误', text: '错误' }]
    if (!q.options || q.options.length === 0) return defs
    return (q.options || []).map((o: any) => ({
      label: typeof o === 'string' ? o : (o.label ?? o),
      text: typeof o === 'string' ? o : (o.text ?? o),
    }))
  }
  return (q.options || []).map((o: any) => ({
    label: typeof o === 'string' ? o : (o.label ?? o),
    text: typeof o === 'string' ? o : (o.text ?? o),
  }))
}

// 模拟结果统计卡片
function StatisticCard({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ background: '#fff', borderRadius: 6, padding: '12px 16px', border: '1px solid #f0f0f0' }}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{label}</Typography.Text>
      <div style={{ fontSize: 22, fontWeight: 600, color }}>{value}</div>
    </div>
  )
}
