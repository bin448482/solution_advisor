# Solution Advisor · PPT解析与项目画像流水线

将项目介绍类 PPT 自动转换为结构化画像与 RAG 知识库，支持端到端渲染、抽取、总结与问答。

> 项目类型：AI / Tool / CLI  
> 主要语言：Python 3.9+  
> 技术栈：LibreOffice、Poppler、Chroma、LLM（可 mock）、FastAPI/CLI（内部）  
> 目标用户：Developers / Internal Teams

---

## 徽章（可选）
![License](https://img.shields.io/badge/license-Private-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## 目录
- [功能特性](#功能特性)
- [架构 / 设计概览](#架构--设计概览)
- [前置条件](#前置条件)
- [安装](#安装)
- [配置](#配置)
- [使用示例](#使用示例)
- [项目结构](#项目结构)
- [开发指南](#开发指南)
- [测试](#测试)
- [部署（如适用）](#部署如适用)
- [路线图（可选）](#路线图可选)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [维护者 / 联系方式](#维护者--联系方式)

---

## 功能特性
- 一键处理 PPT：渲染 → 文本提取 → 单页总结 → 项目画像 → manifest
- 针对内部项目画像的 RAG 知识库生成与检索
- 可切换 LLM 提供商，支持 `LLM_PROVIDER=mock` 离线调试
- 与 LibreOffice / Poppler 集成的可移植渲染链路
- CLI 入口便于批处理，QA CLI 支持带护栏的问答

---

## 架构 / 设计概览
- 核心组件：`renderer/libreoffice.py`（渲染）、`extractor/ppt_extractor.py`（文本抽取）、`summarizer/`（LLM 总结）、`rag.py` & `pipeline.py`（编排与 RAG 文档生成）
- 接口层：`python -m src` CLI；`src/scripts/qa_cli.py` 提供问答接口
- 数据与存储：本地文件系统 + `chroma_db/` 向量库
- 扩展点：LLM 客户端、召回与重排参数、pipeline 配置、输出 manifest

详见 `docs/` 下的实施方案与设计文档。

---

## 前置条件
- Python 3.9+
- LibreOffice（提供 `soffice` 可执行）
- Poppler（提供 `pdftoppm`）
- 可选：真实 LLM Key（无则使用 `LLM_PROVIDER=mock`）

---

## 安装
```bash
# 克隆仓库
git clone https://github.com/your-org/solution_advisor.git
cd solution_advisor

# 安装依赖（示例）
pip install -r requirements.txt
```

安装 LibreOffice / Poppler（PPT 渲染必需）：
- Windows：安装 LibreOffice，确保 `soffice.exe` 在 PATH；安装 Poppler for Windows，将 `pdftoppm.exe` 所在目录加入 PATH。
- macOS：`brew install --cask libreoffice`，`brew install poppler`
- Linux：`apt/yum install libreoffice`，`apt/yum install poppler-utils`
验证：
```bash
soffice --headless --version
pdftoppm -h | head -n 1
```
如未在 PATH，可在 `.env` 中设置绝对路径（详见“配置”）。

---

## 配置
- 复制示例环境：`.env.example -> .env`，填入 LLM 及路径配置
- 复制模板配置：`config/settings.example.yaml -> config/settings.yaml` 并按需调整
- 确保 `soffice` 与 `pdftoppm` 在 PATH，或在 `.env` 中指定绝对路径

---

## 使用示例
```bash
# 运行主流水线（覆盖输出目录需加 --force）
python -m src --input ppts/ChatBI产品介绍_2025.pptx --output ppt_outputs/ChatBI产品介绍_2025 --force

# 运行问答 CLI（示例）
python -m src.scripts.qa_cli -q "ChatBI的核心功能是什么" --config config/settings.yaml
```

输出示例：
- `slides/001.png`…：渲染图片
- `page_summaries/001.json`…：单页总结
- `doc_summary/project_profile.json`：聚合画像
- `manifest.json`：元数据与错误记录
- `ppt_outputs/<ppt>/embeddings/rag_documents.json`：RAG 文档

---

## 项目结构
```bash
.
├─docs/                     # 需求、设计、方案文档
├─ppts/                     # 输入 PPT 资产
├─ppt_outputs/              # 渲染与总结产物（构建输出）
├─src/                      # 核心代码（pipeline、渲染、抽取、summarizer、QA）
├─tests/                    # 单元与端到端测试
├─config/                   # 配置模板与默认设置
└─venv/                     # 本地虚拟环境（可选）
```

---

## 开发指南
- 代码风格：PEP8；建议使用 `black`/`isort`（未强制）
- 提交规范：简短中文描述，例如“更新渲染异常处理”
- 分支策略：`main` 常备，功能分支 `feature/*`

---

## 测试
```bash
pytest
```
> 若缺少 LibreOffice/Poppler 或未配置 LLM，相关测试会自动跳过；可设置 `LLM_PROVIDER=mock` 以离线运行。

---

## 部署（如适用）
- 部署目标：本地/自托管服务器
- 交付方式：Python CLI；可封装为容器镜像（自行添加 Dockerfile）
- 关键参数：`.env`、`config/settings.yaml` 中的路径与 LLM 配置

---

## 路线图（可选）
- [ ] 完善 Docker 化与一键安装脚本
- [ ] 增强多模型策略与重排参数自动调优
- [ ] 增加可视化 Web 界面与任务队列

---

## 贡献指南
- 提交 PR 前请确保通过全部测试并更新相关文档
- 如需讨论新功能/问题，请先提交 Issue 或在内部渠道同步
- 代码评审由核心维护者轮值

---

## 许可证
本项目当前为内部使用，许可证：Private（未公开）。如需外部分发请先与维护者确认。

---

## 维护者 / 联系方式
- Owner：Solution Advisor 团队（internal）
- 协作渠道：企业微信/邮件（请在内网通讯录查找）
