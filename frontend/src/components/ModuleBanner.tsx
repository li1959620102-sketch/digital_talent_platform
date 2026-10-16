import { Alert, Typography, Space, Button } from 'antd'
import { useNavigate } from 'react-router-dom'
import { RightOutlined } from '@ant-design/icons'

/**
 * 业务板块「价值引导横幅」
 *
 * 对标北森/Moka「数据闭环」理念：在每个业务板块顶部讲清——
 *   1. 这个板块帮你（角色）解决什么业务问题（价值）
 *   2. 它的数据从哪里来、会流向哪里（前后业务关联）
 *   3. 提供一个入口，让用户顺着「人才生命周期」主线走下去
 *
 * 用法：<ModuleBanner value="一句话价值" relation="前后关联说明" from="/talents" fromLabel="人才档案" next="/positions" nextLabel="岗位管理" />
 */
interface ModuleBannerProps {
  /** 本板块一句话业务价值 */
  value: string
  /** 本板块在人才生命周期中的位置说明（从哪来→到哪去） */
  relation?: string
  /** 前置板块（生命周期上游） */
  prevPath?: string
  prevLabel?: string
  /** 后置板块（生命周期下游） */
  nextPath?: string
  nextLabel?: string
}

export default function ModuleBanner({
  value,
  relation,
  prevPath,
  prevLabel,
  nextPath,
  nextLabel,
}: ModuleBannerProps) {
  const navigate = useNavigate()

  return (
    <Alert
      type="info"
      showIcon={false}
      style={{
        marginBottom: 16,
        background: 'linear-gradient(90deg, #eef2ff 0%, #f5f3ff 100%)',
        border: '1px solid #c7d2fe',
        borderRadius: 10,
        padding: '10px 16px',
      }}
      message={
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {/* 业务价值：绿点 + 一句话 */}
          <Space size={8} style={{ alignItems: 'flex-start' }}>
            <span
              style={{
                marginTop: 5,
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: '#22c55e',
                flexShrink: 0,
              }}
            />
            <Typography.Text style={{ color: '#334155', fontSize: 13, lineHeight: 1.6 }}>
              {value}
            </Typography.Text>
          </Space>

          {/* 关联引导：如果有关联入口则显示 */}
          {(prevLabel || nextLabel || relation) && (
            <Space
              size={6}
              style={{ flexWrap: 'wrap', alignItems: 'center', color: '#64748b', fontSize: 12 }}
            >
              {relation && (
                <span style={{ marginRight: 4 }}>
                  {relation}
                </span>
              )}
              {prevLabel && prevPath && (
                <Button
                  type="link"
                  size="small"
                  icon={<RightOutlined style={{ transform: 'rotate(180deg)', fontSize: 10 }} />}
                  style={{ padding: 0, color: '#6366f1', fontSize: 12 }}
                  onClick={() => navigate(prevPath!)}
                >
                  {prevLabel}
                </Button>
              )}
              <span style={{ color: '#94a3b8' }}>→</span>
              {nextLabel && nextPath && (
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0, color: '#6366f1', fontSize: 12 }}
                  onClick={() => navigate(nextPath!)}
                >
                  {nextLabel}
                  <RightOutlined style={{ fontSize: 10 }} />
                </Button>
              )}
            </Space>
          )}
        </Space>
      }
    />
  )
}
