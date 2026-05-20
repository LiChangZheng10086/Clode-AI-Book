# Clode AI Book — AI 小说生成系统

## 项目概述

一种基于七个 AI Agent 协作的全自动长篇小说生成系统。用户提供不完整的小说构思（基础设定、角色草图、风格偏好），AI Agent 依次完成世界观构建、角色设计、风格量化、大纲规划，然后逐章生成大纲、撰写内容、自动审核、去 AI 化润色，并通过四层记忆系统确保长篇小说的一致性。

**核心设计原则：**
- 每次仅一本小说处于活跃生成状态
- 关键决策点暂停，等待人工确认
- 章节生成后自动审核 → 不达标则修订（最多 3 轮）
- 所有文本自动经过去 AI 化润色
- 基于 BGE 本地嵌入 + pgvector 的向量检索记忆

## 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (React)                     │
│  Vite + TypeScript + Tailwind CSS + Zustand + WebSocket │
│                    http://localhost:5173                 │
└─────────────────────┬───────────────────────────────────┘
                      │ REST API + WebSocket
┌─────────────────────▼───────────────────────────────────┐
│                  Backend (FastAPI)                       │
│                 http://localhost:8000                    │
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  A1 世界观│ │  A2 风格  │ │  A3 角色  │ │  A4 大纲  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │  A5 章节  │ │  A6 写手  │ │  A7 审核  │   Polisher  │
│  │  大纲器  │ │          │ │          │   (去AI润色)  │
│  └──────────┘ └──────────┘ └──────────┘                │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              记忆系统 (4 层)                       │   │
│  │  全书摘要 → 卷摘要 → 最近章节 → 向量检索          │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  Hook 注册表 │  │  实体状态追踪 │  │  上下文检索器 │   │
│  └─────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   数据层                                  │
│  ┌──────────────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ PostgreSQL 16    │  │  Redis   │  │ BGE Embedding │  │
│  │ + pgvector       │  │ (Celery) │  │ (本地推理)    │  │
│  └──────────────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 技术栈

### 后端
| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | FastAPI 0.133+ | 异步 Web 框架 |
| LLM 编排 | LangChain 1.3+ / LangGraph 1.2+ | Agent 调用与状态机 |
| LLM 网关 | LiteLLM 1.84+ | 统一 LLM 接口 |
| 数据库 | PostgreSQL 16 + pgvector | 关系存储 + 向量相似搜索 |
| ORM | SQLAlchemy 2.0 (async) | 异步数据库操作 |
| 迁移 | Alembic 1.18+ | 数据库版本管理 |
| 嵌入模型 | BGE-large-zh-v1.5 (1024维) | 本地嵌入生成 |
| 嵌入框架 | sentence-transformers 5.5+ | 模型加载与推理 |
| 任务队列 | Celery 5.6+ / Redis 7 | 异步后台任务 |
| WebSocket | FastAPI WebSocket | 实时 Agent 状态推送 |

### 前端
| 类别 | 技术 | 说明 |
|------|------|------|
| 框架 | React 19 + TypeScript | SPA |
| 构建 | Vite 8 | 开发与打包 |
| 样式 | Tailwind CSS 4 | 暗色主题 |
| 状态管理 | Zustand | projectStore + agentStore |
| 实时通信 | WebSocket (原生) | 双向 Agent 状态流 |

## 目录结构

