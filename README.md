# PPT-Genius

> 基于LLM与RAG的PPT大纲智能生成与内容深度补全系统

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Prototype-orange.svg)](STATUS)

## 📝 项目简介

在商业汇报、学术展示、教育培训等场景中，演示文稿是信息传达的核心载体。然而，制作一份结构清晰、内容详实、论据充分的PPT通常耗费大量时间与精力。

本系统旨在解决用户在PPT制作中面临的两大核心困境：

- **有主题但难以组织成逻辑自洽的演示大纲**
- **有大纲但缺乏充实、可靠的内容细节**

通过融合大语言模型（LLM）的结构化生成能力与检索增强生成（RAG）技术，实现从模糊主题或原始文档到高质量叙事大纲与知识增强内容的自动化生成。

## 🎯 项目目标

| 目标 | 描述 |
| ---- | ------------------------------------------------------------ |
| 1 | 设计并实现支持结构化叙事约束的PPT大纲生成Prompt工程与方法 |
| 2 | 构建基于RAG的外部知识检索与内容补全机制，提供可溯源、高可信的增强内容 |
| 3 | 实现从用户输入（主题/文档）到完整PPT大纲与内容输出的端到端原型系统 |
| 4 | 验证系统在结构合理性、内容准确性、知识增强效果等方面的性能与实用性 |

## ✅ 成功标准

- [ ] 系统能够从单一主题或文档输入中生成结构清晰、逻辑连贯的PPT大纲，**结构评分 ≥ 4.5/5**
- [ ] 80%以上的生成内容可通过外部知识溯源验证，**事实性错误率 < 5%**
- [ ] 用户测试中，**70%以上用户**认为系统显著提升PPT制作效率与内容质量
- [ ] 完成系统原型开发，并在**商业、教育、科研**三个领域完成验证
- [ ] 技术报告完成，代码与文档开源

## 🚀 快速开始

### 环境要求

- Python 3.9+
- pip / conda

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/smart-ppt-outline-generator.git
cd smart-ppt-outline-generator

# 安装依赖
pip install -r requirements.txt
```

### 基本使用

```python
from ppt_generator import PPTGenerator

# 初始化生成器
generator = PPTGenerator()

# 从主题生成PPT大纲
outline = generator.generate_outline(
    topic="人工智能在医疗领域的应用",
    num_slides=10
)

# 基于RAG进行内容补全
enhanced_ppt = generator.enhance_with_rag(outline)

# 导出PPT文件
enhanced_ppt.export("output.pptx")
```

## 📁 项目结构

```plaintext
.
├── README.md
├── requirements.txt
├── setup.py
├── src/
│   ├── __init__.py
│   ├── llm/           # LLM调用与Prompt工程
│   ├── rag/           # RAG检索与知识增强
│   ├── outline/       # 大纲结构化生成
│   └── export/        # PPT导出模块
├── tests/             # 单元测试
├── docs/              # 文档
└── examples/          # 使用示例
```

## 👥 团队成员

| 角色 | 姓名 | 学号 | 邮箱 |
| :--- | :------- | :------ | :-------------------- |
| 组长 | 潘越 | 2353788 | <2353788@tongji.edu.cn> |
| 成员 | 罗力 | 2353250 | <2353250@tongji.edu.cn> |
| 成员 | 上官思洋 | 2352647 | <2352647@tongji.edu.cn> |
| 成员 | 左凌旭 | 2351042 | <2351042@tongji.edu.cn> |

## 👨‍🏫 指导老师

- **杜博闻** 助理教授，同济大学 - <bowendu@tongji.edu.cn>

## 📄 License

本项目采用 MIT 许可证 - 详见 [LICENSE](https://license/) 文件

## 📧 联系方式

如有问题或建议，欢迎通过邮箱联系我们。
