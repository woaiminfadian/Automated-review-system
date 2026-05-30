# 前后端分离改造 — Agent 执行 Prompts

## 现状

- 后端: Flask + SQLite，服务端渲染 HTML 模板
- 数据库: journal.db（10 张表）
- 页面: 15 个 Jinja2 模板
- 总路由: ~50 个

## 目标架构

```
后端 (Flask REST API, port 5678)  ←→  前端 (Vue 3 + Element Plus, port 5173)
     只返回 JSON                        独立开发服务器
```

---

## Phase 1: 后端 API 改造

### Prompt 1.1 — 初始化后端 API 项目结构

```
请在 后端审稿系统/ 目录下完成以下操作，不要改动现有的 webapp.py：

1. 新建 api/ 文件夹，包含 __init__.py
2. 新建 api/auth.py — 鉴权相关 API
3. 新建 api/dashboard.py — 仪表盘统计 API
4. 新建 api/submissions.py — 投稿 CRUD API
5. 新建 api/reviews.py — 审稿轮次 API
6. 新建 api/assignments.py — 派稿 API
7. 新建 api/authors.py — 作者管理 API
8. 新建 api/editors.py — 编辑管理 API
9. 新建 api/email.py — 邮件收稿 API
10. 新建 api/upload.py — 文件上传下载 API
11. 新建 app_api.py — 新 Flask 应用入口，加载所有 api 蓝图，启用 CORS，使用 JWT 鉴权（flask-jwt-extended）

要求：
- 每个蓝图 URL 前缀统一加 /api
- 所有 API 返回纯 JSON，格式统一为 {"code": 0, "data": ..., "message": "ok"} 或 {"code": 1, "message": "错误信息"}
- JWT token 有效期 24 小时
- 数据库操作复用现有 webapp.py 中的 get_conn()、log_activity() 等函数，从 webapp.py 提取到 api/db.py
- 在 requirements.txt 中添加 flask-cors、flask-jwt-extended
```

### Prompt 1.2 — 实现鉴权 API

```
在 api/auth.py 中实现以下接口，数据库表结构参考 create_db.py 中的 editors 表：

POST /api/auth/login
  入参: {"username": "xxx", "password": "xxx"}
  逻辑: 查 editors 表，用 werkzeug.security.check_password_hash 验证密码
  返回: {"code": 0, "data": {"token": "jwt...", "user": {"id": 1, "name": "张三", "role": "主编"}}}

POST /api/auth/logout
  无需参数，JWT 过期即视为登出

GET /api/auth/me
  返回当前登录用户信息

POST /api/auth/change-password
  入参: {"old_password": "xxx", "new_password": "xxx"}
  仅编辑角色可用

要求：
- 密码验证复用 werkzeug.security（与现有 webapp.py 一致）
- 主编 role 判断：is_admin 字段 = 1
- 所有接口（除 login）需要 @jwt_required()
```

### Prompt 1.3 — 实现仪表盘 API

```
在 api/dashboard.py 中实现：

GET /api/dashboard/stats
  返回:
  {
    "total_submissions": 总投稿数,
    "by_status": {"待处理": 5, "审稿中": 10, ...},
    "by_field": {"民法": 3, "刑法": 5, ...},
    "pending_reviews": 待审稿数,
    "active_editors": 在编辑人数,
    "recent_activity": [{最近10条操作记录}]
  }

实现方法：查询 submissions、assignments、editors、activity_log 表，聚合计算。
参考 webapp.py dashboard() 函数中的 SQL 查询逻辑。
```

### Prompt 1.4 — 实现投稿 CRUD API

