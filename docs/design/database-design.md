# PPTGenius 数据库设计

> MySQL + asyncmy，SQLAlchemy async engine
> 日期：2026-06-03

---

## 一、ER 图

```
┌──────────┐
│  users   │ (预留多用户)
│──────────│
│ PK id    │
│   name   │
└────┬─────┘
     │ 1:N
     │
┌────▼────────────┐         ┌─────────────────┐
│  conversations  │ 1     N │    messages     │
│─────────────────│─────────│─────────────────│
│ PK id           │         │ PK id           │
│ FK user_id      │         │ FK conversation │
│    title        │         │    role         │
│    status       │         │    content      │
│    created_at   │         │    token_count  │
│    updated_at   │         │    created_at   │
└────────┬────────┘         └─────────────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌─────────────────┐
│    outlines     │ 1     N │  outline_slides │
│─────────────────│─────────│─────────────────│
│ PK id           │         │ PK id           │
│ FK conversation │         │ FK outline_id   │
│ FK user_id      │         │    slide_index  │
│    title        │         │    title        │
│    status       │         │    content_json │
│    eval_score   │         │    layout_type  │
│    feedback     │         │    has_image    │
│    version      │         │    has_chart    │
│    created_at   │         │    notes        │
│    updated_at   │         └─────────────────┘
└────────┬────────┘
         │
         │ 1:N
         │
┌────────▼────────┐         ┌──────────────────┐
│  presentations  │ 1     N │ presentation_slides│
│─────────────────│─────────│───────────────────│
│ PK id           │         │ PK id             │
│ FK conversation │         │ FK presentation   │
│ FK outline      │         │    slide_index    │
│ FK user_id      │         │    layout_type    │
│    file_path    │         │    text_content    │
│    file_size    │         │    image_paths     │
│    slide_count  │         │    chart_paths     │
│    status       │         │    color_scheme    │
│    created_at   │         │    created_at      │
└─────────────────┘         └──────────────────┘

┌─────────────────┐         ┌──────────────────┐
│ knowledge_files │ 1     N │ knowledge_chunks │
│─────────────────│─────────│──────────────────│
│ PK id           │         │ PK id            │
│ FK user_id      │         │ FK file_id       │
│    filename     │         │    chunk_index   │
│    file_path    │         │    chunk_text    │
│    file_type    │         │    token_count   │
│    file_size    │         │    created_at    │
│    chunk_count  │         └──────────────────┘
│    source_type  │
│    status       │
│    content_hash │
│    created_at   │
└─────────────────┘

┌──────────────────┐
│  web_resources   │
│──────────────────│
│ PK id            │
│ FK user_id       │
│    url           │
│    title         │
│    content_text  │
│    source_domain │
│    fetched_at    │
│    stored_path   │
└──────────────────┘
```

---

## 二、表结构

### 2.1 users

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `name` | VARCHAR(64) | NOT NULL, DEFAULT 'default' | 单人默认 default |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.2 conversations

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK→users.id, NOT NULL | |
| `title` | VARCHAR(256) | NOT NULL, DEFAULT '' | |
| `status` | VARCHAR(32) | NOT NULL, DEFAULT 'active' | active / completed / archived |
| `current_phase` | VARCHAR(32) | DEFAULT 'chat' | chat / outline / ppt |
| `workspace_path` | VARCHAR(512) | NOT NULL | |
| `total_tokens` | INT | DEFAULT 0 | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | |

### 2.3 messages

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `conversation_id` | INT | FK→conversations.id, NOT NULL | |
| `role` | VARCHAR(16) | NOT NULL | user / assistant / system |
| `content` | TEXT | NOT NULL | |
| `content_type` | VARCHAR(32) | DEFAULT 'text' | text / outline / ppt_result / error |
| `token_count` | INT | | |
| `metadata_json` | JSON | | 扩展字段 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.4 outlines

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK→users.id, NOT NULL | |
| `conversation_id` | INT | FK→conversations.id, NOT NULL | |
| `title` | VARCHAR(256) | NOT NULL | |
| `status` | VARCHAR(32) | NOT NULL, DEFAULT 'draft' | draft / review / approved / rejected |
| `eval_score` | DOUBLE | | Evaluator 评分 (0-1) |
| `eval_feedback` | TEXT | | |
| `user_feedback` | TEXT | | |
| `version` | INT | NOT NULL, DEFAULT 1 | |
| `slide_count` | INT | | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |
| `updated_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP | |

### 2.5 outline_slides

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `outline_id` | INT | FK→outlines.id, NOT NULL | |
| `slide_index` | INT | NOT NULL | |
| `title` | VARCHAR(256) | NOT NULL | |
| `content_json` | JSON | | |
| `layout_type` | VARCHAR(32) | DEFAULT 'content' | |
| `has_image` | TINYINT(1) | DEFAULT 0 | |
| `has_chart` | TINYINT(1) | DEFAULT 0 | |
| `notes` | TEXT | | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.6 presentations

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK→users.id, NOT NULL | |
| `conversation_id` | INT | FK→conversations.id, NOT NULL | |
| `outline_id` | INT | FK→outlines.id | |
| `file_path` | VARCHAR(512) | NOT NULL | |
| `file_size` | INT | | |
| `slide_count` | INT | | |
| `status` | VARCHAR(32) | NOT NULL, DEFAULT 'completed' | generating / completed / failed |
| `error_msg` | TEXT | | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.7 presentation_slides

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `presentation_id` | INT | FK→presentations.id, NOT NULL | |
| `slide_index` | INT | NOT NULL | |
| `layout_type` | VARCHAR(32) | NOT NULL | |
| `color_scheme` | JSON | | agent 动态生成的配色 |
| `text_content_json` | JSON | | |
| `image_paths` | TEXT | | |
| `chart_paths` | TEXT | | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.8 knowledge_files

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK→users.id, NOT NULL | |
| `filename` | VARCHAR(256) | NOT NULL | |
| `file_path` | VARCHAR(512) | NOT NULL | |
| `file_type` | VARCHAR(16) | NOT NULL | txt / pdf / docx / csv / xlsx |
| `file_size` | INT | | |
| `chunk_count` | INT | DEFAULT 0 | |
| `source_type` | VARCHAR(16) | DEFAULT 'upload' | upload / scrape |
| `status` | VARCHAR(32) | DEFAULT 'indexed' | pending / indexing / indexed / failed |
| `content_hash` | VARCHAR(64) | | SHA256 去重 |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.9 knowledge_chunks

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `file_id` | INT | FK→knowledge_files.id, NOT NULL | |
| `chunk_index` | INT | NOT NULL | |
| `chunk_text` | TEXT | NOT NULL | |
| `token_count` | INT | | |
| `created_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

