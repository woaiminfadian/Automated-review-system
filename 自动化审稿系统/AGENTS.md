# 自动化审稿系统 Agent 快速说明

本文档用于帮助新的 coding agent 快速理解本项目。开始修改前，请先阅读本文件，再按需阅读具体源码。

## 项目定位

这是“中国政法大学研究生学报”内部使用的本地审稿管理系统，目标是支持多人协作完成：

1. 从投稿邮箱抓取新邮件。
2. 识别投稿信息与附件。
3. 暂存邮件，供主编人工核对。
4. 录入稿件、作者、编辑、派稿记录。
5. 编辑登录后查看自己的审稿任务。
6. 编辑提交评分、审稿意见、审稿评分表和批注版附件。
7. 管理员查看稿件流转和审稿进度。

当前最适合的发展方向是：稳定的本地/局域网 Web 审稿工作台，而不是重新做原生 app。

## 目录结构

项目根目录：

```text
/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统
```

关键目录：

```text
前端显示设计/templates/      Flask/Jinja2 前端模板
后端审稿系统/               Flask 后端、数据库、邮件解析、自动化脚本
启动网页.command            macOS 启动脚本
```

后端关键文件：

```text
后端审稿系统/webapp.py                  Web 管理系统主程序
后端审稿系统/create_db.py               初始化 journal.db
后端审稿系统/import_xlsx.py             从既有 Excel 台账导入数据
后端审稿系统/journal.db                 Web 系统 SQLite 数据库
后端审稿系统/uploads/                   Web 端上传与邮件附件目录
后端审稿系统/journal_cli.py             旧版交互式命令行管理工具
后端审稿系统/journal_automation/        投稿自动处理模块
后端审稿系统/tests/                     自动化测试
```

自动化模块关键文件：

```text
journal_automation/mail.py        IMAP/POP3 收信、邮件解析、投稿邮件过滤
journal_automation/metadata.py    题名、学科、作者、联系方式识别
journal_automation/workflow.py    命令行自动化主流程
journal_automation/storage.py     附件归档、派稿目录创建
journal_automation/templates.py   回复草稿、审稿评分表生成
journal_automation/workbook.py    Excel 台账写入与进度更新
journal_automation/state.py       命令行自动化自己的 SQLite 状态库
journal_automation/config.py      automation.config.json 读取
```

## 两套数据链路

系统目前存在两套数据链路，开发时要特别注意。

### Web 主链路

Web 端使用：

```text
后端审稿系统/journal.db
```

主要表：

```text
authors           作者
submissions       稿件
editors           编辑账号
assignments       派稿与审稿记录
activity_log      操作日志
email_staging     邮件暂存箱
email_sync_state  Web 邮件同步游标
```

Web 邮件流程：

```text
/api/email/fetch
  -> 读取 email_sync_state.last_uid
  -> IMAP 抓取新邮件
  -> is_submission_email 过滤
  -> parse_submission 解析
  -> 写入 email_staging
  -> 附件保存到 uploads/email_staging/<staging_id>/

/api/email/import/<staging_id>
  -> 从 email_staging 创建 submissions/authors
  -> 附件移动到 uploads/submission_<submission_id>/
  -> submissions.file_path 当前主要记录第一个附件路径
```

编辑审稿流程：

```text
管理员创建 assignment
  -> 编辑登录 /editor/
  -> 打开 /editor/review/<assignment_id>
  -> 填评分、审稿意见
  -> 上传 file_review / file_annotated
  -> 文件保存到 uploads/review_<assignment_id>/
  -> assignments 记录返回文件路径
```

### 命令行自动化链路

命令行工具使用：

```text
后端审稿系统/.automation/journal_automation.sqlite3
```

并会写入：

```text
法大研究生学报/1. 未处理来稿/
法大研究生学报/2. 派稿及回复/
私法组审稿（2025—2026学年）.xlsx
```

入口：

```bash
cd "/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/后端审稿系统"
./run_journal_automation.sh sync-submissions
./run_journal_automation.sh generate-reply-materials ...
./run_journal_automation.sh update-progress ...
```

注意：Web 主链路和命令行自动化链路尚未完全统一。多人协作审稿时，优先围绕 Web 端 `journal.db` 开发；Excel 和命令行自动化可作为导入、导出或辅助工具。

## 前端页面

模板目录：

```text
/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/前端显示设计/templates
```

主要页面：

```text
base.html                    全局布局、侧边栏、公共样式、脚本
dashboard.html               管理员总览
email_inbox.html             邮件暂存箱
submissions.html             稿件列表
submission_detail.html       稿件详情
submission_add.html          手动录入稿件
submission_edit.html         编辑稿件
assignments.html             派稿管理
assignment_add.html          新建派稿
editor_dashboard.html        编辑端“我的审稿”
editor_review.html           编辑提交审稿意见
authors.html                 作者管理
editors.html                 编辑管理
login.html / setup.html      登录与首次设置
```

UI 目标：

- 简洁、高效、排版紧凑。
- 以审稿流程为主线：邮件收稿 -> 核对录入 -> 派稿 -> 编辑审稿 -> 查看返回结果。
- 常用动作应直接露出，不要全部藏在齿轮菜单中。
- 管理员和普通编辑入口要区分，普通编辑不应进入管理员详情页。
- 表格优先承载信息，减少大块装饰卡片。