```
clode-ai-book/
├── backend/
│   ├── main.py                  # FastAPI 入口，路由注册，CORS，生命周期
│   ├── core/
│   │   ├── config.py            # Pydantic Settings：LLM/DB/Redis/嵌入配置
│   │   ├── database.py          # SQLAlchemy 异步引擎与会话工厂
│   │   ├── llm.py               # LLM 工厂：get_llm/get_planning_llm/get_reviewer_llm
│   │   └── embedding.py         # EmbeddingService 单例：BGE 模型懒加载
│   ├── models/
│   │   └── base.py              # 11 个 SQLAlchemy ORM 模型
│   ├── schemas/                 # Pydantic 请求/响应模型
│   │   ├── __init__.py          # NovelCreate/Update/Response
│   │   ├── character.py         # Character CRUD schema
│   │   ├── chapter.py           # Volume/Chapter CRUD schema
│   │   ├── hook.py              # Hook CRUD schema
│   │   └── setting.py           # WorldSetting/StyleProfile CRUD schema
│   ├── api/
│   │   ├── novels.py            # 小说 CRUD
│   │   ├── characters.py        # 角色 CRUD
│   │   ├── chapters.py          # 卷/章节 CRUD
│   │   ├── hooks.py             # 钩子 CRUD + 状态筛选
│   │   ├── settings.py          # 世界观/风格配置 CRUD
│   │   └── ws.py                # WebSocket：预处理 + 写作管道
│   ├── engine/                  # 7 个 AI Agent
│   │   ├── planner.py           # A1 世界观 / A2 风格 / A3 角色 / A4 大纲
│   │   ├── generator.py         # A5 章节大纲器 / A6 章节写手
│   │   ├── checker.py           # A7 章节审核器（8 维度评分）
│   │   ├── polisher.py          # 去 AI 化润色器（7 条规则）
│   │   └── summarizer.py        # 章节/卷/全书摘要生成
│   ├── workflow/
│   │   └── graph.py             # LangGraph 状态机（预处理 + 写作管道）
│   ├── memory/
│   │   ├── summary_store.py     # 摘要存储与上下文组装（4 层记忆）
│   │   ├── hook_registry.py     # 钩子生命周期管理
│   │   ├── entity_tracker.py    # 实体状态时间线追踪
│   │   └── retriever.py         # pgvector 向量相似检索
│   ├── migrations/              # Alembic 迁移文件
│   ├── requirements.txt         # Python 依赖
│   ├── Dockerfile               # 后端容器
│   ├── alembic.ini              # Alembic 配置
│   └── .env                     # 环境变量（API Key、数据库URL）
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 路由定义（8 个页面）
│   │   ├── main.tsx             # React 入口
│   │   ├── index.css            # Tailwind 暗色主题
│   │   ├── components/
│   │   │   └── ProjectLayout.tsx # 顶部导航 + 项目切换 + Tab 导航
│   │   ├── pages/
│   │   │   ├── ProjectList.tsx  # 首页：项目列表 + 创建
│   │   │   ├── Dashboard.tsx    # 项目仪表盘：进度卡片 + 快捷操作
│   │   │   ├── Preprocess.tsx   # 预处理页：WebSocket 驱动 Agent 管道
│   │   │   ├── Outline.tsx      # 大纲页：卷/章节结构展示
│   │   │   ├── Settings.tsx     # 设定页：世界观/角色/风格 Tab
│   │   │   ├── Write.tsx        # 写作页：大纲/内容/审核三 Tab + WebSocket
│   │   │   ├── Hooks.tsx        # 钩子看板：4 列 Kanban
│   │   │   └── ChapterEditor.tsx# 章节富文本编辑器（预留）
│   │   ├── stores/
│   │   │   ├── projectStore.ts  # Zustand：当前小说 + 小说列表
│   │   │   └── agentStore.ts    # Zustand：Agent 状态 + 决策点
│   │   └── lib/
│   │       ├── api.ts           # REST API 客户端
│   │       └── useWS.ts         # WebSocket 连接池 Hook
│   ├── vite.config.ts           # Vite 配置 + API 代理
│   └── package.json
│
└── docker-compose.yml           # PostgreSQL + Redis 容器编排
```

## 数据库结构

### 核心表（11 张）

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| `novels` | 小说主表 | title, genre, target_chapters, status |
| `volumes` | 卷 | novel_id, index, title, summary, status |
| `chapters` | 章节 | volume_id, index, title, outline(JSONB), content, status, version, review_round |
| `chapter_summaries` | 章节摘要 | chapter_id, summary_type(chapter/volume/book), content |
| `chapter_embeddings` | 向量嵌入 | chapter_id, chunk_index, content, embedding(Vector 1024) |
| `characters` | 角色 | novel_id, name, role, profile(JSONB), voice_config(JSONB), relationships(JSONB), arc(JSONB) |
| `entity_states` | 实体状态时间线 | novel_id, entity_type, entity_name, state_snapshots(JSONB[]) |
| `hooks` | 剧情钩子 | novel_id, hook_type, description, planted_chapter_index, target_chapter_range, priority, status |
| `style_profiles` | 风格配置 | novel_id (unique), reference_text, extracted_params(JSONB) |
| `world_settings` | 世界观设定 | novel_id (unique), world_type, settings(JSONB) |