```
在 api/submissions.py 中实现：

GET    /api/submissions              投稿列表（分页、筛选、搜索）
GET    /api/submissions/:id          投稿详情（含作者信息、审稿轮次、派稿记录、文件列表）
POST   /api/submissions              新建投稿
PUT    /api/submissions/:id          编辑投稿
DELETE /api/submissions/:id          删除投稿
PUT    /api/submissions/:id/status   更新投稿状态
POST   /api/submissions/:id/anonymize  匿名化处理
POST   /api/submissions/:id/revision   上传返修稿

要求：
- 列表接口支持 ?page=1&page_size=20&status=xxx&field=xxx&keyword=xxx
- 返回格式: {"code": 0, "data": {"items": [...], "total": 100}}
- 投稿详情接口要带出：作者信息、所有审稿轮次、每轮的派稿和审稿意见、文件列表
- 参考 webapp.py 中 submission_detail() 的 SQL 查询拼装逻辑
- 文件上传保存到 uploads/ 目录，结构保持现有 convention
```

### Prompt 1.5 — 实现审稿轮次 API

```
在 api/reviews.py 中实现：

GET    /api/submissions/:sid/rounds                    获取某投稿的所有审稿轮次
GET    /api/submissions/:sid/rounds/:rid               获取某轮详情（含派稿列表、主编决定）
POST   /api/submissions/:sid/rounds/:rid/decide        主编决定（通过/返修/退稿）
POST   /api/submissions/:sid/rounds/:rid/author-reply  标记作者回复

要求：
- 主编决定时更新 review_rounds.chief_decision 和 submissions.workflow_stage
- 返修时更新 review_rounds.author_reply_status = '等待回复'
- 参考 webapp.py 中 chief_decide() 和 author_reply_mark() 的业务逻辑
```

### Prompt 1.6 — 实现派稿 API

```
在 api/assignments.py 中实现：

GET    /api/assignments                派稿列表（支持 ?submission_id=xxx&editor_id=xxx&round=xxx&status=xxx）
POST   /api/assignments                新建派稿
PUT    /api/assignments/:id            更新派稿（审稿人提交审稿意见/评分）
PUT    /api/assignments/:id/retract    审稿人撤回已提交意见

要求：
- 新建派稿需要验证：同一投稿同一轮次不能重复派给同一编辑
- 更新派稿时的评分字段：score_topic, score_argument, score_innovation, score_standard, score_total
- 审稿意见字段：review_opinion, review_comment, editor_recommendation
- 参考 webapp.py 中 assignment_add() 和 editor_review() 的业务逻辑
```

### Prompt 1.7 — 实现编辑端 API

```
在 api/editors.py 中实现：

GET    /api/editors                 编辑列表
POST   /api/editors                 新增编辑
PUT    /api/editors/:id             编辑信息
DELETE /api/editors/:id             删除编辑
PUT    /api/editors/:id/toggle      启用/停用
PUT    /api/editors/:id/password    重置密码

GET    /api/editor/my-assignments   当前登录编辑的派稿列表（editor_dashboard）
GET    /api/editor/review/:aid      查看某派稿详情（稿件信息+评分表）
POST   /api/editor/review/:aid      提交审稿意见

要求：
- 编辑只能看自己的派稿
- 主编才能增删改编辑
- 参考 webapp.py 中 editors_list、editor_dashboard、editor_review 的逻辑
```

### Prompt 1.8 — 实现作者管理 API

```
在 api/authors.py 中实现：

GET    /api/authors            作者列表（支持 ?keyword=xxx 搜索）
POST   /api/authors            新增作者
PUT    /api/authors/:id        编辑作者
DELETE /api/authors/:id        删除作者

要求：
- 删除作者前检查是否有关联投稿，有则返回错误提示
- 参考 webapp.py 中 authors_list()、author_add() 等函数
```

### Prompt 1.9 — 实现邮件收稿 API

```
在 api/email.py 中实现：

GET    /api/email/inbox          邮件待处理列表
GET    /api/email/status         邮件同步状态
POST   /api/email/fetch          触发邮件抓取
POST   /api/email/import/:id     将邮件导入为投稿
POST   /api/email/confirm/:id    确认导入
POST   /api/email/dismiss/:id    忽略
POST   /api/email/undismiss/:id  恢复

要求：
- 参考 webapp.py 中 email_* 系列函数和 api_email_* 函数
- 邮件抓取为异步操作，返回任务状态
```

### Prompt 1.10 — 实现文件上传下载 API

