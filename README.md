# 自动化审稿系统 — 法大研究生学报

中国政法大学研究生学报内部审稿管理系统，支持从投稿邮箱自动抓取、识别、暂存邮件，经主编核对后一键录入，完成派稿、编辑审稿、评分反馈全流程。

## 功能概览

- **邮件收稿** — IMAP 自动抓取投稿邮件，AI 辅助识别标题/学科/作者/联系方式，暂存待主编确认后一键录入
- **审稿流程主线** — 一审 → 二审 → 三审，每轮派稿给 1-2 名编辑，主编汇总决定（通过/返修/退稿），支持作者返修稿上传与回复通知
- **稿件管理** — 稿件全生命周期追踪，粗状态（status）+ 细阶段（workflow_stage）双重标识
- **派稿与审稿** — 主编按轮次派稿给对应方向编辑，编辑在线填写评分、审稿意见，上传审稿评分表和批注版附件
- **作者与编辑管理** — 作者信息库、编辑账号与权限管理
- **文件安全** — 基于角色的附件下载权限控制（管理员全权限，编辑仅限本人审稿稿件）
- **操作日志** — 全流程操作记录，可追溯

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3 + Flask |
| 数据库 | SQLite（journal.db） |
| 前端 | Jinja2 模板 + Bootstrap 5 + Vanilla JS |
| 邮件 | IMAP（imaplib）+ email 解析 |
| 格式处理 | python-docx、openpyxl |

## 目录结构

```
法大研究生学报/
├── 自动化审稿系统/
│   ├── 后端审稿系统/           # Flask 主程序、数据库、邮件解析
│   │   ├── webapp.py           # Web 管理系统入口
│   │   ├── create_db.py        # 数据库初始化
│   │   ├── migrate_v5_workflow.py  # v5 数据库迁移（审稿流程主线）
│   │   ├── journal.db          # SQLite 数据库
│   │   ├── uploads/            # 上传文件与邮件附件
│   │   ├── journal_automation/ # 投稿自动处理模块
│   │   │   ├── mail.py         # IMAP 收信、邮件解析、投稿过滤
│   │   │   ├── metadata.py     # 标题/学科/作者/联系方式识别
│   │   │   ├── config.py       # automation.config.json 读取
│   │   │   ├── storage.py      # 附件归档、派稿目录创建
│   │   │   ├── templates.py    # 回复草稿、审稿评分表生成
│   │   │   └── workflow.py     # 命令行自动化主流程
│   │   └── tests/              # 自动化测试
│   ├── 前端显示设计/
│   │   └── templates/          # Jinja2 模板（15 个页面）
│   └── 启动网页.command        # macOS 启动脚本
├── 0. 学报面试/
├── 1. 未处理来稿/
├── 2. 派稿及回复/
└── 6. 录用定稿/
```

## 快速开始

### 环境要求

- Python 3.8+
- macOS / Linux（局域网部署）

### 安装依赖

```bash
cd 自动化审稿系统/后端审稿系统
pip install flask flask-login python-docx openpyxl
```

### 初始化数据库

```bash
python3 create_db.py
```

### 配置邮件（可选）

复制示例配置文件，填入 126 邮箱授权码：

```bash
cp automation.config.example.json automation.config.json
# 编辑 automation.config.json，填写邮箱账号和授权码
```

### 启动

```bash
python3 webapp.py
```

默认监听 `127.0.0.1:5000`。局域网部署时修改 `HOST` 为 `0.0.0.0`：

```bash
HOST=0.0.0.0 PORT=5000 python3 webapp.py
```

> 局域网使用时务必关闭 debug 模式并设置 `SECRET_KEY`。

### 首次登录

首次运行时系统会引导创建管理员账号。

## 数据库核心表

| 表 | 用途 |
|---|---|
| `submissions` | 稿件信息（含 workflow_stage、current_round、final_decision） |
| `authors` | 作者信息 |
| `editors` | 编辑账号与权限 |
| `assignments` | 派稿与审稿记录（含轮次、编辑建议、是否返回） |
| `review_rounds` | 审稿轮次（一审/二审/三审，含主编决定、作者回复状态） |
| `author_notifications` | 作者通知记录（退稿/返修/录用通知） |
| `email_staging` | 邮件暂存箱（待核对后录入） |
| `email_sync_state` | IMAP 同步游标 |
| `submission_files` | 稿件附件（多文件支持） |
| `activity_log` | 操作日志 |

## 数据库迁移

重大结构变更通过迁移脚本完成，幂等可重复运行：

```bash
cd 自动化审稿系统/后端审稿系统
python3 migrate_v5_workflow.py  # v5: 新增 review_rounds、author_notifications 表，审稿流程主线优化
```

迁移前自动备份 `journal.db → journal.db.bak.v5`。

## 运行测试

```bash
cd 自动化审稿系统/后端审稿系统
python3 -m unittest discover -s tests -v
```

## 安全注意事项

- `automation.config.json` 含邮箱授权码，已加入 `.gitignore`，切勿提交
- 局域网部署时使用 `HOST=0.0.0.0`，关闭 `DEBUG`，设置 `SECRET_KEY`
- 编辑账号默认密码应在首次登录后强制修改
- 附件下载有基于角色的权限控制，编辑只能访问分配给自己的稿件文件

## License

内部使用，未开放授权。
