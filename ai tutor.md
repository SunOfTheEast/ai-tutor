

---

# AI 智能教学系统(AI Tutoring System) 核心架构文档

## 1. 系统定位与核心原则

本系统是一个基于状态机驱动、动态上下文组装与用户画像迭代的 AI 辅导引擎。系统由三个核心底座构成：状态机教学引擎、数据库索引系统（静态知识底座）、Post Learning（动态用户适配层）。

## 1.1 核心设计原则
- **节点即原子**：运行时的最小原子不是“整题”，而是“解题步骤节点（Solution Node）”。
    
- **版本控制(Head + Revision)**：题目、解法、教学卡片（Cards）等核心教研资产均采用版本化管理，确保回溯与稳定。
    
- **结构化检索优先**：上下文构造依赖“结构化选择+显式链接”，向量检索（Embedding）仅作为辅助，绝不依赖大模型“全靠猜”。
    
- **按需裁剪(Projection)**：ContextBuilder 必须根据当前状态机状态（Step State）精准裁剪下发的上下文，防止模型偷跑或剧透。

---

## 2. 数据库结构规范(Database Schema Definition)

建议技术栈：PostgreSQL + JSONB + pgvector(可选)。

## 2.1 课程与章节树(Taxonomy DAG)

不要使用简单的字符串路径，应使用有向无环图(DAG) 以支持多父节点和前置依赖关系。
- `subjects`: 学科定义（如高中数学）。
    
- `topic_nodes`: 章节、知识点、方法族(method_family)、误区族(misconception_family)。
    
- `topic_edges`: 节点关系，支持包含(contains)、前置(prerequisite)、关联(related)。

## 2.2 题目与题面版本(Problems Layer)
- `problems`: 题目基础信息及默认发布版本引用。
    
- `problem_revisions`: 题目内容的具体版本（题干、难度、来源）。
    
- `problem_revision_topics`: 题目与 Topic 的粗粒度多对多绑定。

## 2.3 解法与步骤图(Solutions & Nodes Layer)

由于需要支持多解法、分支和回退，解法必须表示为图(Graph)。
- `solutions` / `solution_revisions`: 解法元数据与版本管理。
    
- `solution_nodes`: 运行时一等公民。包含 `step_goal`（目标）、`step_text`（正文）、`step_type`（如 quadratic_rooting）。
    
- `solution_edges`: 步骤间的图关系。`edge_type` 包括 next、branch、rollback 等，支持条件守卫 `guard_expr`。

## 2.4 教学卡片与版本(Cards Layer)

教学卡片是带有策略的可执行教学对象，非纯文本。
- `cards` / `card_revisions`: 卡片元数据与版本。`card_type` 严格限制为 method、anti_mislead、verify、pedagogy。
    
- **核心 JSONB 字段(`content_json`)**：存放具体的深层误区(`deep_pitfalls`)、反触发(`anti_triggers`)、分级脚手架(`scaffolded_hints`)、教学备注(`pedagogical_note`)。
    
- `card_revision_topics`: 卡片提取出的核心字段（如误区标签）作为结构化维度与 Topic 关联。

## 2.5 链接与锚点层(Link & Anchor Layer-索引核心)

解绑 `card_id` 与文本的硬编码，通过链接层维系上下文。
- `text_spans`: 细粒度的文本局部锚点（挂载在题目或步骤上）。
    
- `node_card_links`: 解题步骤与卡片的直接绑定关系。包含 `link_role`(如 primary_method, anti_mislead)。
    
- `span_card_links`: 局部文本片段与卡片的绑定关系。

## 2.6 会话与画像数据(Runtime & Profile)
- `tutoring_sessions` / `tutoring_turns`: 记录对话轮次与上下文特征。
    
- `trace_events`: 关键状态流转记录。记录状态转移、使用的 scaffold 层级、命中的反查卡片等。
    
- `learner_profiles` / `learner_topic_stats` / `learner_card_stats`: 学生的学习特征与卡片粒度的掌握数据。

---

