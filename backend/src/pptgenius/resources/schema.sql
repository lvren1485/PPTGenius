-- PPTGenius Database Schema v0.2.0 (MySQL)
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
    current_outline_id INT,
    workspace_path VARCHAR(512) NOT NULL DEFAULT '',
    estimated_cost DOUBLE DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (current_outline_id) REFERENCES outlines(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    conversation_id INT NOT NULL,
    idx INT NOT NULL DEFAULT 0,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    content_type VARCHAR(32) DEFAULT 'text',
    estimated_cost DOUBLE,
    token_cost_json JSON,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== 大纲 ====================

CREATE TABLE IF NOT EXISTS outlines (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    title VARCHAR(256) NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    eval_score DOUBLE,
    eval_detail JSON,
    version INT NOT NULL DEFAULT 0,
    explore_result_json JSON,
    slide_count INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outline_sections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    outline_id INT NOT NULL,
    section_index INT NOT NULL,
    title VARCHAR(256) NOT NULL,
    description TEXT,
    slide_count INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (outline_id) REFERENCES outlines(id) ON DELETE CASCADE,
    UNIQUE KEY uk_outline_section (outline_id, section_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outline_slides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    outline_id INT NOT NULL,
    section_id INT,
    slide_index INT NOT NULL,
    title VARCHAR(256) NOT NULL,
    content_json JSON,
    layout_type VARCHAR(32) DEFAULT 'content',
    has_image TINYINT(1) DEFAULT 0,
    has_chart TINYINT(1) DEFAULT 0,
    notes TEXT,
    citations JSON,
    status VARCHAR(32) DEFAULT 'new',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (outline_id) REFERENCES outlines(id),
    FOREIGN KEY (section_id) REFERENCES outline_sections(id) ON DELETE SET NULL,
    UNIQUE KEY uk_outline_slide (outline_id, slide_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outline_snapshots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    outline_id INT NOT NULL,
    user_id INT NOT NULL,
    conversation_id INT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    outline_json JSON NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (outline_id) REFERENCES outlines(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ==================== 样式表 ====================

CREATE TABLE IF NOT EXISTS styles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE COMMENT '样式标识',
    label VARCHAR(100) NOT NULL COMMENT '显示名',
    colors_json JSON NOT NULL COMMENT '{primary, accent, text, bg, ...}',
    chart_colors_json JSON NOT NULL COMMENT '图表配色序列',
    fonts_json JSON NOT NULL COMMENT '{title, subtitle, body, caption}',
    style_density VARCHAR(16) DEFAULT 'moderate' COMMENT 'minimal|moderate|elaborate',
    decoration_json JSON COMMENT '装饰开关 {title_accent_bar, section_divider_line, ...}',
    background_json JSON COMMENT '背景设置 {color, gradient, image}',
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
    style_id INT COMMENT 'FK → styles.id',
    file_path VARCHAR(512) NOT NULL DEFAULT '',
    file_size INT,
    slide_count INT DEFAULT 0,
    version INT NOT NULL DEFAULT 0,
    outline_version INT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    error_msg TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (outline_id) REFERENCES outlines(id),
    FOREIGN KEY (style_id) REFERENCES styles(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS presentation_slides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    presentation_id INT NOT NULL,
    outline_slide_id INT COMMENT 'FK → outline_slides.id',
    slide_index INT NOT NULL,
    style_id INT COMMENT '本页样式覆盖',
    layout_name VARCHAR(50) NOT NULL,
    agent_outputs JSON COMMENT '{elements: [...], notes: "", background: {}}',
    chart_data JSON COMMENT '纯图表数据',
    table_data JSON COMMENT '纯表格数据',
    image_paths JSON COMMENT '图片路径列表',
    status VARCHAR(20) DEFAULT 'new',
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (presentation_id) REFERENCES presentations(id) ON DELETE CASCADE,
    FOREIGN KEY (outline_slide_id) REFERENCES outline_slides(id) ON DELETE SET NULL,
    FOREIGN KEY (style_id) REFERENCES styles(id) ON DELETE SET NULL
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
    conversation_id INT,
    filename VARCHAR(256) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(16) NOT NULL,
    file_size INT,
    chunk_count INT DEFAULT 0,
    source_type VARCHAR(16) DEFAULT 'upload',
    web_url VARCHAR(2048),
    summary_json JSON COMMENT 'LLM 生成的摘要缓存',
    status VARCHAR(32) DEFAULT 'indexed',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
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

-- ==================== 索引 ====================
CREATE INDEX idx_conv_user ON conversations(user_id);
CREATE INDEX idx_conv_current_outline ON conversations(current_outline_id);
CREATE INDEX idx_msg_conv_idx ON messages(conversation_id, idx);
CREATE INDEX idx_out_conv ON outlines(conversation_id);
CREATE INDEX idx_out_user ON outlines(user_id);
CREATE INDEX idx_osec_outline ON outline_sections(outline_id, section_index);
CREATE INDEX idx_oslide_outline ON outline_slides(outline_id, slide_index);
CREATE INDEX idx_oslide_section ON outline_slides(section_id);
CREATE INDEX idx_osnap_outline ON outline_snapshots(outline_id, version DESC);
CREATE INDEX idx_style_name ON styles(name);
CREATE INDEX idx_pres_conv ON presentations(conversation_id);
CREATE INDEX idx_pres_user ON presentations(user_id);
CREATE INDEX idx_pres_outline ON presentations(outline_id);
CREATE INDEX idx_pslide_pres ON presentation_slides(presentation_id, slide_index);
CREATE INDEX idx_pslide_status ON presentation_slides(status);
CREATE INDEX idx_pslide_outline ON presentation_slides(outline_slide_id);
CREATE INDEX idx_snap_pres ON presentation_snapshots(presentation_id, version DESC);
CREATE INDEX idx_know_user ON knowledge_files(user_id);
CREATE INDEX idx_know_conv ON knowledge_files(conversation_id);
CREATE INDEX idx_kchunk_file ON knowledge_chunks(file_id, chunk_index);

SET FOREIGN_KEY_CHECKS = 1;
