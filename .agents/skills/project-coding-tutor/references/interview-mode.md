# Interview Mode

Convert implemented mechanisms into defensible engineering explanations. Do not turn the project into memorized buzzwords.

## 1. Start from evidence

Before drafting an answer, identify:
- what the system actually does;
- what the learner personally understands;
- which tests or traces demonstrate it;
- what is synthetic, local, deferred, or unmeasured.

Do not claim production traffic, money moved, enterprise adoption, accuracy, latency, or safety beyond measured evidence.

## 2. Use the five-part technical answer

For an important mechanism, practice:

1. **Context:** what user/system problem existed?
2. **Risk:** what could go wrong with a naive design?
3. **Decision:** what architecture/mechanism was chosen?
4. **Tradeoff:** what complexity or limitation did it introduce?
5. **Evidence:** how was it verified?

Example skeleton:

> “售后写操作可能在服务端已经提交但客户端超时。如果直接重新生成请求，可能重复创建申请。所以我让 Java 端持有稳定 operationId + payload hash，并用数据库约束/事务保证业务不变量；Python 在未知结果时查询权威状态并只用原键重试。代价是要维护操作记录和恢复流程。我们用提交后丢响应、并发重复调用等测试验证没有产生第二条业务记录。”

## 3. Ask mechanism questions, not trivia

Good questions:
- Why is this decision in Java instead of the LLM?
- Why is checkpoint not enough for exactly-once business behavior?
- What happens if the process crashes after the DB commit but before graph state advances?
- Why does a UNIQUE constraint still matter if you already check before insert?
- How do you prevent the model from controlling amount or user identity?
- What would make the fixed workflow baseline stronger than the Agent?

Weak questions for this mode:
- recite every decorator;
- list every library method;
- memorize framework marketing language.

## 4. Probe progressively

Round 1: 30-second explanation.
Round 2: one failure case.
Round 3: one alternative design.
Round 4: one code/test location.

If the learner cannot answer Round 2, return to the mechanism rather than coaching a polished script.

## 5. Resume bullets

Prefer evidence-backed bullets:

`Implemented [mechanism] to handle [failure/invariant], verified with [specific test/eval].`

Avoid:
- “built enterprise-grade secure agent” without evidence;
- “improved efficiency by 80%” without a defined baseline and measurement;
- “processed real refunds” when the project creates local synthetic refund requests.
