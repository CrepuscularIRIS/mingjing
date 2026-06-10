# QA Gate Calibration Set

答辩硬证据:**我们的 judge 可信,准确率有分母。**

明镜的 QA gate 是确定性的(无 LLM、无置信小数),所有裁决可被人工逐条复核。
本校准集用一组人工标注的 claimset 把 gate 的判定与「人应当得到的判定」逐例对齐,
给出每类 IssueCode 与整体 admit/withhold 的 precision / recall / accuracy —— 让
"judge 准不准" 从口号变成有分母的数字。


## 口径边界 (Scope of the claim)

- 期望标签由作者(AI 工程师)人工推理标注并逐例断言一致;**非盲测、非第三方独立标注**。
- 因测试同时断言每例 expected==actual,门禁通过时 P/R/acc 必为 1.00 ——
  这组数字的含义是「43 例全一致、0 已知缺口」的**一致性证明**(且任何人重跑结果相同),
  不是对未知分布的独立统计估计。新增用例若与 gate 不一致,会进入 known_gaps 并被诚实披露。

## 方法 (Method)

- **谁标注**:人工逐例标注 (`labeled_by: "human-review 2026-06-10"`)。每例的
  `expected_codes` 由人工依据 `src/mingjing/qa/rules.py` 与 `src/mingjing/scoring.py`
  的文档化规则推理得出,**不是**先跑 `qa_check` 再抄回标签(那是循环论证)。
  每例 `description` 用一句中文记录了该标注的推理依据。
- **多少例**:**43** 个标注用例(任务下限 40),存于
  `tests/fixtures/qa_calibration.json`,与 `qa_check` 的输入契约
  (`claims` / `sources` / `coverage`)逐字段一致。
  - 干净通过(空 `expected_codes`,即应 admit):**17** 例
  - 应 withhold(至少一条 issue):**26** 例
  - 边界 / 近失误用例(`BOUNDARY-*`):**8** 例
  - 每类 IssueCode 正例数:SCHEMA_GAP 6、WEAK_EVIDENCE 8、HALLUCINATED_SNIPPET 4、
    CONTRADICTION 3、LOW_COVERAGE 4、VALUE_UNSUPPORTED 7(每类 ≥3)。
- **怎么算**:`tests/test_qa_calibration.py` 加载 fixture,对每例运行真实
  `qa_check`,然后:
  1. **逐例断言** `expected == actual`(gate 行为与人工标签完全一致);
  2. **逐 IssueCode** 的 precision / recall(以「该 code 是否应出现」为正类);
  3. **claimset 级二元 admit/withhold** 的 precision / recall / accuracy,其中
     正类 = withhold(gate 至少报一条 issue,verdict=`reject`),
     负类 = admit(无 issue,verdict=`pass`)。

  `known_gaps`(见下)中的用例**不计入** precision/recall 总体:它们度量的是
  标注者已承认的 gate 缺口,而非 gate 对可信标签的准确率。

> 复跑:`uv run pytest tests/test_qa_calibration.py -q`(全绿);
> 看 scoreboard:`uv run pytest tests/test_qa_calibration.py -s -k emit_metrics`。

## 结果 (Results)

总体 **43** 例(`known_gaps` 为空,全部计入)。

### claimset 级 admit / withhold(二元)

| 指标 | 数值 | 混淆矩阵 |
|------|------|----------|
| Precision | **1.00** | tp=26, fp=0 |
| Recall | **1.00** | tp=26, fn=0 |
| Accuracy | **1.00** | (tp=26 + tn=17) / 43 |

- **零假阳性 (fp=0)**:没有一个应 admit 的干净 claimset 被误判 withhold ——
  gate 不会因「过度谨慎」而埋没真实证据。
- **零假阴性 (fn=0)**:没有一个应 withhold 的脏 claimset 被放行 ——
  铁律「杜绝假阳性放行」在这 43 例上成立。

### 逐 IssueCode

| IssueCode | Precision | Recall | (tp, fp, fn) |
|-----------|-----------|--------|--------------|
| SCHEMA_GAP | 1.00 | 1.00 | (6, 0, 0) |
| WEAK_EVIDENCE | 1.00 | 1.00 | (8, 0, 0) |
| CONTRADICTION | 1.00 | 1.00 | (3, 0, 0) |
| HALLUCINATED_SNIPPET | 1.00 | 1.00 | (4, 0, 0) |
| LOW_COVERAGE | 1.00 | 1.00 | (4, 0, 0) |
| VALUE_UNSUPPORTED | 1.00 | 1.00 | (7, 0, 0) |

> 注:`IssueCode` 共 6 个成员;`SCHEMA_GAP` 同时承载「inference lineage 完整性」
> 这一行为类(`SCHEMA_GAP-04` 即此类的正例),因此任务所述「7 类」中第 7 类
> 在代码里复用 `SCHEMA_GAP` code。

## 边界 / 近失误用例覆盖

校准集刻意包含 8 个最容易误判的边界,逐项锁定 gate 的正确切分:

| 用例 | 设计意图 | 期望 |
|------|----------|------|
| BOUNDARY-01 | 两独立域名(权威+弱)均 supports → 应过 | admit |
| BOUNDARY-02 | 两弱类型域名 supports → moderate(gate 只拒 weak,不拒 moderate) | admit |
| BOUNDARY-03 | 同站(同 registrable domain)supports+refutes → 非跨源矛盾 | admit |
| BOUNDARY-04 | 一真一模拟:SIMULATED 不计档位 → 仅 1 真实域名 moderate,仍不报错 | admit |
| BOUNDARY-05 | 单源片段完全逐字 → 不过度拒绝(锁定 G5) | admit |
| BOUNDARY-06 | 必填字段缺失 → 应拒(与 CLEAN-07/10 的「可选缺失无害」成对照) | SCHEMA_GAP |
| BOUNDARY-07 | 数字不在原文(原文 120/2012 含 '12' 子串但无整 token) → 应拒 | VALUE_UNSUPPORTED |
| BOUNDARY-08 | 逗号千分位接地 + 派生 depth 豁免 → 应过 | admit |

另有跨规则的组合用例:`MULTI-01..03` 同例触发多 code,
`CONTRADICTION-03`/`LOW_COVERAGE-03` 验证矛盾/零覆盖与 WEAK_EVIDENCE 的叠加,
`INFERENCE-01..03` 验证 inference 的 value 仍被无条件接地、lineage 完整性、
以及「显式 inference 标签不能绕过 value gate」。

关键标注依据(供复核):评分器仅把 `relevance == "supports"` 的来源计为支持票
(`relevance: "direct"` 不计,故零 supports → weak);`VALUE_UNSUPPORTED` 只检查
**必填**子字段下的可查叶子(≥4 字符且含字母的字符串,或非派生数字),可选子字段
不在硬门内;矛盾会把 strong 降到 moderate 但**永远不会**降到 weak。

## known_gaps

**当前为空。** 43 例全部 `expected == actual`,无需把任何用例移入
`known_gaps`。

`known_gaps` 的契约:若未来某例经复核确认是 gate 的**真实缺口**(而非标注错误),
**不修改 `rules.py` 来削弱 gate**,而是把该例移入 fixture 的 `known_gaps` 数组并
记录 `actual_codes`(gate 的真实行为)。届时:

- `test_each_case_matches_label` 对该例改为断言 gate 的**当前真实行为**(不静默纠正);
- 该例从 precision/recall 总体中**剔除**(它度量缺口,不度量准确率);
- 本文件此处列出该缺口与说明。
