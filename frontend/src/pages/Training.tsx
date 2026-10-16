import { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, message, Space, Card,
  Tag, Row, Col, Typography, Tabs, Badge, Popconfirm, DatePicker,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, BookOutlined, ScheduleOutlined, DeleteOutlined,
} from '@ant-design/icons'
import {
  listCourses, listTrainingPlans, createCourse, createTrainingPlan,
  deleteCourse, deleteTrainingPlan, batchDeleteCourses, batchDeleteTrainingPlans,
} from '../api'
import ModuleBanner from '../components/ModuleBanner'
import dayjs from 'dayjs'

const CATEGORY_OPTIONS = ['技术', '管理', '通识', '安全', '合规'].map((v) => ({ value: v, label: v }))
const TYPE_OPTIONS = [
  { value: 'video', label: '视频' },
  { value: 'doc', label: '文档' },
  { value: 'live', label: '直播' },
  { value: 'exam', label: '考试' },
]
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  // 课程状态
  published: { color: 'green', text: '已发布' },
  draft: { color: 'default', text: '草稿' },
  offline: { color: 'red', text: '已下架' },
  active: { color: 'green', text: '已上架' },
  // 学习计划 / 培训状态（兜底完整映射，避免业务用户看到 in_progress 等英文）
  in_progress: { color: 'processing', text: '进行中' },
  completed: { color: 'cyan', text: '已完成' },
  cancelled: { color: 'red', text: '已取消' },
}

