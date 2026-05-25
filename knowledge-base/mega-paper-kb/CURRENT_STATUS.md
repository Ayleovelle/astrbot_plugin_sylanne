# 当前状态

## 已完成，可上传

已完成 4 个主题，每个主题包含：

- 20000 条 OpenAlex 文献元数据。
- 500 条高被引期刊论文线索。
- Markdown 分卷。
- AstrBot 上传批次。

完成主题：

- 机器学习
- 神经网络
- 计算机科学
- 数学建模

上传目录：

- `G:\pet\astrbot_migration\mega-paper-kb\upload-batches`

上传顺序：

- `G:\pet\astrbot_migration\mega-paper-kb\upload-batches\UPLOAD_ORDER.md`

当前批次数：

- 18 批，每批不超过 10 个文件。

## 未完成，已保留断点

当前断点：

- 有限元分析：3100 / 20000。

断点文件：

- `G:\pet\astrbot_migration\mega-paper-kb\raw\finite-element-analysis\finite-element-analysis_full_state.json`

## 暂停原因

OpenAlex 返回 `429 Too Many Requests`，说明当前请求频率或额度触发限流。已将构建器改为：

- 429 后长等待。
- 成功请求之间默认等待 5 秒。
- 可用 `--request-sleep` 进一步降低频率。

## 续跑命令

限流恢复后，从有限元继续：

```powershell
& 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' G:\pet\astrbot_migration\mega-paper-kb\build_mega_paper_kb.py --subjects G:\pet\astrbot_migration\mega-paper-kb\subjects.json --only finite-element-analysis --request-sleep 10
```

后续主题可以分组继续，例如：

```powershell
& 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' G:\pet\astrbot_migration\mega-paper-kb\build_mega_paper_kb.py --subjects G:\pet\astrbot_migration\mega-paper-kb\subjects.json --only bridge-engineering,tunnel-engineering,structural-engineering --request-sleep 10
```

