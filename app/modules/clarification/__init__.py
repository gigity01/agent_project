"""跨 Turn 澄清请求模块。

本模块负责在 Planner 发现意图歧义、缺少必要参数或候选资源不唯一时，
创建 ClarificationRequest 并驱动跨 Turn 的用户追问、回答写回与基于澄清的新 Plan Revision 重规划。
"""
