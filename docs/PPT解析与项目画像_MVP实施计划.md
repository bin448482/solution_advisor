# PPT解析与项目画像系统 - MVP实施计划

## 项目概述

实现一个自动化流水线，将项目介绍类PPT转换为结构化的项目画像：
- **输入**：PPTX文件（如 `ppts/ChatBI产品介绍_2025.pptx`）
- **输出**：逐页图片 + 单页总结 + 项目画像（JSON格式）
- **目标**：可追溯、可批处理、可运营

## 技术选型

- **语言**：Python 3.9+
- **PPT渲染**：LibreOffice headless (PPTX → PDF → PNG)
- **文本提取**：python-pptx
- **LLM框架**：LangChain（支持多种LLM提供商：OpenAI、Claude、本地模型等）
- **数据验证**：Pydantic 2.0+
- **CLI框架**：Click

## 核心依赖

```
python-pptx>=0.6.21
Pillow>=10.0.0
langchain>=0.1.0
langchain-openai>=0.0.5
langchain-anthropic>=0.1.0
pydantic>=2.0.0
click>=8.1.0
python-dotenv>=1.0.0
```

## 系统架构

```
PPTX输入
  ↓
[Renderer] → slides/001.png, 002.png, ...
  ↓
[Extractor] → 提取标题、文本、备注
  ↓
[PageSummarizer] → page_summaries/001.json (并行处理)
  ↓
[ProfileGenerator] → doc_summary/project_profile.json
  ↓
[Pipeline] → manifest.json (元数据+错误)
```

## 目录结构

```
src/
├── __init__.py
├── __main__.py                 # CLI入口
├── config.py                   # 配置管理
├── models.py                   # Pydantic数据模型
├── renderer/
│   ├── __init__.py
│   ├── base.py                 # 抽象渲染器接口
│   └── libreoffice.py          # LibreOffice实现
├── extractor/
│   ├── __init__.py
│   └── ppt_extractor.py        # PPT文本提取
├── summarizer/
│   ├── __init__.py
│   ├── llm_client.py           # LLM API封装
│   ├── page_summarizer.py      # 单页总结
│   └── profile_generator.py    # 项目画像生成
├── pipeline.py                 # 主流程编排
└── utils.py                    # 工具函数

tests/
├── conftest.py
├── test_models.py
├── test_renderer.py
├── test_extractor.py
└── test_pipeline_e2e.py
```

## 核心组件设计

### 1. 数据模型 (src/models.py)

**SlideText**：单页文本提取结果
- slide_no, title, text_content, notes

**PageSummary**：单页总结
- slide_no, title, one_liner, bullets, details, entities, signals, evidence, confidence

**ProjectProfile**：项目画像
- project_name, positioning, target_users, core_value, core_capabilities, architecture, deployment, integrations, differentiators, cases, risks_and_limits, open_questions, evidence_map

**Manifest**：运行元数据
- input_file, file_hash, timestamp, page_count, errors, duration

### 2. 渲染器 (src/renderer/)

**LibreOffice实现**：
1. 调用 `soffice --headless --convert-to pdf` 转换PPTX为PDF
2. 使用 `pdftoppm` 将PDF转为PNG图片序列
3. 生成固定宽度命名：001.png, 002.png, ...
4. 返回图片路径列表

### 3. 文本提取器 (src/extractor/)

使用python-pptx读取：
- 每页标题（slide.shapes.title）
- 文本框内容（遍历text_frame）
- 备注/讲稿（slide.notes_slide）

### 4. 单页总结器 (src/summarizer/page_summarizer.py)

**输入**：slide图片 + 提取的文本
**处理**：通过LangChain调用多模态LLM（支持OpenAI GPT-4V、Claude等）
**Prompt设计**：
- 中文指令
- 明确输出JSON schema
- 包含示例
- 要求标注置信度

**输出**：PageSummary JSON

**LangChain集成**：
- 使用 `ChatOpenAI` 或 `ChatAnthropic` 等LangChain模型类
- 支持通过配置切换不同LLM提供商
- 利用LangChain的重试和错误处理机制

### 5. 项目画像生成器 (src/summarizer/profile_generator.py)

**输入**：所有PageSummary列表
**处理**：调用LLM聚合分析
**Prompt设计**：
- 从全量总结中提取项目画像
- 每个字段标注证据页码
- 识别未覆盖的关键问题

**输出**：ProjectProfile JSON

### 6. 流程编排 (src/pipeline.py)

**PPTPipeline类**：
```python
def run(pptx_path, output_dir, force_rerun=False):
    # 1. 检查manifest（幂等性）
    # 2. 渲染slides
    # 3. 提取文本
    # 4. 并行生成单页总结
    # 5. 生成项目画像
    # 6. 写入manifest
```

**错误处理**：
- 关键错误（缺少依赖、配置）→ 立即失败
- 单页错误 → 继续处理，记录到manifest
- LLM API错误 → 利用LangChain内置重试机制（指数退避）

### 7. CLI入口 (src/__main__.py)

```bash
python -m src --input <pptx> --output <dir> [--force] [--verbose]
```

