"""CommerceAgent Agent Service.

Python 侧只拥有 `agent` 与 `policy` 两个 schema，以及 Agent 编排/检索/评测逻辑。
对权威业务数据（`commerce.*`）没有任何直接数据库访问权限，只能经由 Java 类型化 API。
"""
