// replicate-chat-home Task 2.1：空态首页建议卡片（静态配置）。
// 卡片点击仅填入输入框、不直接发送（delta spec）。
export interface SuggestionCard {
  icon: string
  title: string
  prompt: string
}

export const SUGGESTION_CARDS: SuggestionCard[] = [
  { icon: 'fa-chart-line', title: '深度分析', prompt: '分析宁德时代' },
  { icon: 'fa-file-alt', title: '财报解读', prompt: '300750 最新财报解读' },
  { icon: 'fa-search', title: '最新消息', prompt: '茅台最新消息和市场动态' },
  { icon: 'fa-balance-scale', title: '对比研究', prompt: '对比茅台和五粮液的财务表现' },
]
