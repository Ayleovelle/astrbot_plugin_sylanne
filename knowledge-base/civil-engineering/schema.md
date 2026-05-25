# 知识库数据字段

`assets/openalex_civil_engineering_works.jsonl.gz` 每行是一条 JSON 记录。

核心字段：

- `id`：OpenAlex work ID。
- `doi`：DOI URL，可能为空。
- `title`：论文标题。
- `year`：出版年份。
- `publication_date`：出版日期。
- `type`：文献类型。
- `language`：语言。
- `authors`：作者名列表，最多保留前 12 位。
- `venue`：期刊、会议或来源名称。
- `publisher`：出版组织。
- `cited_by_count`：OpenAlex 引用数。
- `is_oa`：是否开放获取。
- `oa_status`：OA 状态。
- `landing_page_url`：落地页。
- `pdf_url`：开放 PDF 链接，可能为空；不要批量下载未确认许可的 PDF。
- `primary_topic`：OpenAlex 主题。
- `topics`：主题列表。
- `keywords`：关键词列表，轻量构建时可能为空。
- `abstract`：由 OpenAlex 倒排索引重建的摘要，轻量构建时通常为空，可后续增量补齐。
- `themes`：本 skill 按关键词粗分类的毕业设计主题。
- `source`：固定为 `openalex`。
- `retrieved_at`：采集时间。

验证指标：

- 去重后记录数不少于 20,000。
- 至少 95% 记录应有 `id` 和 `title`。
- 尽量保留 DOI、OA 状态和来源链接，便于核查。
- 不用本库记录替代学校要求的正式参考文献格式；引用前应二次核对 DOI、题名、作者和出版信息。