export default function Training() {
  // 课程库
  const [courses, setCourses] = useState<any[]>([])
  const [selectedCourseKeys, setSelectedCourseKeys] = useState<React.ReactText[]>([])
  const [batchCourseDeleting, setBatchCourseDeleting] = useState(false)
  const [courseTotal, setCourseTotal] = useState(0)
  const [coursePage, setCoursePage] = useState(1)
  const [courseLoading, setCourseLoading] = useState(false)
  const [courseOpen, setCourseOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [courseForm] = Form.useForm()

  // 学习计划
  const [plans, setPlans] = useState<any[]>([])
  const [selectedPlanKeys, setSelectedPlanKeys] = useState<React.ReactText[]>([])
  const [batchPlanDeleting, setBatchPlanDeleting] = useState(false)
  const [planTotal, setPlanTotal] = useState(0)
  const [planPage, setPlanPage] = useState(1)
  const [planLoading, setPlanLoading] = useState(false)
  const [planOpen, setPlanOpen] = useState(false)
  const [planForm] = Form.useForm()

  const loadCourses = async (p = coursePage) => {
    setCourseLoading(true)
    try {
      const res = await listCourses({ page: p, page_size: 10 })
      setCourses(res.items || [])
      setCourseTotal(res.total || 0)
      setCoursePage(p)
    } catch (e: any) {
      message.error(e.message || '加载课程失败')
    } finally {
      setCourseLoading(false)
    }
  }

  const loadPlans = async (p = planPage) => {
    setPlanLoading(true)
    try {
      const res = await listTrainingPlans({ page: p, page_size: 10 })
      setPlans(res.items || [])
      setPlanTotal(res.total || 0)
      setPlanPage(p)
    } catch (e: any) {
      message.error(e.message || '加载学习计划失败')
    } finally {
      setPlanLoading(false)
    }
  }

  useEffect(() => {
    loadCourses(1)
    loadPlans(1)
  }, [])  // eslint-disable-line

  const handleCreateCourse = async () => {
    try {
      const values = await courseForm.validateFields()
      setSubmitting(true)
      await createCourse(values)
      message.success('课程创建成功')
      setCourseOpen(false)
      courseForm.resetFields()
      loadCourses(1)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleCreatePlan = async () => {
    try {
      const values = await planForm.validateFields()
      setSubmitting(true)
      // DatePicker 值转字符串
      const payload = {
        ...values,
        start_time: values.start_time ? dayjs(values.start_time).format('YYYY-MM-DD') : undefined,
        end_time: values.end_time ? dayjs(values.end_time).format('YYYY-MM-DD') : undefined,
      }
      await createTrainingPlan(payload)
      message.success('学习计划创建成功')
      setPlanOpen(false)
      planForm.resetFields()
      loadPlans(1)
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  // 删除课程
  const handleDeleteCourse = async (id: number) => {
    try {
      await deleteCourse(id)
      message.success('课程已删除')
      loadCourses()
      setSelectedCourseKeys([])
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 批量删除课程
  const handleBatchDeleteCourses = async () => {
    if (selectedCourseKeys.length === 0) {
      message.warning('请先勾选要删除的课程')
      return
    }
    try {
      setBatchCourseDeleting(true)
      const res = await batchDeleteCourses(selectedCourseKeys.map((k: any) => Number(k)))
      message.success(`批量删除成功：共删除 ${res?.deleted ?? selectedCourseKeys.length} 条`)
      setSelectedCourseKeys([])
      loadCourses()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchCourseDeleting(false)
    }
  }

  // 删除学习计划
  const handleDeletePlan = async (id: number) => {
    try {
      await deleteTrainingPlan(id)
      message.success('学习计划已删除')
      loadPlans()
      setSelectedPlanKeys([])
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 批量删除学习计划
  const handleBatchDeletePlans = async () => {
    if (selectedPlanKeys.length === 0) {
      message.warning('请先勾选要删除的学习计划')
      return
    }
    try {
      setBatchPlanDeleting(true)
      const res = await batchDeleteTrainingPlans(selectedPlanKeys.map((k: any) => Number(k)))
      message.success(`批量删除成功：共删除 ${res?.deleted ?? selectedPlanKeys.length} 条`)
      setSelectedPlanKeys([])
      loadPlans()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchPlanDeleting(false)
    }
  }

  const courseColumns = [
    { title: '课程编号', dataIndex: 'course_code', key: 'course_code', width: 160 },
    { title: '课程名称', dataIndex: 'course_name', key: 'course_name' },
    { title: '分类', dataIndex: 'course_category_label', key: 'course_category_label', width: 90 },
    { title: '类型', dataIndex: 'course_type_label', key: 'course_type_label', width: 80 },
    { title: '时长(分)', dataIndex: 'duration_minutes', key: 'duration_minutes', width: 90 },
    { title: '讲师', dataIndex: 'instructor', key: 'instructor', width: 100 },
    {
      title: '状态', dataIndex: 'status_label', key: 'status_label', width: 90,
      render: (v: string, r: any) => {
        const raw = r?.status
        const cfg = STATUS_TAG[raw] || { color: 'default', text: v || raw || '-' }
        return <Tag color={cfg.color}>{v || cfg.text}</Tag>
      },
    },
    {
      title: '评分', key: 'rating', width: 90,
      render: (_: any, r: any) => (r.rating != null ? `${r.rating} (${r.rating_count})` : '-'),
    },
    {
      title: '操作', key: 'action', width: 90, fixed: 'right' as const,
      render: (_: any, r: any) => (
        <Popconfirm title="确定删除该课程？" onConfirm={() => handleDeleteCourse(r.id)} okText="删除" cancelText="取消">
          <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ]

  const planColumns = [
    { title: '计划编号', dataIndex: 'plan_code', key: 'plan_code', width: 160 },
    { title: '计划名称', dataIndex: 'plan_name', key: 'plan_name' },
    {
      title: '目标类型', dataIndex: 'target_type', key: 'target_type', width: 100,
      render: (v: string) => v === 'batch' ? '批量' : v === 'individual' ? '个人' : v || '-',
    },
    {
      title: '课程数', key: 'course_count', width: 80,
      render: (_: any, r: any) => (r.courses?.length || 0),
    },
    {
      title: '起止时间', key: 'time', width: 220,
      render: (_: any, r: any) => `${r.start_time || '-'} ~ ${r.end_time || '-'}`,
    },
    {
      title: '是否考核', dataIndex: 'examination_required', key: 'examination_required', width: 90,
      render: (v: boolean) => v ? <Tag color="orange">需考核</Tag> : <Tag>否</Tag>,
    },
    {
      title: '状态', dataIndex: 'status_label', key: 'status_label', width: 90,
      render: (v: string, r: any) => {
        const raw = r?.status
        const cfg = STATUS_TAG[raw] || { color: 'default', text: v || raw || '-' }
        return <Tag color={cfg.color}>{v || cfg.text}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 90, fixed: 'right' as const,
      render: (_: any, r: any) => (
        <Popconfirm title="确定删除该学习计划？" onConfirm={() => handleDeletePlan(r.id)} okText="删除" cancelText="取消">
          <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><BookOutlined /> 培训管理</Space>
      </Typography.Title>

      <ModuleBanner
        value="针对测评暴露的能力短板，定向安排课程与学习计划，实现「缺什么、补什么」的精准培养。"
        relation="培训承接测评短板，闭环于能力提升："
        prevLabel="测评管理"
        prevPath="/assessments"
        nextLabel="人才档案"
        nextPath="/talents"
      />

      <Tabs
        defaultActiveKey="courses"
        items={[
          {
            key: 'courses',
            label: <span><BookOutlined /> 课程库</span>,
            children: (
              <Card bordered={false}>
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setCourseOpen(true)}>新增课程</Button>
                  <Button icon={<ReloadOutlined />} onClick={() => loadCourses()}>刷新</Button>
                  <Button danger icon={<DeleteOutlined />} disabled={selectedCourseKeys.length === 0} loading={batchCourseDeleting} onClick={handleBatchDeleteCourses}>
                    批量删除{selectedCourseKeys.length > 0 ? ` (${selectedCourseKeys.length})` : ''}
                  </Button>
                  <Badge count={courseTotal} overflowCount={9999} style={{ backgroundColor: '#4361ee' }} />
                </Space>
                <Table
                  rowKey="id"
                  loading={courseLoading}
                  dataSource={courses}
                  columns={courseColumns}
                  scroll={{ x: 900 }}
                  rowSelection={{
                    selectedRowKeys: selectedCourseKeys,
                    onChange: (keys: any) => setSelectedCourseKeys(keys),
                    preserveSelectedRowKeys: false,
                  }}
                  pagination={{
                    total: courseTotal,
                    current: coursePage,
                    pageSize: 10,
                    showTotal: (t) => `共 ${t} 条`,
                    onChange: (p) => loadCourses(p),
                  }}
                />
              </Card>
            ),
          },
          {
            key: 'plans',
            label: <span><ScheduleOutlined /> 学习计划</span>,
            children: (
              <Card bordered={false}>
                <Space style={{ marginBottom: 16 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setPlanOpen(true)}>新增学习计划</Button>
                  <Button icon={<ReloadOutlined />} onClick={() => loadPlans()}>刷新</Button>
                  <Button danger icon={<DeleteOutlined />} disabled={selectedPlanKeys.length === 0} loading={batchPlanDeleting} onClick={handleBatchDeletePlans}>
                    批量删除{selectedPlanKeys.length > 0 ? ` (${selectedPlanKeys.length})` : ''}
                  </Button>
                  <Badge count={planTotal} overflowCount={9999} style={{ backgroundColor: '#4361ee' }} />
                </Space>
                <Table
                  rowKey="id"
                  loading={planLoading}
                  dataSource={plans}
                  columns={planColumns}
                  scroll={{ x: 900 }}
                  rowSelection={{
                    selectedRowKeys: selectedPlanKeys,
                    onChange: (keys: any) => setSelectedPlanKeys(keys),
                    preserveSelectedRowKeys: false,
                  }}
                  pagination={{
                    total: planTotal,
                    current: planPage,
                    pageSize: 10,
                    showTotal: (t) => `共 ${t} 条`,
                    onChange: (p) => loadPlans(p),
                  }}
                />
              </Card>
            ),
          },
        ]}
      />

      {/* 新增课程 Modal */}
      <Modal
        title="新增课程"
        open={courseOpen}
        onOk={handleCreateCourse}
        onCancel={() => { setCourseOpen(false); courseForm.resetFields() }}
        confirmLoading={submitting}
        width={640}
        okText="创建"
        cancelText="取消"
      >
        <Form form={courseForm} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={24}>
              <Form.Item name="course_name" label="课程名称" rules={[{ required: true, message: '请输入课程名称' }]}>
                <Input placeholder="如：Python进阶开发" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="course_category" label="分类">
                <Select options={CATEGORY_OPTIONS} placeholder="请选择" allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="course_type" label="类型">
                <Select options={TYPE_OPTIONS} placeholder="请选择" allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="duration_minutes" label="时长(分钟)" initialValue={60}>
                <InputNumber min={0} max={600} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="instructor" label="讲师">
                <Input placeholder="如：张老师" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="course_url" label="课程链接">
                <Input placeholder="如：https://..." />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 新增学习计划 Modal */}
      <Modal
        title="新增学习计划"
        open={planOpen}
        onOk={handleCreatePlan}
        onCancel={() => { setPlanOpen(false); planForm.resetFields() }}
        confirmLoading={submitting}
        width={640}
        okText="创建"
        cancelText="取消"
      >
        <Form form={planForm} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={24}>
              <Form.Item name="plan_name" label="计划名称" rules={[{ required: true, message: '请输入计划名称' }]}>
                <Input placeholder="如：2026新员工入职培训" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="target_type" label="目标类型" initialValue="batch">
                <Select options={[{ value: 'batch', label: '批量' }, { value: 'individual', label: '个人' }]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="examination_required" label="是否需要考核" initialValue={false}>
                <Select options={[{ value: true, label: '需要' }, { value: false, label: '不需要' }]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="start_time" label="开始时间">
                <DatePicker style={{ width: '100%' }} placeholder="选择开始日期" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="end_time" label="结束时间">
                <DatePicker style={{ width: '100%' }} placeholder="选择结束日期" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Space>
  )
}