### 小说状态流转

```
draft → preprocess → writing → completed → archived
```

### 章节状态流转

```
draft → outlining → writing → reviewing → done
```

## Agent 系统

### 预处理管道（A1 → A3 → A2 → cross_validate → A4）

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| **A1 世界观构建器** | 三阶段构建完整世界观 | 用户输入 | world_type, geography, power_system, factions, items, rules, history |
| **A3 角色设计师** | 三阶段设计角色系统 | 用户输入 + 世界观 | 主角/配角/反派/NPC 完整档案，含 voice_card, relationships, arc |
| **A2 风格分析师** | 量化写作风格参数 | 用户输入 + 世界观 + 角色 | narrative_pov, tense, tone, 句式/段落/对话指标, 禁用词 |
| **Cross Validate** | 交叉验证 A1/A2/A3 | 三个 Agent 输出 | 一致性检查（预留占位） |
| **A4 大纲规划器** | 生成卷/章/场景结构 | 所有预处理输出 | 卷结构 → 章大纲 → 场景节拍（含 hook 种植/回收点） |

### 写作管道（A5 → A6 → Polisher → A7 → 条件循环）

| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| **A5 章节大纲器** | 将章节级节拍展开为详细场景大纲 | 小说大纲节拍 + 上下文包 | 场景级大纲：目的/角色动机/场景/情绪曲线/关键节拍/信息揭示/钩子操作 |
| **A6 章节写手** | 根据大纲生成章节正文 | 场景大纲 + 上下文包 | 完整章节文本 |
| **Polisher** | 自动去 AI 化润色 | A6 生成的原始文本 | 润色后文本（不改变信息内容） |
| **A7 章节审核器** | 8 维度评分 → pass/revision_needed | 润色文本 + 大纲 + 全集设定 | 分值 + 问题列表（位置/问题/建议）+ 总体裁决 |

### A7 审核维度（8 项，每项 0-10 分）

1. **outline_compliance** — 大纲覆盖度（场景/节拍是否全部完成）
2. **worldbuilding_consistency** — 世界观一致性（设定规则是否被遵守）
3. **character_consistency** — 角色一致性（人格/声线/动机是否偏离）
4. **plot_logic** — 情节逻辑（因果链是否完整，是否有逻辑漏洞）
5. **hook_management** — 钩子管理（是否推进/回收了应该处理的钩子）
6. **style_adherence** — 风格符合度（句式、节奏、描写比例是否符合风格配置）
7. **ai_flavor** — AI 痕迹检测（"然而/因此/突然/就在这时"等高频词、重复句式、同质化对话）
8. **detail_quality** — 细节质量（感官描写、情感深度）

**通过标准：** 所有维度 ≥ 6 分，无 major 问题，minor 问题 < 3 个。

### 修订循环

```
A6 写 → A7 审 → 不通过 → A6 根据 A7 的问题报告修订 → A7 再审
                                              ↳ 最多 3 轮，3 轮后强制通过
```

### 去 AI 化润色（Polisher）— 7 条规则

1. 打破重复句式结构
2. 替换 AI 高频词（然而/因此/此外/总而言之/值得注意的是/突然/就在这时）
3. 变化句子长度（短句 3-8 字 / 中句 / 长句 30+ 字交替）
4. 增加感官细节（视觉/听觉/触觉/嗅觉/温度）
5. 区分不同角色的对话风格
6. 删除动作已表达含义的多余解释段
7. 增加留白（删除不必要的过渡和内心独白，让读者自行推断）
8. **严格禁止改变**：情节、角色行为/对话语义、关键信息、角色数量、章节结构

## 记忆系统（4 层架构）

