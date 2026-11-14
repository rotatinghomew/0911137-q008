# 本地接口

- `GET /api/catalog`：资料名称、可选业务范围、业务时点范围、表计数、资料指纹与关联筛选默认值（`link_defaults`）。
- `GET /api/view`：当前摘要，可选 `cutoff` 整数、`group` 业务范围、`window` 关联时窗（1–365 个时标）、`exclude_public`（`true`/`false`）和 `capacity` 批次容量（1–1000）；未知或非法筛选项返回 400。
- `GET /api/source?table=claims`：按实际资料表名称查询原始记录；不存在的表返回 404。
- `POST /api/analyses`：JSON 对象包含 `title` 与 `options`，重新计算并保存，成功返回 201。`options` 与当前摘要的筛选结构相同。
- `GET /api/analyses`：只返回版本目录及资料指纹。
- `GET /api/analyses/{id}`：返回保存的完整结果，不重新计算。

API 的 `rows` 是原有单笔金额领域行，`summary` 是当前汇总，`notes` 是业务口径提示，`options` 是实际采用的筛选值。无记录使用空列表，不能把无观测偷偷表示为有效的零值。错误 JSON 的 `error` 可直接在页面反馈。

在原有字段之外，`/api/view` 的结果还包含：

- `leads`：按优先级排序的关联线索。每条含 `lead_id`、`claims`、`evidence`（按 `evidence_id` 去重的独立凭证及修订）、`reasons`、`score_parts`、`priority`、`reviews`、`outcome`（`confirmed`/`dismissed`/`unknown`）和 `correction`。
- `evaluation`：批次内已结案反馈的精确率、威尔逊区间、前 K 条曲线、单笔金额排序对照与 `next_batch`；同时给出 `method` 与 `selection_bias` 口径说明。
- `correction`：`material_corrections`（当前可见的实质性更正）、`affected_leads`（需重算的线索）与 `retired_leads`（更正后不再成立的旧线索，保留原提出原因和支撑记录）。
- `options`、`score_weights`：采用值与排序权重。

每条线索只是待复核入口，不是违规结论；`unknown` 表示没有已结案反馈，不能当作正常。口径细节见 `link-review.md`。

这是本地单用户应用，不包含认证与外网部署设置。默认只监听回环地址，容器中可显式监听所有接口，但宿主机端口建议只绑定回环地址。
