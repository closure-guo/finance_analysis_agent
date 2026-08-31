// 「汉堡 ⇄ X」形变图标（sidebar 折叠按钮）。
// 风格：粗描边直线（stroke 3 + round 端帽），X 态为 4 条臂 + 中心小点。
// 动画：CSS d 属性过渡（Chromium/Firefox 原生支持，见 index.css
// .menu-toggle-path 规则）；不支持该属性的浏览器降级为无动画直接切换。
// 形态映射：P1 顶线→右上臂、P2 中线左段+右小段→中心点+右下臂、
// P3 底线→左下臂、P4 藏于顶线（重合不可见）→左上臂。
const paths = [
  // P1：顶线（全宽） → 右上臂
  {
    closed: 'M 5 9.5 L 27 9.5',
    open: 'M 20.5 11.5 L 26 6',
  },
  // P2：中线左段 + 右小段 → 中心点 + 右下臂
  {
    closed: 'M 5 16 L 17 16 M 21.5 16 L 27 16',
    open: 'M 15.4 16 L 16.6 16 M 20.5 20.5 L 26 26',
  },
  // P3：底线（全宽） → 左下臂
  {
    closed: 'M 5 22.5 L 27 22.5',
    open: 'M 11.5 20.5 L 6 26',
  },
  // P4：藏于顶线左段（重合不可见） → 左上臂
  {
    closed: 'M 5 9.5 L 13 9.5',
    open: 'M 11.5 11.5 L 6 6',
  },
]

export function MenuToggleIcon({ open, className }: { open: boolean; className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      stroke="currentColor"
      strokeWidth={3}
      strokeLinecap="round"
      className={className ?? 'size-5'}
    >
      {paths.map((p, i) => (
        <path
          key={i}
          className="menu-toggle-path"
          style={{ d: `path("${open ? p.open : p.closed}")` }}
        />
      ))}
    </svg>
  )
}