# 投稿自动处理工具

这套工具复用已有的文件夹、总表和模板，完成三件事：

- `sync-submissions`：同步 126 邮箱投稿，归档附件，并写入总表。
- `generate-reply-materials`：为指定稿件生成派稿目录、审稿评分表和作者回复草稿。
- `update-progress`：把阶段进度追加写入总表，不覆盖既有记录。

## 1. 初始化

1. 复制 `automation.config.example.json` 为 `automation.config.json`。
2. 把 `username` 改成你的 126 邮箱，把 `password` 改成 126 邮箱授权码。
3. 确认总表、模板路径没有改名。

## 2. 同步投稿邮件

```bash
cd "/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/后端审稿系统"
./run_journal_automation.sh sync-submissions
```

如果你想先拿导出的 `.eml` 邮件做离线测试：

```bash
./run_journal_automation.sh sync-submissions --eml-dir /绝对路径/邮件样本目录
```

执行后会：

- 把原始邮件存进 `.automation/raw_mail/`
- 把稿件归档到 `../../1. 未处理来稿/`
- 把信息写入 Excel 总表
- 把待人工确认项目写入 `.automation/issues/`
- 把状态写入 `.automation/journal_automation.sqlite3`

## 3. 生成派稿/回复材料

```bash
./run_journal_automation.sh generate-reply-materials \
  --record-id 1 \
  --result-label 一审返修 \
  --editor-name 张芮铭 \
  --folder-date 20260505
```

可选参数：

- `--expected-issue`：录用时写拟安排期次
- `--deadline-days`：返修默认 14 天，可改

执行后会：

- 创建 `../../2. 派稿及回复/YYYYMMDD/【阶段】学科-作者-题目/`
- 复制当前稿件进去
- 生成一份已填基础信息的审稿评分表
- 在 `.automation/drafts/` 生成一封 `.eml` 作者回复草稿

## 4. 更新总表进度

```bash
./run_journal_automation.sh update-progress \
  --record-id 1 \
  --result-label 一审返修 \
  --editor-name 张芮铭 \
  --note-date 2026.05.05
```

录用场景可以加：

```bash
--expected-issue 26年第2期
```

## 5. 查看待人工确认稿件

```bash
./run_journal_automation.sh list-pending
```

## 6. 当前边界

- 第一阶段不会自动发信，只会生成草稿。
- 第一阶段不会自动匿名化正文，只会标记"疑似未匿名"。
- 学科无法可靠识别时，会进入待人工确认列表，不自动派稿。
- `.docx` 正文识别效果最好，老式 `.doc` 目前主要依赖文件名和邮件正文信息。

## 注意

此工具为命令行自动化链路，与 Web 端（`webapp.py` / `journal.db`）是两套独立的数据链路。Web 端是当前的主要工作方式，命令行工具作为导入、导出或辅助工具使用。详见 `../AGENTS.md`。
