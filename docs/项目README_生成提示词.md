# 项目 README 生成提示词

> 用途：生成/刷新 `README.md`。复制下方提示词，替换花括号中的占位内容后提交给 LLM 或写入 README。

---

# {PROJECT_NAME}

{ONE_LINE_DESCRIPTION}

> 项目类型：{Backend / Data Platform / AI / Library / Tool / Web App / CLI}  
> 主要语言：{LANGUAGES}  
> 技术栈：{TECH_STACK}  
> 目标用户：{Developers / Data Engineers / End Users / Internal Teams}

---

## AI 驱动快速上手（Claude / Codex）

> 适用：当项目是 **AI 驱动生成/沉淀工程**（例如：解析→总结→画像→RAG 资产生成），且实现细节分散在 `docs/`、`AGENTS.md`、`src/` 代码与配置中时，建议保留本节作为“项目导读入口”。

你可以直接用 **Claude / Codex** 作为“项目导读助手”，在不通读全仓库的情况下快速建立全局理解与落地路径。

建议的高频提问（可直接复制给工具）：
- “用一句话说明这个仓库解决什么问题；端到端输入/输出分别是什么？”
- “从 `{ENTRYPOINT_CMD}` 开始，逐步解释每一步做什么、产物写到哪里、如何复跑/强制重跑。”
- “解释 `{CORE_RAG_ARTIFACT}` 的产物结构，以及为什么它比逐页 QA 更稳定；对应的实现/配置开关在哪里？”
- “如果我想在新项目上落地：需要准备哪些依赖与配置（例如：LibreOffice/Poppler/LLM/mock），最小可跑的命令是什么？”

---

## 核心价值（Core Value · Features · Use Cases）

> 目的：用“**一段价值主张 + 一组特点（Features）+ 一组应用场景（Use Cases）**”把项目说清楚。  
> 写法：尽量具体，回答“**为什么需要它 / 它解决什么痛点 / 它有什么独特之处 / 在哪些业务场景最有用**”。

**价值主张（1–3 句话，写清楚收益与边界）**  
{一句话定义：这个项目把什么输入变成什么输出，给谁用，带来什么确定性的收益（效率/成本/质量/可追溯/可复现）。}

**问题诊断（可选，2–4 条，写清楚痛点而不是现象）**
- {PAIN_1：例如“信息分散导致上下文噪声/检索碎片化/口径漂移/不可回归”}
- {PAIN_2：例如“人工整理成本高、难规模化、难复用”}
- {PAIN_3：例如“缺乏来源引用与审计链路，难以评审与迭代”}

**Features（特点：强调“差异点 + 可落地”）**
- **{FEATURE_1_TITLE}**：{FEATURE_1_DESC（描述机制/产物/约束，例如：产出结构化资产、支持开关与参数化、具备护栏与失败回退、可观测/可回归）}
- **{FEATURE_2_TITLE}**：{FEATURE_2_DESC（描述为什么它比常规方案更稳定/更便宜/更快/更易维护）}
- **{FEATURE_3_TITLE}**：{FEATURE_3_DESC（描述可替换性/低耦合/兼容性/扩展点）}
- （可选）**{FEATURE_4_TITLE}**：{FEATURE_4_DESC}

**Use Cases（应用场景：强调“谁在什么场合用它做什么”）**
- **{USE_CASE_1_ROLE} / {USE_CASE_1_SCENARIO}**：{USE_CASE_1_DESC（输入是什么、触发频率、输出如何被使用、带来什么收益）}
- **{USE_CASE_2_ROLE} / {USE_CASE_2_SCENARIO}**：{USE_CASE_2_DESC}
- **{USE_CASE_3_ROLE} / {USE_CASE_3_SCENARIO}**：{USE_CASE_3_DESC}
- （可选）**{USE_CASE_4_ROLE} / {USE_CASE_4_SCENARIO}**：{USE_CASE_4_DESC}

**成功标准（可选：用于验收/回归）**
- {METRIC_1：例如“从输入到可用知识资产的端到端耗时 < X”}
- {METRIC_2：例如“高频问题命中率/可引用率/人工复核通过率 ≥ X%”}
- {METRIC_3：例如“单次问答 token 成本/延迟降低 ≥ X%”}

---

## 徽章（可选）
<!-- 可根据需要替换或移除 -->
![License](https://img.shields.io/badge/license-{LICENSE}-blue)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Status](https://img.shields.io/badge/status-active-success)

---

## 目录
- [AI 驱动快速上手（Claude / Codex）](#ai-驱动快速上手claude--codex)
- [核心价值（Core Value · Features · Use Cases）](#核心价值core-value--features--use-cases)
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
> 以下为通用占位描述，请根据实际功能补充或替换。
- 清晰的模块化设计，便于扩展与维护
- 面向 {Target users} 的友好接口
- 与 {TECH_STACK} 集成
- 可配置、可测试、可部署

---

## 架构 / 设计概览
> 简要说明系统的整体架构或核心设计思想。

- 核心组件：`{Core Module / Service / Library}`
- 接口层：`{API / CLI / UI}`
- 数据或状态管理：`{Database / Storage / In-memory}`
- 扩展点：`{Plugins / Hooks / Pipelines}`

如有需要，可在此处添加架构图或链接到更详细的设计文档。

---

## 前置条件
在开始之前，请确保已安装以下依赖：
- {Language Runtime} >= {Version}
- {Package Manager / Build Tool}
- 其他依赖（如有）

---

## 安装
```bash
# 克隆仓库
git clone https://github.com/your-org/{PROJECT_NAME}.git
cd {PROJECT_NAME}

# 安装依赖（示例）
{INSTALL_COMMAND}
```

---

## 配置
- 复制并修改示例配置：`{CONFIG_SAMPLE_PATH} -> {CONFIG_PATH}`
- 设置必要的环境变量：`{ENV_VARS}`
- 如有密钥或凭证，请使用本地 `.env` 或密钥管理工具存储

---

## 使用示例
```bash
# 运行核心流程
{RUN_COMMAND}
```

输出示例：
- {OUTPUT_ITEM_1}
- {OUTPUT_ITEM_2}

---

## 项目结构
```bash
{PROJECT_TREE}
```

---

## 开发指南
- 代码风格：{LINT_RULES / FORMATTER}
- 提交规范：{COMMIT_RULES}
- 分支策略：{BRANCH_STRATEGY}

---

## 测试
```bash
{TEST_COMMAND}
```
> 可补充集成测试/端到端测试的运行方式与跳过条件。

---

## 部署（如适用）
- 部署目标：{Cloud / On-Prem / Container}
- 交付方式：{Docker / Helm / Serverless / Wheel}
- 关键参数：{ENV / Secrets / Scaling}

---

## 路线图（可选）
- [ ] 里程碑 1：{M1_DESC}
- [ ] 里程碑 2：{M2_DESC}
- [ ] 里程碑 3：{M3_DESC}

---

## 贡献指南
- 提交 PR 前请确认通过全部测试并更新相关文档
- 讨论/Issue 模板：{ISSUE_TEMPLATE}
- 代码评审：{REVIEW_POC}

---

## 许可证
本项目遵循 `{LICENSE}` 协议，详见 `LICENSE` 文件。

---

## 维护者 / 联系方式
- Owner：{OWNER_NAME} ({OWNER_CONTACT})
- 协作渠道：{Slack / WeCom / Email}