```
在 api/upload.py 中实现：

POST   /api/upload                  上传文件（支持多文件）
GET    /api/uploads/:path           下载文件
GET    /api/download/scoring-template  下载审稿评分表模板

要求：
- 上传文件保存到 uploads/ 目录，文件名加时间戳防冲突
- 文件类型限制：.docx .doc .pdf
- 最大 50MB
```

---

## Phase 2: 前端项目初始化

### Prompt 2.1 — 创建 Vue 3 项目

```
在 自动化审稿系统/ 目录下创建前端项目：

1. 用 Vite 创建 Vue 3 项目：npm create vite@latest frontend -- --template vue
2. 进入 frontend/，安装依赖：
   - element-plus（UI 组件库）
   - vue-router（路由）
   - pinia（状态管理）
   - axios（HTTP 请求）
   - @element-plus/icons-vue（图标）
3. 配置 vite.config.js：
   - 开发服务器端口 5173
   - 代理 /api 到 http://localhost:5678（开发时跨域代理）
4. 创建目录结构：

   src/
   ├── api/              axios 请求封装
   │   ├── index.js      基础配置（baseURL、拦截器、token 注入）
   │   ├── auth.js       登录接口
   │   ├── submissions.js
   │   ├── reviews.js
   │   ├── assignments.js
   │   ├── editors.js
   │   ├── authors.js
   │   ├── dashboard.js
   │   ├── email.js
   │   └── upload.js
   ├── stores/           Pinia 状态
   │   ├── user.js       当前用户信息、token
   │   └── app.js        全局状态
   ├── router/           路由配置
   │   └── index.js
   ├── views/            页面组件
   │   ├── Login.vue
   │   ├── Dashboard.vue
   │   ├── Intake.vue
   │   ├── SubmissionList.vue
   │   ├── SubmissionDetail.vue
   │   ├── SubmissionForm.vue
   │   ├── ReviewRoundManage.vue
   │   ├── AssignmentList.vue
   │   ├── AssignmentForm.vue
   │   ├── AuthorList.vue
   │   ├── EditorList.vue
   │   ├── EditorDashboard.vue
   │   ├── EditorReview.vue
   │   └── EmailInbox.vue
   ├── layouts/          布局组件
   │   └── MainLayout.vue  侧边导航 + 顶栏 + 内容区
   ├── components/       公用组件
   │   ├── StatusTag.vue
   │   ├── FileUploader.vue
   │   └── ScoringForm.vue
   ├── utils/            工具函数
   │   └── constants.js  状态映射、学科列表等常量
   ├── App.vue
   └── main.js
```

### Prompt 2.2 — 配置路由和布局

```
实现 src/router/index.js：

路由表：
  /login                Login.vue（无需登录）
  /                     Dashboard.vue
  /intake               Intake.vue
  /submissions          SubmissionList.vue
  /submissions/add      SubmissionForm.vue
  /submissions/:id      SubmissionDetail.vue
  /submissions/:id/edit SubmissionForm.vue
  /reviews/:round       ReviewRoundManage.vue
  /assignments          AssignmentList.vue
  /assignments/add      AssignmentForm.vue
  /authors              AuthorList.vue
  /editors              EditorList.vue
  /editor               EditorDashboard.vue（编辑角色）
  /editor/review/:id    EditorReview.vue
  /email/inbox          EmailInbox.vue

要求：
- 路由守卫：未登录跳 /login，token 过期清空并跳转
- MainLayout.vue 作为除 Login 外所有页面的外层布局
- MainLayout.vue 左侧导航结构参考 系统管理与导航重构方案.md 中的定义：
  收稿管理 → intake、email/inbox
  审稿管理 → dashboard、reviews/:round、assignments
  资源管理 → authors、editors
  编辑专区 → editor、editor/review/:id
```

### Prompt 2.3 — 封装 Axios 和 API 层