```
第 1 层：全书摘要（~500-1000 字）       → 始终注入，提供全局弧线
第 2 层：当前卷摘要（~300-500 字）      → 当前卷注入，保持卷内连贯
第 3 层：最近 3-5 章摘要                → 即时连续性
第 4 层：向量检索（pgvector 余弦相似）  → 按需检索相关历史片段
```

### 上下文包（Context Package）组装

每章生成前，通过当前章节大纲生成搜索查询，从 pgvector 检索最相关历史片段：

```python
{
    "world_setting_chunks": [...],    # 前 3 条相关世界观片段
    "past_chapter_chunks": [...],     # 后续 2 条相关历史章节片段
    "book_summary": "...",            # 从 chapter_summaries 表查询
    "volume_summary": "...",          # 从 chapter_summaries 表查询
    "recent_chapters": [...]          # 从 chapter_summaries 表查询（最近 5 章）
}
```

### 摘要自动生成

每章完成后自动触发：
1. **章节摘要**：提取关键事件、实体状态变化、新钩子、已回收钩子
2. **卷摘要**：当前卷所有章节标记 done 后，自动生成卷摘要
3. **全书摘要**：有新卷摘要后，重新生成全书摘要

### 钩子生命周期

```
unresolved → in_progress → resolved
              ↳ 逾期检测：target_chapter_range[1] < current_chapter → 标记为 overdue
```

### 实体状态追踪

每个实体（角色/物品/阵营/地点）维护 `state_snapshots` 数组，每章记录一次状态快照：

```json
[
  {"chapter": 1, "state": {"status": "初入江湖", "note": "..."}},
  {"chapter": 5, "state": {"status": "功力初成", "note": "已习得基础功法"}}
]
```

## LangGraph 工作流

### 预处理状态机

```
parse_input → worldbuilding(A1) → character(A3) → style(A2)
                                                         ↓
                                                     cross_validate
                                                         ↓
                                                     outline(A4)
                                                         ↓
                                                        END
```

每个节点可产生：
- `complete` → 进入下一节点
- `asking` → 暂停，通过 WebSocket 向用户发送 `decision_point`，等待 `decide` 指令恢复

### 写作状态机

```
chapter_outline(A5) → chapter_write(A6) → [Polisher自动执行] → chapter_review(A7)
                         ↑                                                  ↓
                         └── revision_needed & review_round < 3 ────────────┘
                                                                            ↓
                                                                  pass or round >= 3
                                                                            ↓
                                                                  update_memory → END
```

## REST API

### 健康检查
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |

### 小说
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/novels/` | 列出所有小说 |
| POST | `/api/novels/` | 创建小说 |
| GET | `/api/novels/{id}` | 获取小说详情 |
| PATCH | `/api/novels/{id}` | 更新小说 |
| DELETE | `/api/novels/{id}` | 删除小说 |

### 角色
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/characters/?novel_id=...` | 列出角色 |
| POST | `/api/characters/` | 创建角色 |
| PATCH | `/api/characters/{id}` | 更新角色 |
| DELETE | `/api/characters/{id}` | 删除角色 |

### 章节/卷
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/chapters/volumes?novel_id=...` | 列出卷 |
| POST | `/api/chapters/volumes?novel_id=...` | 创建卷 |
| GET | `/api/chapters/?volume_id=...` | 列出章节 |
| POST | `/api/chapters/?volume_id=...` | 创建章节 |
| PATCH | `/api/chapters/{id}/outline` | 更新章节大纲 |
| PATCH | `/api/chapters/{id}/content` | 更新章节内容 |

### 钩子
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/hooks/?novel_id=...&status=...&priority=...` | 列出/筛选钩子 |
| POST | `/api/hooks/` | 创建钩子 |
| PATCH | `/api/hooks/{id}` | 更新钩子 |

### 设定
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings/world?novel_id=...` | 获取世界观 |
| PUT | `/api/settings/world?novel_id=...` | 更新世界观 |
| GET | `/api/settings/style?novel_id=...` | 获取风格配置 |
| PUT | `/api/settings/style?novel_id=...` | 更新风格配置 |

## WebSocket 协议

### 预处理管道：`ws://localhost:8000/api/ws/preprocess/{novel_id}`