**输出**：
- 进度指示
- 统计信息（页数、成功/失败、耗时）
- manifest.json路径

## 配置管理

**.env文件**：
```
# LLM配置（LangChain）
LLM_PROVIDER=openai              # 可选：openai, anthropic, local
LLM_API_KEY=sk-...               # API密钥
LLM_BASE_URL=https://api.openai.com/v1  # 可选：自定义API端点
LLM_MODEL=gpt-4-vision-preview   # 模型名称
LLM_TEMPERATURE=0.1              # 温度参数

# 渲染配置
RENDER_DPI=150
MAX_WORKERS=3
LIBREOFFICE_PATH=/usr/bin/soffice
```

**LangChain模型配置示例**：
- OpenAI: `LLM_PROVIDER=openai`, `LLM_MODEL=gpt-4-vision-preview`
- Claude: `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-3-opus-20240229`
- 本地模型: `LLM_PROVIDER=local`, `LLM_BASE_URL=http://localhost:8000`

**优先级**：CLI参数 > 环境变量 > 默认值

## 实施步骤（8天计划）

### Day 1: 项目基础
- [ ] 创建目录结构
- [ ] 编写 `requirements.txt`
- [ ] 实现 `src/models.py`（所有Pydantic模型）
- [ ] 实现 `src/config.py`（配置加载）
- [ ] 实现 `src/utils.py`（文件hash、路径处理）

### Day 2: 渲染模块
- [ ] 实现 `src/renderer/base.py`（抽象接口）
- [ ] 实现 `src/renderer/libreoffice.py`
- [ ] 测试：ChatBI产品介绍_2025.pptx → slides/*.png
- [ ] 验证：图片数量、命名、质量

### Day 3: 文本提取
- [ ] 实现 `src/extractor/ppt_extractor.py`
- [ ] 测试：提取标题、文本、备注
- [ ] 验证：结构化输出正确性

### Day 4: LLM客户端
- [ ] 实现 `src/summarizer/llm_client.py`（基于LangChain）
- [ ] 支持多种LLM提供商（OpenAI、Claude等）
- [ ] 配置LangChain模型初始化和切换逻辑
- [ ] 测试：简单图片+文本prompt（验证多模态能力）

### Day 5: 单页总结
- [ ] 实现 `src/summarizer/page_summarizer.py`
- [ ] 设计中文prompt（结构化输出）
- [ ] 测试：2-3张样例slides
- [ ] 迭代优化prompt质量

### Day 6: 项目画像
- [ ] 实现 `src/summarizer/profile_generator.py`
- [ ] 设计聚合prompt
- [ ] 测试：完整page summaries → profile
- [ ] 验证：evidence_map正确性

### Day 7: 流程编排
- [ ] 实现 `src/pipeline.py`（主编排逻辑）
- [ ] 实现 `src/__main__.py`（CLI）
- [ ] 添加manifest.json生成
- [ ] 端到端测试

### Day 8: 测试与文档
- [ ] 编写 `tests/test_pipeline_e2e.py`
- [ ] 创建 `.env.example`
- [ ] 编写 `README.md`（安装、使用说明）
- [ ] 完整验收测试

## 关键文件清单

**必须创建的核心文件**：

1. **src/models.py** - 数据模型定义（数据契约）
2. **src/pipeline.py** - 主流程编排（系统核心）
3. **src/summarizer/page_summarizer.py** - 单页总结（核心智能）
4. **src/renderer/libreoffice.py** - 渲染实现（基础能力）
5. **src/__main__.py** - CLI入口（用户界面）

**支持文件**：
- requirements.txt - 依赖管理
- .env.example - 配置模板
- README.md - 使用文档

## 验收标准

**MVP完成标准**：
1. ✅ 输入ChatBI产品介绍_2025.pptx，输出完整目录结构
2. ✅ slides/目录包含所有页面PNG图片（命名正确）
3. ✅ page_summaries/目录包含所有单页JSON（字段完整）
4. ✅ doc_summary/project_profile.json生成（包含evidence_map）
5. ✅ manifest.json记录元数据（页数、hash、耗时、错误）
6. ✅ 单页失败不影响整体流程（错误记录在manifest）
7. ✅ 二次运行跳过已完成步骤（幂等性）

## 风险与对策

**风险1：LibreOffice依赖**
- 对策：提供详细安装文档（Windows/Mac/Linux）
- 备选：手动PDF转换说明

**风险2：LLM API成本**
- 对策：限制并发数（MAX_WORKERS=3）
- 对策：基于manifest缓存结果

**风险3：中文质量**
- 对策：使用GPT-4 Vision（多语言支持最佳）
- 对策：prompt中明确中文指令

**风险4：错误恢复**
- 对策：单页失败继续处理
- 对策：manifest详细记录错误
- 对策：支持部分重跑（V1增强）

## 下一步行动

1. 确认LibreOffice安装（Windows环境）
2. 获取LLM API密钥（OpenAI、Claude或其他兼容服务）
3. 配置LangChain环境和模型提供商
4. 开始Day 1实施：创建项目结构和基础模型