## 附件保存现状

当前 Web 端附件路径：

```text
uploads/email_staging/<staging_id>/       邮件暂存附件
uploads/submission_<submission_id>/       稿件录入后的投稿附件
uploads/review_<assignment_id>/           编辑返回的审稿评分表、批注版
```

当前限制：

- `submissions.file_path` 主要记录第一个投稿附件。
- 多个投稿附件尚未结构化为独立表。
- 编辑端可以上传审稿评分表和批注版，但原稿/投稿附件下载链路仍需完善。

建议后续优化：

- 新增 `submission_files` 表，记录每篇稿件的全部附件。
- 使用文件 id 下载，不直接暴露任意路径。
- 管理员可下载所有稿件附件；普通编辑只能下载分配给自己的稿件附件。
- 在 `editor_review.html` 增加“稿件附件下载”区域。

## 邮件同步逻辑

Web 端收信入口：

```text
POST /api/email/fetch
```

当前逻辑：

1. 从 `email_sync_state.last_uid` 读取上次同步位置。
2. 使用 `journal_automation.mail.fetch_messages_from_imap` 抓取新邮件。
3. 使用 `is_submission_email` 过滤非投稿邮件。
4. 使用 `Message-ID` 检查是否已暂存。
5. 写入 `email_staging`。
6. 推进 `last_uid`。

重要注意：

- 126 邮箱可能出现 Unsafe Login 或 IMAP 限制。
- 轮询收信比 IMAP IDLE 更稳，建议以后台定时检查为主。
- 新增后台 worker 时，应避免重复处理：用 UID 游标 + Message-ID 双重去重。

## 启动方式

推荐在后端目录运行：

```bash
cd "/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/后端审稿系统"
python3 webapp.py
```

可指定端口：

```bash
python3 webapp.py 5001
```

也可使用环境变量：

```bash
HOST=127.0.0.1 PORT=5000 DEBUG=false SECRET_KEY=... python3 webapp.py
```

当前 `webapp.py` 默认：

```text
HOST=127.0.0.1
PORT=5000
DEBUG=false
```

如果要让局域网内其他编辑访问，需要将 `HOST` 设为本机局域网 IP 或 `0.0.0.0`，但不要开启 debug。

## 常用验证命令

语法检查建议使用临时 pycache，避免 macOS 系统缓存权限问题：

```bash
cd "/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/后端审稿系统"
PYTHONPYCACHEPREFIX=/private/tmp/journal_pycache python3 -m compileall -q .
```

运行测试：

```bash
cd "/Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/后端审稿系统"
python3 -m unittest discover -s tests -v
```

如果测试失败，先确认测试中的模板路径是否与当前目录结构一致。

## 配置与敏感信息

`automation.config.json` 包含邮箱账号和授权码，不应提交或泄露。当前 `.gitignore` 已忽略：

```text
automation.config.json
*.sqlite3
__pycache__/
*.pyc
.DS_Store
```

示例配置：

```text
后端审稿系统/automation.config.example.json
```

如果需要恢复真实配置，应由用户本地提供，不要在回复中打印邮箱授权码。

## 已知问题与优先优化项

高优先级：

1. 统一 Web 端和命令行自动化的数据主线，优先以 `journal.db` 为主。
2. 将投稿附件结构化，新增 `submission_files` 表。
3. 完善编辑端下载原稿/附件、上传审稿文件的闭环。
4. 邮件收稿增加后台轮询服务，实现接近实时处理。
5. 前端 UI 改为紧凑工作台：减少大卡片、强化流程按钮联动。
6. 取消固定默认密码或强制首次登录修改。
7. 多人局域网使用时，关闭 debug，设置稳定 SECRET_KEY。

中优先级：

1. `templates.py` 生成 Word 评分表时依赖 XML 字符串替换，模板变动后可能静默失败。
2. `is_submission_email` 和 `parse_submission` 会重复解析附件，可优化性能。
3. 邮件正文 HTML 目前只做文本抽取，复杂邮件格式可能识别不稳定。
4. `.doc` 老格式正文识别能力有限，主要依赖文件名和邮件正文。

## 开发约束

请 agent 修改代码时遵守：

1. 不要重置或删除 `journal.db`。
2. 不要删除 `uploads/` 里的既有文件。
3. 不要覆盖用户已有稿件、评分表、批注版。
4. 数据库结构调整应提供迁移逻辑，兼容旧库。
5. 不要把真实邮箱授权码、密码写入代码或文档。
6. 普通编辑权限必须小于管理员；下载附件时尤其要检查 assignment 权限。
7. 优先保持现有路由名和数据库字段兼容。
8. 前端不引入复杂构建工具，继续使用 Flask/Jinja2 + Bootstrap。
9. 修改后至少跑语法检查；如涉及流程，尽量启动 Web 服务手动验证页面。

## 推荐给新 agent 的第一句话

可以这样开始新对话：

```text
请先阅读 /Users/zhangruiming/Desktop/法大研究生学报/自动化审稿系统/AGENTS.md，
再根据其中的项目结构和开发约束，继续维护自动化审稿系统。
```

