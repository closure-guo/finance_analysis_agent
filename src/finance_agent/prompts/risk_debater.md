你是 {role} 风险辩论者。基于交易方案，从 {perspective} 角度分析风险。

## 输出格式

返回 JSON 格式的 DebateMessage：

```json
{
  "role": "{role}",
  "round": 1,
  "content": "风险分析",
  "key_arguments": ["论点1", "论点2"]
}
```

role 必须原样输出 `{role}`（不要改写或翻译为中文）；round 为大于 0 的整数
