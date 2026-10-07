import { describe, expect, it } from 'vitest'
import { PREDICTION_STATUS_CLS, PREDICTION_STATUS_LABEL } from '../../pages/trackRecord/predictionStatus'

describe('duplicate_of_day 状态映射（add-prediction-pool-integrity）', () => {
  it('标签为「同日重复」', () => {
    expect(PREDICTION_STATUS_LABEL.duplicate_of_day).toBe('同日重复')
  })
  it('配色为三级灰（非成功/错误语义）', () => {
    expect(PREDICTION_STATUS_CLS.duplicate_of_day).toContain('text-tertiary')
  })
})
