// 「汉堡 ⇄ X」形变图标（sidebar 折叠按钮）。
// 原理：4 个 <path>（第 3 个含两段子路径），closed/open 两组 d 命令结构
// 完全相同，framer-motion 把 d 当数字序列自动插值形变；回弹感来自 spring 过渡。
// 颜色走 currentColor，暗色模式自动适配。形态映射：
// P1 顶线→右上臂、P2 中线→中心点、P3 两小段→左下+右下臂、P4 底线→左上臂。
import { motion } from 'framer-motion'

const spring = { type: 'spring', stiffness: 260, damping: 22 } as const

const paths = [
  {
    closed:
      'M 5 10 L 27 10 A 1 1 0 0 0 28 9 A 1 1 0 0 0 27 8 L 5 8 A 1 1 0 0 0 4 9 A 1 1 0 0 0 5 10',
    open:
      'M 17.4 13.2 L 23.1 7.5 A 1 1 0 0 0 24.5 7.5 A 1 1 0 0 0 24.5 8.9 L 18.8 14.6 A 1 1 0 0 0 17.4 14.6 A 1 1 0 0 0 17.4 13.2',
  },
  {
    closed: 'M 5 17 L 17 17 A 1 1 0 0 0 18 16 A 1 1 0 0 0 17 15 L 5 15 A 1 1 0 0 0 4 16 A 1 1 0 0 0 5 17',
    open:
      'M 16 15 L 16 15 A 1 1 0 0 0 17 16 A 1 1 0 0 0 16 17 L 16 17 A 1 1 0 0 0 15 16 A 1 1 0 0 0 16 15',
  },
  {
    closed:
      'M 17 17 L 19.5 17 A 1 1 0 0 0 20.5 16 A 1 1 0 0 0 19.5 15 L 17 15 A 1 1 0 0 0 16 16 A 1 1 0 0 0 17 17 M 22.5 17 L 27 17 A 1 1 0 0 0 28 16 A 1 1 0 0 0 27 15 L 22.5 15 A 1 1 0 0 0 21.5 16 A 1 1 0 0 0 22.5 17',
    open:
      'M 14.6 18.8 L 8.9 24.5 A 1 1 0 0 0 7.5 24.5 A 1 1 0 0 0 7.5 23.1 L 13.2 17.4 A 1 1 0 0 0 14.6 17.4 A 1 1 0 0 0 14.6 18.8 M 18.8 17.4 L 24.5 23.1 A 1 1 0 0 0 24.5 24.5 A 1 1 0 0 0 23.1 24.5 L 17.4 18.8 A 1 1 0 0 0 17.4 17.4 A 1 1 0 0 0 18.8 17.4',
  },
  {
    closed:
      'M 5 24 L 27 24 A 1 1 0 0 0 28 23 A 1 1 0 0 0 27 22 L 5 22 A 1 1 0 0 0 4 23 A 1 1 0 0 0 5 24',
    open:
      'M 13.2 14.6 L 7.5 8.9 A 1 1 0 0 0 7.5 7.5 A 1 1 0 0 0 8.9 7.5 L 14.6 13.2 A 1 1 0 0 0 14.6 14.6 A 1 1 0 0 0 13.2 14.6',
  },
]

export function MenuToggleIcon({ open, className }: { open: boolean; className?: string }) {
  return (
    <motion.svg
      viewBox="0 0 32 32"
      className={className ?? 'size-5'}
      initial={false}
      animate={open ? 'open' : 'closed'}
    >
      {paths.map((p, i) => (
        <motion.path
          key={i}
          fill="currentColor"
          variants={{ closed: { d: p.closed }, open: { d: p.open } }}
          transition={spring}
        />
      ))}
    </motion.svg>
  )
}