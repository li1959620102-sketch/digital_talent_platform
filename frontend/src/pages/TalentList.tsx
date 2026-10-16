import { useEffect, useState } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, message, Space, Card,
  Tag, Row, Col, Typography, Popconfirm, Tooltip, Badge, Descriptions,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, DeleteOutlined,
  EyeOutlined, TeamOutlined,
} from '@ant-design/icons'
import { listTalents, createTalent, deleteTalent, batchDeleteTalents, getTalent } from '../api'
import ModuleBanner from '../components/ModuleBanner'

const GENDER_OPTIONS = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
]
const EDUCATION_OPTIONS = ['高中', '大专', '本科', '硕士', '博士'].map((v) => ({ value: v, label: v }))
const STATUS_OPTIONS = [
  { value: 'active', label: '在岗' },
  { value: 'reserve', label: '储备' },
  { value: 'on_leave', label: '休假' },
  { value: 'resigned', label: '离职' },
]
const STATUS_TAG: Record<string, { color: string; text: string }> = {
  active: { color: 'green', text: '在岗' },
  inactive: { color: 'default', text: '离职' },
  candidate: { color: 'blue', text: '候选' },
  onboarding: { color: 'orange', text: '入职中' },
  reserve: { color: 'cyan', text: '储备' },
  resigned: { color: 'default', text: '离职' },
  on_leave: { color: 'purple', text: '休假' },
}

