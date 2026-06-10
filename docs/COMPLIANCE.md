# 明镜 (MingJing) 合规声明

> 本声明逐条对应代码中**真实存在**的保护机制（标注 `文件:行`），并**如实披露已知边界与限制**——
> 不夸大、不声称未实现的能力。最后更新：随 feature/mingjing-w1-core 分支。

明镜是一个证据接地（evidence-grounded）的竞品分析多 Agent 运行时：联网检索 → 抓取 →
独立 QA 门禁打回弱证据 → 重采补强 → 仅将通过校验的结论写入报告，每条结论可溯源到原始出处。

---

## 一、数据来源与 robots 合规

- **抓取前 robots.txt 准入门**：每个 URL 在抓取前先过 `robots.is_allowed(UA=MingJingBot)`
  （`collector/robots.py:80-96`，调用点 `agents/collector.py:144,220`）。被 disallow 的命中记为
  `skipped_robots`，**永不抓取**（`collector.py:146,222`）。
- **robots 负缓存**：成功解析按域名进程级缓存；解析失败仅做短 TTL（60s）负缓存
  （`robots.py:33,59-77`），避免单次瞬时失败把一个域名永久 fail-open 白名单化。
- **robots.txt 抓取本身也走 SSRF 校验**（`agents/collector.py:36-71`）。
- **如实披露**：robots.txt 取不到时采用 **fail-open（默认允许）** 的有意宽松策略
  （`robots.py:88-95`）——这是工程取舍，非 fail-closed。

## 二、网络安全（SSRF 防护）

- `is_safe_url`（`collector/fetch.py:81-126`）：仅放行 http/https；端口白名单 {80,443}；
  对元数据主机名/IP 黑名单；字面量 IP 直接判定，主机名先 `getaddrinfo` 解析后对**所有**解析地址
  校验，命中 private/loopback/link-local/reserved/multicast/unspecified 即拒。
- **重定向逐跳再校验**（`fetch.py:146-163`）：`allow_redirects=False` 手动跟随，每一跳重跑
  `is_safe_url`，最多 5 跳——防止公开页 3xx 跳转到内网/元数据端点绕过初始校验。
- **如实披露**：代码已注明残留的 DNS-rebinding TOCTOU 风险（校验解析与连接解析为两次，
  `fetch.py:140-145`）；因抓取目标来自受限的竞品/搜索结果集而非任意用户输入，予以接受。
  本项目**不**声称 SSRF 防护完备无缺。
- **如实披露**：自托管 SearXNG 实例 URL 属受信运维配置，走**宽校验**（允许 localhost，
  `search.py:78-97`），与对不可信抓取目标的 public-only 守卫明确区分——二者不可混同。

## 三、PII / 数据脱敏

- **问卷/访谈开放文本脱敏**：对 `pii_scrub=True` 的开放题（Q5/Q10），落库前由
  `scrub_open_text`（`survey.py:233-312`，模式 `:33-63`）正则脱敏：邮箱→`[EMAIL]`、
  中国 18 位身份证→`[ID]`、手机/座机/国际电话→`[PHONE]`、6 位邮编→`[ZIP]`、
  触发短语（“我叫/我是/my name is”）之后的姓名首 token→`[NAME]`，并返回脱敏计数；
  `survey_seed` 落库的 `raw_text` 为脱敏后文本（`survey_seed.py:26,50`）。前端在
  问卷卡片上以“脱敏”标记逐题展示。
- **可观测日志密钥脱敏**：`trace.py:16-97` 在 `trace_events`/`llm_calls` 入库前将
  `MINIMAX_API_KEY` 的值替换为 `[REDACTED_API_KEY]`。
- **已知限制（不可过度声称）**：
  - 姓名脱敏是**正则启发式，不是 NER**：仅替换显式触发短语之后的姓名首 token；
    句中无触发短语的人名、多 token 姓名的非首部分不保证脱敏（`survey.py:52-54` 已自述）。
  - 密钥脱敏当前**仅覆盖 `MINIMAX_API_KEY` 这一个环境变量的精确值**，并非通用
    `sk-`/`ark-` 模式脱敏。
  - `scrub_open_text` 仅用于**问卷开放文本**；抓取的证据正文有意**保名**以供分析。

## 四、证据诚实性 / 不捏造（QA 门禁）

- **HALLUCINATED_SNIPPET**（`qa/rules.py:128-150`）：每条引用 snippet 必须是其来源 `raw_text`
  的逐字子串（空白归一后比对），否则判为捏造。
- **VALUE_UNSUPPORTED**（`qa/rules.py:299-392`）：结构化 value 中 required 子字段下的可校验
  字符串叶子（≥4 字符且含字母）必须出现在所引来源文本；数值叶子按整 token 精确 Decimal 比对
  （`12` 不被 `120` 接地），防伪造数字；derived 子字段（如 depth）豁免。