```
实现 src/api/index.js：

- 创建 axios 实例，baseURL 为 /api
- 请求拦截器：自动在 header 中加 Authorization: Bearer <token>
- 响应拦截器：
  - code === 0 时直接返回 data
  - code === 401 时清空 token 跳转登录
  - 其他错误用 ElMessage.error 弹提示
- 封装 get/post/put/delete 方法

然后分别实现各 api 文件，例如 src/api/auth.js：

  export function login(username, password) { return post('/auth/login', { username, password }) }
  export function getMe() { return get('/auth/me') }
  export function changePassword(data) { return post('/auth/change-password', data) }

按照 Phase 1 中每个 API 模块的接口定义，逐一在对应的 api 文件中封装调用函数。
```

---

## Phase 3: 前端页面实现

### Prompt 3.1 — 实现登录页

```
实现 views/Login.vue：

- 居中卡片布局，Element Plus el-card
- 表单：用户名 + 密码，el-form + el-input
- 登录按钮调用 api/auth.js 的 login()
- 成功后存 token 到 localStorage + Pinia store，跳转 /
- 失败显示错误信息
- 背景色浅灰，卡片带阴影
```

### Prompt 3.2 — 实现主布局

```
实现 layouts/MainLayout.vue：

- 左侧 el-menu 垂直导航，router 模式（:router="true"）
- 顶栏显示当前用户名 + 退出按钮
- 右侧内容区 <router-view />
- 菜单结构（参考 系统管理与导航重构方案.md）：

  收稿管理
    └ 邮件收稿    /intake
    └ 邮件收件箱  /email/inbox
  审稿管理
    └ 工作台      /
    └ 一审管理    /reviews/一审
    └ 二审管理    /reviews/二审
    └ 三审管理    /reviews/三审
    └ 派稿记录    /assignments
  资源管理
    └ 作者管理    /authors
    └ 编辑管理    /editors
  编辑专区（仅编辑角色可见）
    └ 我的审稿    /editor
```

### Prompt 3.3 — 实现工作台

```
实现 views/Dashboard.vue：

- 顶部统计卡片行（el-row + el-col，4个卡片）：
  - 总投稿数
  - 待处理数
  - 审稿中
  - 已录用
- 下半部分：
  - 左侧：按状态分布的表格或图表
  - 右侧：最近操作记录时间线（el-timeline）
- 数据从 GET /api/dashboard/stats 获取
```

### Prompt 3.4 — 实现投稿列表和详情

```
实现 views/SubmissionList.vue：

- 顶部搜索栏：关键词输入框 + 状态下拉 + 学科下拉 + 搜索按钮
- el-table 展示投稿列表，列：ID、标题、作者、学科、状态、收稿日期、操作
- 分页组件 el-pagination
- 点击行或"详情"按钮跳转 SubmissionDetail

实现 views/SubmissionDetail.vue：

- 顶部：投稿基本信息卡片（标题、作者、学科、状态、日期、附件下载）
- 中部：审稿轮次 tabs（一审/二审/三审），每轮显示：
  - 派稿列表（编辑姓名、状态、评分、审稿意见、推荐决定）
  - 主编决定按钮组（通过/返修/退稿）
- 底部：操作日志 el-timeline
- 右侧操作区：编辑投稿、匿名化、状态变更、删除

数据从 GET /api/submissions/:id 获取
```

### Prompt 3.5 — 实现投稿表单

```
实现 views/SubmissionForm.vue：

- el-form，字段：
  - 标题（el-input）
  - 作者（el-select，支持搜索，从 /api/authors 获取列表）
  - 学科（el-select，来自 utils/constants.js 中的 FIELDS）
  - 状态（el-select）
  - 期号（el-input）
  - 收稿日期（el-date-picker）
  - 备注（el-input type=textarea）
  - 附件上传（components/FileUploader.vue）
- 提交按钮调用 POST /api/submissions 或 PUT /api/submissions/:id
- 成功跳转回列表

如果是编辑模式（有 :id），页面加载时从 API 获取现有数据填充表单。
```

### Prompt 3.6 — 实现审稿轮次管理