## 3. 核心服务 1：ContextBuilder(上下文组装系统)

**职责**：这不是一个传统的“搜索服务”，而是一个上下文装配器。它根据 Session ID、当前步骤节点、当前状态机状态，从数据库中挑选出“最少但足够”的运行时上下文包。

## 3.1 接口契约规范(Interface Contract)

**输入参数(Request):**

```json
{
  "mode": "session",
  "session_id": "sess_001",
  "target_step_state": "T_Scaffold",
  "token_budget": 2200,
  "include_learner_profile": true,
  "include_trace_tail": true,
  "runtime_overrides": {
    "hint_level": 2,
    "attempt_count": 1
  }
}
```

**

**输出参数(Response-ContextPack):**
- 输出必须包含：元数据、题目上下文(`problem_context`)、步骤上下文(`step_context`)、过滤后的卡片上下文(`cards_context`)、学生画像偏置(`learner_context`)、运行态约束(`constraints_context`) 以及溯源信息(`provenance`)。

## 3.2 构造工作流(The 6-Step Pipeline)

ContextBuilder 必须严格按以下 6 步执行逻辑：
1. **Resolve(解析)**：根据 `session_id` 获取当前 node、状态、提示层级。
    
2. **Fetch static bundles(提取静态包裹)**：获取题目、当前及前后步骤的元数据。
    
3. **Select cards(优先级筛选卡片)**：优先级为 `显式 Node 绑定 > Span 绑定 > 步骤类型推断 > 用户偏好重排 > 教学覆盖`。
    
4. **Apply state-specific projection(状态裁剪)**：最核心一步。不同状态喂给模型不同的 JSON 切片：
    - `T_Probe_NewStep`：不给 verify 和下一步预览，只给当前 goal 和主方法逻辑。
        
    - `T_Scaffold`：仅提供当前 `hint_level` 对应的那一层提示，**严禁**输入所有 L0-L3 的提示内容。
        
    - `T_Anti_Mislead`：只装配命中的 anti-card 字段（诱导原因、错误点、纠偏桥梁）。
        
    
5. **Apply learner/runtime bias(施加画像偏置)**：如发现容易“假懂”的学生，强制配置 `verify_mode = hard`。
    
6. **Emit ContextPack(分发输出)**：返回标准 JSON 结构，交由 Prompt Renderer 渲染为文本。

---

## 4. 核心服务 2：PostLearningService(动态用户适配层)

**核心认知**：当前阶段的 Post Learning 不是对大模型进行 Fine-Tuning，而是**“画像更新 + 策略更新 + 检索偏置更新”**。

## 4.1 核心职责与数据提取

从 `trace_events` 抽取有价值的教学信号，而非单纯记录对错。
- **认知信号**：首次通过率、需要哪一级 scaffold、verify 是否通过。
    
- **误导信号**：高频命中的 `anti-card`、重复出现的错误分支。
    
- **行为/节奏信号**：回复速度、是否频繁索要 direct explain、是否有假懂倾向。

## 4.2 反哺系统回调(Agent 回调)

通过抽取的画像，直接影响 ContextBuilder 下次运行时的参数：
1. **动态 Scaffold 起点**：强学生 `L0/L1` 起步，弱学生 `L1/L2` 起步。
    
2. **Verify 强度动态判定**：假懂型学生提高 verify 阈值与触发频率。
    
3. **Anti-Card 权重置顶**：学生多次犯同类错误时，提前将相关误导卡片注入到新题目的上下文中。
    
4. **教学干预(Bailout) 调整**：针对挫败感高的学生减少 retry 次数。

---

## 5. 开发落地路线建议(Execution Roadmap)

根据当前的系统成熟度，推荐采用以下三个阶段（Phases）落地：
- **Phase 1：数据库索引层构建**。实现题目、解法、节点、卡片的增删改查及链接表的管理功能。搭建基础的 Context Builder。
    
- **Phase 2：Trace 与简易 画像**。建立对话流的 `trace_events` 落库机制，统计 scaffold 使用率、防错卡命中率，生成基础版本 Learner Profile。
    
