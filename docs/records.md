# 记录样式

以下为当前业务文件中的实际记录，字段口径见 `data-contract.md`；字段标识保持业务接口写法。

### `claims`

字段：`amount`、`claim`、`day`、`employee`、`payee`、`project`。

```json
{
  "claim": "x000",
  "employee": "e0",
  "payee": "p0",
  "project": "项目1",
  "amount": 933.47,
  "day": 1
}
```

### `relations`

字段：`employee`、`evidence_id`、`payee`、`recorded_at`、`relation`、`valid_from`、`valid_to`。同一 `relation` 可有多条修订，`recorded_at` 决定该修订何时对分析可见；页面按 `evidence_id` 合并同一凭证的多条边。

```json
{
  "relation": "r0",
  "employee": "e0",
  "payee": "p0",
  "evidence_id": "x000",
  "valid_from": 1,
  "valid_to": null,
  "recorded_at": 1
}
```

### `payees`

字段：`name`、`payee`、`public_service`。

```json
{
  "payee": "p0",
  "public_service": true,
  "name": "服务商0"
}
```

### `reviews`

字段：`claim`、`result`、`reviewed_at`。

```json
{
  "claim": "x000",
  "result": "needs_followup",
  "reviewed_at": 8
}
```