**客户端 → 服务端：**
```json
{"action": "start", "user_input": "修真世界，主角拥有吞噬能力", "target_chapters": 150}
{"action": "decide", "answer": "用户对决策点的回答"}
```

**服务端 → 客户端：**
```json
{"event": "pipeline_start", "message": "..."}
{"event": "state_update", "agent": "worldbuilding", "status": "running"}
{"event": "state_update", "agent": "worldbuilding", "status": "complete", "output": {...}}
{"event": "decision_point", "agent": "character", "question": "...", "options": [...]}
{"event": "pipeline_complete", "output": {...}}
{"event": "error", "message": "..."}
```

### 写作管道：`ws://localhost:8000/api/ws/write/{novel_id}`

**客户端 → 服务端：**
```json
{"action": "start_outline", "chapter_id": "...", "chapter_index": 1, "novel_outline_beat": {...}, "context_package": {...}}
{"action": "start_write", "chapter_id": "...", "chapter_index": 1, "novel_outline_beat": {...}, "context_package": {...}}
{"action": "retry_outline", "chapter_id": "..."}
{"action": "confirm_manual", "chapter_id": "..."}
```

**服务端 → 客户端：**
```json
{"event": "agent_start", "agent": "A6"}
{"event": "agent_complete", "agent": "A6", "output": "..."}
{"event": "review_retry", "report": {...}}
{"event": "pipeline_complete", "output": {...}}
{"event": "pipeline_stuck", "report": {...}}
{"event": "error", "message": "..."}
```

## 前端页面

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | ProjectList | 项目列表 + 创建小说 |
| `/project/:id` | Dashboard | 进度一览 + 快捷操作 |
| `/project/:id/preprocess` | Preprocess | WebSocket 驱动的预处理管道 |
| `/project/:id/outline` | Outline | 卷/章节大纲浏览 |
| `/project/:id/settings` | Settings | 世界观/角色/风格 Tab |
| `/project/:id/write` | Write | 写作主界面（大纲/内容/审核三 Tab） |
| `/project/:id/write/:ch` | Write | 指定章节写作 |
| `/project/:id/hooks` | Hooks | 钩子 Kanban（unresolved/in_progress/resolved/overdue） |

## 环境变量

```bash
# .env 文件（backend/.env）
LLM_API_KEY=sk-xxx                  # DeepSeek API Key
DATABASE_URL=postgresql+asyncpg://postgres:123456@localhost:5432/clode_ai_book
DATABASE_SYNC_URL=postgresql+psycopg2://postgres:123456@localhost:5432/clode_ai_book
REDIS_URL=redis://localhost:6379/0
DEBUG=true
```

## 启动指南

### 前提条件

- Docker Desktop（或 OrbStack）运行中，包含 PostgreSQL 16 和 Redis 7 容器
- Python 3.13+
- Node.js 20+
- DeepSeek API Key

### 1. 启动基础设施

```bash
# 确保 PostgreSQL 和 Redis 容器在运行
docker ps | grep pgsql    # PostgreSQL 16，端口 5432
docker ps | grep redis    # Redis 7，端口 6379
```

### 2. 后端

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 数据库迁移
alembic upgrade head

# 启动服务（端口 8000）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

首次运行时，BGE 嵌入模型会自动下载到本地（~1.3GB），之后缓存使用。

### 3. 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（端口 5173）
npm run dev
```

### 4. 验证

- 后端健康检查：`curl http://localhost:8000/api/health`
- 前端页面：`http://localhost:5173`
- 前端通过 Vite 代理访问后端 API：`http://localhost:5173/api/health`

### 使用流程

1. 在首页创建新小说
2. 进入预处理页面，输入小说构思 → 启动 Agent 管道
3. 遇到决策点时选择方案 → 管道继续
4. 预处理完成后查看大纲和设定
5. 进入写作页面，逐章生成（大纲 → 撰写 → 审核 → 修订循环）
6. 在钩子看板追踪伏笔生命周期