- **Phase 3：个性化检索重排**。将 Learner Profile 接入 ContextBuilder 的第 5 步(Apply learner/runtime bias)，实现完整的闭环教学体验。

---

---

# AI 辅导 Agent 系统(V6 核心架构) 开发实操文档

## 1. 系统定位与核心架构

本系统是 AI 智能教学系统的核心中枢（Agent 层），采用 **V6 终局架构**。系统不使用不可控的自由对话 Agent，而是采用严格的**三层嵌套有限状态机（Hierarchical FSM）**进行调度控制。
- **架构总纲**：V6 包含三个嵌套的 FSM（Session、Problem、Step）和若干可通过 Feature Flags 动态启用的子策略。
    
- **设计原则**：上层管理生命周期与节奏，底层负责具体教学动作；状态转换依靠结构化数据而非自然语言猜测。
    
- **副作用隔离**：日志记录(`trace_log`)、复盘(`postmortem`)、学生画像更新等行为属于**状态转移的副作用（Side Effects）**，严禁将其设计为独立的 FSM 状态。

---

## 2. 三层嵌套状态机定义(Hierarchical FSM)

## 2.1 第一层：Session-FSM(宏观会话层)

**职责**：负责整次学习会话的生命周期与宏观节奏把控，不干涉具体题目的教学决策。
- **核心状态**：`S_Session_Start`-> `S_Goal_Setting`-> `S_Problem_Loading`-> `S_Tutoring`(调用 Problem-FSM)-> `S_Reflection`-> `S_Recommendation`-> `S_Session_End`。
    
- **特殊状态**：`S_Session_Suspend`（全局中断保护，负责持久化快照）。

## 2.2 第二层：Problem-FSM(题目生命周期层)

**职责**：负责单道题目从加载、解析、策略生成到教学完毕的全流程。
- **核心状态**：`P_Problem_Initialized`-> `P_Problem_Preprocess`(切步/打标签)-> `P_Strategy_Build`(建解题图)-> `P_Step_Enter`-> `P_Step_Tutor`(调用 Step-FSM)-> `P_Problem_Recap`-> `P_Problem_Close`。
    
- **关键机制(Branching)**：包含 `P_Branch_Select` 状态，当学生提出正确但非预期的解法时，支持切换解答分支(`branch_id`)。

## 2.3 第三层：Step-FSM(微观步骤教学层-核心)

**职责**：控制当前“解题步骤”的具体教学动作，决定如何提问、如何提示、如何纠偏。
- **探路与推进层(Probe & Advance)**：
    - `T_Probe_NewStep`(新步探测)、`T_Probe_Retry`(重试)、`T_Probe_Recovery`(纠偏后拉回主线)。
        
    - `T_Step_Advance_When_Ready`(总结当前步并推进)。
        
    
- **核心路由层(Router)**：`T_Router`(全系统最重要的隐式状态，输出结构化 JSON 决定下一步)。
    
- **辅导与抢救层(Rescue & Scaffold)**：
    - `T_Anti_Mislead`(防误导纠偏)、`T_Concept_Clarify`(概念澄清)、`T_Affect_Repair`(情绪安抚)。
        
    - `T_Elicit_Work`(诱发计算/动作)、`T_Scaffold`(四级支架提示 L0-L3)。
        
    - `T_Bailout`(熔断兜底：直接讲解、回退、标记跳过)。
        
    
- **诊断与校验层(Verify)**：`T_Verify_Light`(轻度检验)、`T_Verify_Hard`(防假懂强检验)。

---

## 3. 核心节点约束：输入/输出契约(IO Contracts)

为防止大模型“越狱”或“剧透”，**必须在代码（Prompt 组装环节）中硬编码以下契约约束**：
- **T_Probe(探测)**：只允许输出一句探测性问题；绝不提供公式结果或剧透下一步。
    
- **T_Anti_Mislead(防误导)**：必须包含“为何该路径诱人”、“错在何处”、“如何回到主线”三个元素。
    