### 2.10 web_resources

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INT | PK, AUTO_INCREMENT | |
| `user_id` | INT | FK→users.id, NOT NULL | |
| `url` | VARCHAR(1024) | NOT NULL | |
| `title` | VARCHAR(256) | | |
| `content_text` | TEXT | | |
| `source_domain` | VARCHAR(256) | | |
| `stored_path` | VARCHAR(512) | | |
| `fetched_at` | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP | |

---

## 三、完整 DDL (MySQL)

```sql
CREATE DATABASE IF NOT EXISTS pptgenius
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pptgenius;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL DEFAULT 'default',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(256) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    current_phase VARCHAR(32) DEFAULT 'chat',
    workspace_path VARCHAR(512) NOT NULL,
    total_tokens INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(32) DEFAULT 'text',
    token_count INT,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE outlines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    title VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    eval_score DOUBLE,
    eval_feedback TEXT,
    user_feedback TEXT,
    version INT NOT NULL DEFAULT 1,
    slide_count INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE outline_slides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    outline_id INT NOT NULL,
    slide_index INT NOT NULL,
    title VARCHAR(256) NOT NULL,
    content_json JSON,
    layout_type VARCHAR(32) DEFAULT 'content',
    has_image TINYINT(1) DEFAULT 0,
    has_chart TINYINT(1) DEFAULT 0,
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (outline_id) REFERENCES outlines(id),
    UNIQUE KEY uk_outline_slide (outline_id, slide_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE presentations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    outline_id INT,
    file_path VARCHAR(512) NOT NULL,
    file_size INT,
    slide_count INT,
    status VARCHAR(32) NOT NULL DEFAULT 'completed',
    error_msg TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (outline_id) REFERENCES outlines(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE presentation_slides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    presentation_id INT NOT NULL,
    slide_index INT NOT NULL,
    layout_type VARCHAR(32) NOT NULL,
    color_scheme JSON,
    text_content_json JSON,
    image_paths TEXT,
    chart_paths TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (presentation_id) REFERENCES presentations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE knowledge_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    filename VARCHAR(256) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size INT,
    chunk_count INT DEFAULT 0,
    source_type VARCHAR(16) DEFAULT 'upload',
    status VARCHAR(32) DEFAULT 'indexed',
    content_hash VARCHAR(64),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE knowledge_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES knowledge_files(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE web_resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    url VARCHAR(1024) NOT NULL,
    title VARCHAR(256),
    content_text TEXT,
    source_domain VARCHAR(256),
    stored_path VARCHAR(512),
    fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ========== 索引 ==========
CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_conv_status ON conversations(status);
CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at);
CREATE INDEX idx_out_conv ON outlines(conversation_id, version DESC);
CREATE INDEX idx_out_user ON outlines(user_id);
CREATE INDEX idx_pres_conv ON presentations(conversation_id);
CREATE INDEX idx_pres_user ON presentations(user_id);
CREATE INDEX idx_pslide_pres ON presentation_slides(presentation_id, slide_index);
CREATE UNIQUE INDEX idx_know_hash ON knowledge_files(content_hash);
CREATE INDEX idx_know_user ON knowledge_files(user_id);
CREATE INDEX idx_know_type ON knowledge_files(file_type);
CREATE INDEX idx_kchunk_file ON knowledge_chunks(file_id, chunk_index);
CREATE UNIQUE INDEX idx_web_url ON web_resources(url);
CREATE INDEX idx_web_user ON web_resources(user_id);
```