export default function TalentList() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState({ keyword: '', gender: '', education: '', status: '' })
  const [open, setOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const load = async (p = page, ps = pageSize, filters = search) => {
    setLoading(true)
    try {
      const res = await listTalents({ page: p, page_size: ps, ...filters })
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
    const empty = { keyword: '', gender: '', education: '', status: '' }
    setSearch(empty)
    setPage(1)
    load(1, pageSize, empty)
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await createTalent(values)
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

  const handleDelete = async (id: number) => {
    try {
      await deleteTalent(id)
      message.success('已删除')
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  // 查看详情
  const openDetail = async (id: number) => {
    setDetailOpen(true)
    setDetail(null)
    setDetailLoading(true)
    try {
      const res = await getTalent(id)
      setDetail(res)
    } catch (e: any) {
      message.error(e.message || '加载详情失败')
    } finally {
      setDetailLoading(false)
    }
  }

  // 批量删除（整页删除）
  const [batchDeleting, setBatchDeleting] = useState(false)
  const handleBatchDelete = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选要删除的人才')
      return
    }
    try {
      setBatchDeleting(true)
      const res = await batchDeleteTalents(selectedRowKeys.map((k) => Number(k)))
      message.success(`批量删除成功：共删除 ${res?.deleted ?? selectedRowKeys.length} 条`)
      setSelectedRowKeys([])
      load()
    } catch (e: any) {
      message.error(e.message || '批量删除失败')
    } finally {
      setBatchDeleting(false)
    }
  }

  const columns = [
    { title: '编号', dataIndex: 'talent_code', key: 'talent_code', width: 120 },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
    {
      title: '性别', dataIndex: 'gender', key: 'gender', width: 80,
      render: (v: string) => v === 'male' ? '男' : v === 'female' ? '女' : v || '-',
    },
    { title: '学历', dataIndex: 'education', key: 'education', width: 80 },
    { title: '经验(年)', dataIndex: 'experience_years', key: 'experience_years', width: 90 },
    { title: '部门', dataIndex: 'department_name', key: 'department_name', width: 100, ellipsis: true },
    { title: '当前职位', dataIndex: 'current_position', key: 'current_position', ellipsis: true },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => {
        const cfg = STATUS_TAG[v] || { color: 'default', text: v || '-' }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: any, r: any) => (
        <Space>
          <Tooltip title="查看详情">
            <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => openDetail(r.id)} />
          </Tooltip>
          <Popconfirm title="确定删除该人才档案？" onConfirm={() => handleDelete(r.id)} okText="删除" cancelText="取消">
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Typography.Title level={4} style={{ margin: 0 }}>
        <Space><TeamOutlined /> 人才档案</Space>
      </Typography.Title>

      <ModuleBanner
        value="集中管理人才档案：简历一键入库、多维度检索、自动生成人才画像与标签，建立可持续更新的数字化人才库。"
        relation="档案是人才管理的地基："
        prevLabel="人才看板"
        prevPath="/"
        nextLabel="岗位匹配"
        nextPath="/matching"
      />

      {/* 搜索栏 */}
      <Card bordered={false} size="small">
        <Row gutter={12}>
          <Col flex="220px">
            <Input
              placeholder="姓名/手机号/邮箱"
              value={search.keyword}
              onChange={(e) => setSearch({ ...search, keyword: e.target.value })}
              onPressEnter={onSearch}
              allowClear
            />
          </Col>
          <Col flex="120px">
            <Select
              placeholder="性别"
              value={search.gender || undefined}
              onChange={(v) => setSearch({ ...search, gender: v || '' })}
              options={GENDER_OPTIONS}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col flex="120px">
            <Select
              placeholder="学历"
              value={search.education || undefined}
              onChange={(v) => setSearch({ ...search, education: v || '' })}
              options={EDUCATION_OPTIONS}
              allowClear
              style={{ width: '100%' }}
            />
          </Col>
          <Col flex="120px">
            <Select
              placeholder="状态"
              value={search.status || undefined}
              onChange={(v) => setSearch({ ...search, status: v || '' })}
              options={STATUS_OPTIONS}
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

      {/* 表格 */}
      <Card bordered={false}>
        <Space style={{ marginBottom: 16 }}>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增人才</Button>
          <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          <Button
            danger
            icon={<DeleteOutlined />}
            disabled={selectedRowKeys.length === 0}
            loading={batchDeleting}
            onClick={handleBatchDelete}
          >
            批量删除{selectedRowKeys.length > 0 ? ` (${selectedRowKeys.length})` : ''}
          </Button>
          <Badge count={total} overflowCount={9999} style={{ backgroundColor: '#4361ee' }} />
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={data}
          columns={columns}
          scroll={{ x: 1000 }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys),
            preserveSelectedRowKeys: false,
          }}
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

      {/* 新增人才 Modal */}
      <Modal
        title="新增人才档案"
        open={open}
        onOk={handleCreate}
        onCancel={() => { setOpen(false); form.resetFields() }}
        confirmLoading={submitting}
        width={640}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
                <Input placeholder="如：张三" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="gender" label="性别" rules={[{ required: true, message: '请选择性别' }]}>
                <Select options={GENDER_OPTIONS} placeholder="请选择" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="phone" label="手机号" rules={[{ required: true, message: '请输入手机号' }]}>
                <Input placeholder="如：13800138000" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="email" label="邮箱" rules={[{ type: 'email', message: '邮箱格式不正确' }]}>
                <Input placeholder="如：zhangsan@example.com" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="education" label="学历">
                <Select options={EDUCATION_OPTIONS} placeholder="请选择" allowClear />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="experience_years" label="工作经验(年)" initialValue={0}>
                <InputNumber min={0} max={50} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="current_position" label="当前职位">
                <Input placeholder="如：高级工程师" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="expected_salary" label="期望薪资(元)">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="如：20000" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="skill_tags" label="技能标签(逗号分隔)">
                <Input placeholder="如：Python,SQL,机器学习" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 人才详情 Modal */}
      <Modal
        title="人才档案详情"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={720}
        loading={detailLoading}
      >
        {detail && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="档案编号" span={2}>{detail.talent_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="姓名">{detail.name || '-'}</Descriptions.Item>
            <Descriptions.Item label="性别">
              {detail.gender === 'male' ? '男' : detail.gender === 'female' ? '女' : detail.gender || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="手机号">{detail.phone || '-'}</Descriptions.Item>
            <Descriptions.Item label="邮箱">{detail.email || '-'}</Descriptions.Item>
            <Descriptions.Item label="学历">{detail.education || '-'}</Descriptions.Item>
            <Descriptions.Item label="专业">{detail.major || '-'}</Descriptions.Item>
            <Descriptions.Item label="工作经验(年)">{detail.experience_years ?? '-'}</Descriptions.Item>
            <Descriptions.Item label="当前公司">{detail.current_company || '-'}</Descriptions.Item>
            <Descriptions.Item label="当前职位">{detail.current_position || '-'}</Descriptions.Item>
            <Descriptions.Item label="状态">
              {detail.status ? STATUS_TAG[detail.status]?.text || detail.status : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="技能标签" span={2}>
              {Array.isArray(detail.skills_certificates) && detail.skills_certificates.length > 0
                ? detail.skills_certificates.map((s: any, i: number) => (
                    <Tag key={i}>{typeof s === 'string' ? s : s.name}{s?.level ? `(${s.level})` : ''}</Tag>
                  ))
                : (detail.skill_tags || '-')}
            </Descriptions.Item>
            <Descriptions.Item label="自我介绍" span={2}>{detail.self_introduction || '-'}</Descriptions.Item>
          </Descriptions>
        )}
      </Modal>
    </Space>
  )
}
