-- PPTGenius Database Schema (MySQL)
SET FOREIGN_KEY_CHECKS = 0;

-- ==================== 用户与会话 ====================

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(64) NOT NULL DEFAULT 'default',
    password VARCHAR(256) NOT NULL DEFAULT '',
    other JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS conversations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(256) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    current_phase VARCHAR(32) DEFAULT 'chat',
    workspace_path VARCHAR(512) NOT NULL DEFAULT '',
    total_tokens INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    idx INT NOT NULL DEFAULT 0,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(32) DEFAULT 'text',
    token_count INT,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== 大纲 ====================

CREATE TABLE IF NOT EXISTS outlines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    title VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    eval_score DOUBLE,
    version INT NOT NULL DEFAULT 1,
    slide_count INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outline_slides (
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

-- ==================== 模板与配色 ====================

CREATE TABLE IF NOT EXISTS templates (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT '模板标识',
    label VARCHAR(100) NOT NULL COMMENT '显示名',
    category VARCHAR(50) COMMENT 'corporate|tech|education|creative|minimal',
    description VARCHAR(500),
    slide_width FLOAT NOT NULL DEFAULT 13.333,
    slide_height FLOAT NOT NULL DEFAULT 7.5,
    layouts_json JSON NOT NULL COMMENT '布局定义 [{name, label, placeholders}]',
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS color_schemes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT '方案标识',
    label VARCHAR(100) NOT NULL COMMENT '显示名',
    colors_json JSON NOT NULL COMMENT '{primary, accent, text, bg, ...}',
    chart_colors_json JSON NOT NULL COMMENT '图表配色序列',
    fonts_json JSON NOT NULL COMMENT '{title, subtitle, body, caption}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== PPT ====================

CREATE TABLE IF NOT EXISTS presentations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    outline_id INT,
    template_id INT COMMENT 'FK → templates.id',
    color_scheme_id INT COMMENT 'FK → color_schemes.id',
    file_path VARCHAR(512) NOT NULL DEFAULT '',
    file_size INT,
    slide_count INT DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    error_msg TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (outline_id) REFERENCES outlines(id),
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL,
    FOREIGN KEY (color_scheme_id) REFERENCES color_schemes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS presentation_slides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    presentation_id INT NOT NULL,
    outline_slide_id INT COMMENT 'FK → outline_slides.id',
    slide_index INT NOT NULL,
    template_id INT COMMENT '本页模板覆盖',
    color_scheme_id INT COMMENT '本页配色覆盖',
    layout_name VARCHAR(50) NOT NULL,
    agent_outputs JSON COMMENT '{"text": [...], "chart": {...}, "table": {...}, "image": {...}}',
    chart_data JSON COMMENT '纯图表数据',
    table_data JSON COMMENT '纯表格数据',
    image_paths JSON COMMENT '图片路径列表',
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (presentation_id) REFERENCES presentations(id) ON DELETE CASCADE,
    FOREIGN KEY (outline_slide_id) REFERENCES outline_slides(id) ON DELETE SET NULL,
    FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE SET NULL,
    FOREIGN KEY (color_scheme_id) REFERENCES color_schemes(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== PPT 快照 ====================

CREATE TABLE IF NOT EXISTS presentation_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    presentation_id INT NOT NULL,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    outline_json JSON NOT NULL,
    presentation_json JSON NOT NULL,
    version INT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (presentation_id) REFERENCES presentations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== 知识库 ====================

CREATE TABLE IF NOT EXISTS knowledge_files (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    filename VARCHAR(256) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size INT,
    chunk_count INT DEFAULT 0,
    source_type VARCHAR(16) DEFAULT 'upload',
    status VARCHAR(32) DEFAULT 'indexed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_id INT NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES knowledge_files(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS web_resources (
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

-- ==================== 索引 ====================
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_msg_conv_idx ON messages(conversation_id, idx);
CREATE INDEX IF NOT EXISTS idx_out_conv ON outlines(conversation_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_out_user ON outlines(user_id);
CREATE INDEX IF NOT EXISTS idx_pres_conv ON presentations(conversation_id);
CREATE INDEX IF NOT EXISTS idx_pres_user ON presentations(user_id);
CREATE INDEX IF NOT EXISTS idx_pslide_pres ON presentation_slides(presentation_id, slide_index);
CREATE INDEX IF NOT EXISTS idx_pslide_status ON presentation_slides(status);
CREATE INDEX IF NOT EXISTS idx_pslide_outline ON presentation_slides(outline_slide_id);
CREATE INDEX IF NOT EXISTS idx_template_cat ON templates(category);
CREATE INDEX IF NOT EXISTS idx_colorscheme_name ON color_schemes(name);
CREATE INDEX IF NOT EXISTS idx_snap_pres ON presentation_snapshots(presentation_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_know_user ON knowledge_files(user_id);
CREATE INDEX IF NOT EXISTS idx_kchunk_file ON knowledge_chunks(file_id, chunk_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_web_url ON web_resources(url);
CREATE INDEX IF NOT EXISTS idx_web_user ON web_resources(user_id);

SET FOREIGN_KEY_CHECKS = 1;