```
实现 views/ReviewRoundManage.vue：

- 路由参数 round 决定展示哪个轮次（一审/二审/三审）
- el-table 展示该轮次下的所有投稿，列：
  - 稿件ID、标题、作者、学科、派稿数、审稿进度、主编决定、操作
- 每行操作：查看详情、派稿、主编决定
- 数据从 GET /api/reviews/round/:round 获取（需要后端实现对应接口）
```

### Prompt 3.7 — 实现派稿管理

```
实现 views/AssignmentList.vue：

- el-table，列：稿件ID、稿件标题、审稿轮次、编辑、状态、派稿日期、截止日期、操作
- 筛选：按轮次、状态、编辑
- 新建派稿按钮打开 AssignmentForm 弹窗

实现 views/AssignmentForm.vue（弹窗组件）：

- el-dialog 弹窗
- 表单：选择投稿、选择编辑、选择轮次、截止日期
- 提交 POST /api/assignments
```

### Prompt 3.8 — 实现编辑审稿页面

```
实现 views/EditorDashboard.vue：

- el-table 显示当前登录编辑的所有派稿，列：稿件标题、轮次、状态、派稿日期、截止日期
- 点击进入审稿

实现 views/EditorReview.vue：

- 上半部分：稿件信息（标题、摘要、匿名附件下载）
- 下半部分：评分表单
  - 选题价值（el-input-number, 1-10）
  - 论证质量（el-input-number, 1-10）
  - 创新性（el-input-number, 1-10）
  - 规范性（el-input-number, 1-10）
  - 总分（自动计算）
  - 审稿意见（el-input type=textarea）
  - 批注文件上传（components/FileUploader.vue）
  - 推荐决定（el-select：建议录用/建议返修/建议退稿）
- 提交按钮调用 PUT /api/assignments/:id
- 撤回按钮调用 PUT /api/assignments/:id/retract
```

### Prompt 3.9 — 实现作者和编辑管理

```
实现 views/AuthorList.vue：

- 搜索框 + el-table（姓名、邮箱、投稿数、操作）
- 新增/编辑弹窗（el-dialog + el-form）
- 删除确认 el-message-box

实现 views/EditorList.vue：

- el-table（姓名、邮箱、角色、状态、最后登录、操作）
- 新增/编辑弹窗（含角色选择、学科方向）
- 启用/停用开关
- 重置密码按钮
```

### Prompt 3.10 — 实现邮件收稿

```
实现 views/EmailInbox.vue：

- 顶部：手动抓取按钮（调用 POST /api/email/fetch），显示上次同步时间
- el-table：邮件列表，列：发件人、标题、投稿标题、学科、状态、日期、操作
- 操作按钮：导入为投稿、确认、忽略、恢复
- 点击导入打开确认弹窗，确认后调用 POST /api/email/import/:id
```

---

## Phase 4: 联调与收尾

### Prompt 4.1 — 联调测试

```
完成前后端联调：

1. 确保后端 app_api.py 能独立启动（不与 webapp.py 冲突）
2. 确保前端 npm run dev 能启动且代理工作正常
3. 逐页测试：
   - 登录/登出
   - 投稿列表翻页、筛选、搜索
   - 投稿新增、编辑、删除
   - 派稿、审稿、主编决定
   - 作者/编辑增删改
   - 邮件收稿流程
   - 文件上传下载
4. 修复联调中发现的字段名不匹配、数据结构不一致等问题
```

### Prompt 4.2 — 生产部署适配

```
修改 启动网页.command 脚本，使其同时启动前后端：

1. 后端：python3 app_api.py（新 API 入口，默认端口 5678）
2. 前端：cd frontend && npm run build（构建为静态文件）
3. 修改 app_api.py，在生产模式下托管前端静态文件：
   - 如果 frontend/dist/ 存在，Flask 直接 serve 静态文件
   - 开发模式下代理到 Vite dev server
4. 更新 启动网页.command 脚本
```

---

## 执行顺序

按 Phase 1 → Phase 2 → Phase 3 → Phase 4 顺序执行。
Phase 1 必须最先完成（前端依赖 API）。
Phase 3 的各页面可以并行开发。