- **抗 prompt 注入**：WEAK_EVIDENCE / CONTRADICTION 一律由结构化元数据（独立可注册域名、
  权威来源类型、每来源 stance 枚举、JSON 签名）判定，**从不**向 LLM 询问自由文本结论
  （`qa/rules.py:109-233`）——注入的指令字符串无法翻转判定。
- **Writer 投影不变式**（`agents/writer.py`）：报告是 QA 通过结论的纯确定性投影，
  无背书的结论永不进入报告；Writer 无 LLM 调用。

## 五、来源出处与可追溯

- 每条证据带 `source_mode` 出处标记：实时抓取 = **LIVE**，只读缓存命中 = **CACHED**
  （`cache.get` 始终重标 CACHED，`cache.py:95-100`），仅用搜索摘要 = **SNIPPET**
  （`collector.py:160,242,261`）；并附 `content_hash`（sha256 前 16 位，`fetch.py:53-56`）。
  读取缓存的页面永远诚实标 CACHED，绝不伪装为实时。前端证据抽屉与溯源标签如实展示该出处。

## 五·甲、演示语料出处声明（demo corpus provenance）

- **评分演示 run 的语料**（`demo/corpus/*.json`）为**真实公开网页的逐字片段**
  （server-rendered 页面正文的 verbatim span，含原 URL 与 content_hash），仅为演示
  可复现而预抓取缓存——**不是手写的虚构数据**。其 `source_mode` 如实标 `CACHED`/`SNIPPET`。
- **模拟问卷/访谈行**（fixture）一律 `source_mode=SIMULATED`，前端徽标
  「模拟问卷数据·不参与分档」，且被 `scoring.contributes_to_tier` 从一切可信度计算
  （档位、佐证、矛盾）中排除；真实问卷须经 `POST /runs/{id}/survey/import`
  （PII 脱敏后落库，`INGESTED`）才有权重。
- 推理/QA/升级过程为**真实系统行为**（real LLM + 确定性 QA），非脚本回放；
  录屏主线使用该可复现语料，联网采集能力另行单独展示（组织方认可的口径）。

## 六、第三方 ToS 立场与取数边界

- 仅使用 keyless/受信 provider（DuckDuckGo、自托管 SearXNG）与显式提供 key 的 API
  （Tavily、Brave、博查 Bocha）；所有 provider 失败均非致命（`search.py`）。
- **抓取行为**尊重 robots；超出 fetch 预算的候选**退化为仅使用搜索引擎自带 snippet、
  不发起整页抓取**（`collector.py:250-266`）。
- **如实披露**：robots 门禁主要约束**整页抓取**；snippet 兜底路径使用搜索 API 已返回的摘要，
  未对该候选单独重跑 `robots.is_allowed`。因此“robots-disallowed URL 绝不被抓取”在 fetch
  预算内路径严格成立（disallowed 直接跳过、既不抓也不 snippet，`collector.py:220-223`），
  但本项目不笼统声称所有取数行为统一受 robots 门控。

## 七、泄露凭据处置状态（2026-06-10 实测）

开题材料中的共享 Ark 凭据曾随材料文件存在于本地（文件已 gitignore、从未提交）。
2026-06-10 复核结果：

- **git 对象库干净**：对全部 git objects（可达历史 + dangling + pack，
  `git cat-file --batch-all-objects`）按两枚候选凭据全文扫描，**0 命中**——
  此前评审所称「完整 key 以 dangling blob 留存、git fsck 可恢复」在当前仓库状态**不成立**。
- **凭据已被作废（实证）**：对 Ark `/chat/completions` 用两枚盘上候选凭据各发起一次
  最小请求，均返回 `401 AuthenticationError: The API key doesn't exist`——
  泄露凭据已无法使用。组织方的书面作废确认仍建议获取（human-only 事项）。
- 现行口径：可用 key 仅经私下渠道获取、只注入一次性 shell 环境，
  **不落盘、不入 git、不进截图/录屏**（见 DEMO_RUNBOOK §A 脱敏警告）。

## 八、豆包/Volcengine Ark 接入状态（2026-06-10 已验证）

run `33835db0` 全链路跑在 Doubao-Seed-2.0-lite EP 上（18 条 `llm_calls` 模型指纹均为
`ep-20260514111325-xjmj7`）；确定性门禁在官方模型下同样严格：5 提议 → 1 准入（强档，
逐字复核 100%），4 留存有 issue code。key 仅注入一次性进程环境，未落盘、未入 git。
默认演示主线仍为 MiniMax-M2.7 高幻觉压测口径（gate provider-agnostic，`CLAUDE.md`）。

## 九、当前合规缺口（诚实清单）

- 自由文本姓名为正则 best-effort 脱敏，非 NER（见 §三）。
- 密钥脱敏仅覆盖单一环境变量值（见 §三）。
- 组织方对已作废旧凭据的**书面**确认仍待获取（401 实测见 §七；human-only）。

> 以上每条主张均可在所引 `文件:行` 处核验；缺口均已主动列出，不回避。