- **T_Elicit_Work(诱发)**：只要求学生补全局部动作/算式，禁止大模型直接写全。
    
- **T_Scaffold(支架)**：严格根据传入的 `hint_level` 输出内容（L0 镜像、L1 方向、L2 关键步、L3 直接讲解当前步），只允许润色，禁止擅改数学动作。
    
- **T_Verify(校验)**：只检验当前步掌握情况，禁止长篇大论。
    
- **T_Bailout(兜底讲解)**：直接讲解当前步，**绝对禁止**把整道题直接讲完。

---

## 4. 关键引擎：Router(路由决策器)

`T_Router` 是 Step-FSM 运转的大脑。它不能是自由语言生成器，必须是一个**结构化输出分类器**。

## Router 强类型输出规范(映射为 Pydantic Schema)

后端需验证 Router 的输出必须严格符合以下字段定义：
- `student_intent`: 意图识别(`solve_attempt`, `concept_question`, `give_up`, `fast_guess`, `reflection`)。
    
- `step_correctness`: 正确度(`wrong`, `partial_correct`, `correct_but_incomplete`, `correct`)。
    
- `mislead_hit`:(Boolean) 是否踩中典型误区。
    
- `anti_card_id`:(String) 踩中误区时关联的卡片 ID。
    
- `affect_state`: 情绪/认知负载状态(`normal`, `impatient`, `confused`, `overloaded`)。
    
- `recommended_next_state`: 推荐进入的下一个状态（如 `T_Anti_Mislead`, `T_Scaffold` 等）。

---

## 5. 工程化使能开关(Feature Flags)

系统采用“全量架构构建，渐进式开启能力”的策略。在初始化配置文件时，必须支持按模块启用/禁用功能：
- **`step_kernel`**: `enable_probe_retry`, `enable_probe_recovery`, `enable_elicit_work`。
    
- **`rescue_layer`**: `enable_anti_mislead`, `enable_concept_clarify`, `enable_affect_repair`, `enable_bailout`。
    
- **`verify_layer`**: `enable_verify_light`, `enable_verify_hard`。
    
- **`branch_layer`**: `enable_branch_select`, `enable_branch_switch`。

*落地建议：MVP（最小可行性产品）阶段仅保证主线连通，关闭所有 `branch` 和复杂的 `rescue` 功能，后续通过修改配置字典逐步点亮。*

---

## 6. AI 编码执行指令(给大模型的 Prompt)

当你将上述文档提供给 AI 编程助手时，请附上以下执行指令：

> **开发者指令：**请仔细阅读上述《AI 辅导 Agent 系统(V6) 开发实操文档》以及我提供的三份规范文件（`tutoring_v6.yaml`, `router.schema.json`, `fsm_events.yaml`）。
> 
> 我们的技术栈是：**Python + Pydantic + FastAPI + LangGraph**。请按以下顺序为我生成系统底座代码：
> 
> **Phase 1：数据模型与契约定义**
> 1. 创建 `schemas/context.py`：使用 Pydantic 定义 Session、Problem、Step 三层的上下文数据结构（基于 `tutoring_v6.yaml` 的 `shared_context`）。
>     
> 2. 创建 `schemas/router.py`：将 `router.schema.json` 严格转换为 Pydantic Model，并加入业务验证逻辑。
> 
> **Phase 2：状态机路由与事件流** 3. 创建 `state_machine/events.py`：基于 `fsm_events.yaml` 定义所有的事件枚举（Enums）和中断信号（Interrupts）。4. 创建 `agents/langgraph/step_graph.py`：利用 LangGraph 框架，定义 Step-FSM。将每个状态写成独立的 node 函数，使用 Router 的输出结果作为 conditional_edges 进行状态流转。
> 

---

这样整理后，无论你用的是哪款 AI 编程辅助工具，它都能清晰地理解这是一个**确定的控制流系统**，而不是一个模糊的 Prompt 工程，从而产出结构极其严谨的后端代码。
