# 接口文档陈述与服务负责人变更的影响

接口文档编辑桌校验复合示例，并按接口契约中的负责人核批。维护者手动登记每一步调用、参数与需要读取的返回字段。示例中的后续调用可以用 `$字段名` 引用前一步的输出。当版本的接口不返回该字段或示例先用了变量再取值时，不能核签。刊发回执保留当时发布的说明和示例。

## 环境

需要 Python 3.11 或更新版本。运行程序仅使用 Python 标准库。测试依赖固定为 pytest 8.3.4，可执行 `python -m pip install -r requirements-dev.txt` 安装。

## 运行

使用 `PYTHONPATH=src python -m nlp_software_doc_ownership.publisher_cli check export-v2` 查看草稿核批状态。使用 `PYTHONPATH=src python -m nlp_software_doc_ownership.publisher_cli receipt mercury-v1` 查看旧版回执。示范产品、接口和文档在 `fixtures/guide.json`。相同的锚点可以在不同产品版本中出现。

按读者选定的版本做整版审校：`PYTHONPATH=src python -m nlp_software_doc_ownership.publisher_cli review Mercury v2`；只审单页用 `review-page export-v2`。审校把自然语言指南、迁移说明（`fixtures/records.json`）与接口契约、已刊发回执一起核对，输出：

- `blocking_findings`：阻断项。`BROKEN_BINDING` 表示接口仍适用但接不到正确输入（如 `/status` 仍存在，却引用本版不再返回的 `job_id`）；`DEPRECATED_ENDPOINT` 表示接口本身已弃用，两者处置不同；另有 `STALE_FIELD_REFERENCE`、`BROKEN_CROSS_LINK` 等。
- `quarantined_statements`：待确认而非阻断的陈述。重排章节后“前一个接口”出现多个候选时，原句与候选步骤一并隔离保留，不直接删改。
- `approvals`：逐负责人给出 `carried` / `reconfirm_required` / `missing`。旧批准只有在其针对的契约指纹与示例用途指纹都未变时才沿用；迁移声明与跨步骤字段改动会让受影响负责人重新确认。
- `replacement_traces`：当前版本哪一步、哪个字段因哪条迁移说明需要替换（如 `job_id` → `ticket`，绑定 `$job_id` → `$ticket`）。
- `defaults`：从相邻句子解析出的默认值及其字段。

“除旧网关外”一类例外只豁免带对应用法标记（调用的 `tags`）的步骤，不影响其他页面的过时引用。页面陈述挂在页面声明的稳定 `anchor` 上而非 JSON 字典键，章节重排后锚点仍可核对；读者可通过 `receipt mercury-v1` 按原版号找回当初发布的内容。

从项目根目录执行 `PYTHONPATH=src python -m nlp_software_doc_ownership.cli ingest fixtures/records.json` 导入样例，随后执行 `PYTHONPATH=src python -m nlp_software_doc_ownership.cli list` 查看记录。工作数据写入 `var/records.json`。业务查询使用 fixtures/business.json 中的初始资料，约定见 fixtures/business-contract.md。执行 PYTHONPATH=src python -m nlp_software_doc_ownership.cli business 可查看当前业务目录结果。

样例为本地合成文本。记录包含来源、修订号和原文，当前工作区对空白做统一处理，并提供字符及英文词项切分。

## 测试

执行 `python -m pytest -q` 检查示例参数及其前置引用、核批权限、刊发回执和资料归档。
