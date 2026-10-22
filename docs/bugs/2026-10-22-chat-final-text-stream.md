# BUG-20261022-chat-final-text-stream：最终正文未进入实时增量

- 首次记录：2026-10-22
- 最近更新：2026-10-22
- 状态：已修复，模拟流及相关回归通过；浏览器与真实中转站待验证
- 检索词：智能问答、工具后停止、content_delta、on_chat_model_end、assistantMessage、过程说明、最终正文

## 现象与复现

排查用户反馈的工具后停止问题时发现独立遗漏：前一条模型响应已输出工具前过程说明，最后一条模型响应含有正文但只通过结束事件返回，没有正文 token 事件。此时实时界面可能仍停在过程说明，持久化内容却包含最终正文。

这是模拟协议确认的应用缺陷，不是已证实的用户本次中转站响应。用户现场的完整协议未取得。

## 根因与定位

- `agent_service.py::stream_chat_agent` 只从 `on_chat_model_stream` 发正文增量；结束时只检查缺失的工具产物/失败提示，没有补发缺失的最终正文。
- `chat.py` 从 `agent_complete` 取最终答案并保存，通过 `assistantMessage` 返回。BFF `frontend/src/app/api/bff/chat/sessions/[id]/messages/stream/route.ts` 一旦已经发送文字，便只转发持久化消息元数据，不追加正文。聊天控制器会在结束后刷新数据，无法代替实时流的正确性。
- 工具预算 middleware 替换异常模型响应为有界提示时，也可能只在图结果中出现该提示，触发同一缺口。

## 修复与影响

- 按每次模型调用单独追踪已发送正文，保留最近的模型结束响应；主图结束后，以最终响应正文核对最后一次模型的增量。
- 没有 token 事件时补发最终正文；只有正文前缀时仅发送后缀；已完整发送时不重复。多个模型调用的过程说明与正文之间加入段落分隔。
- 保留现有产物纠错/失败提示拼接、usage、取消和持久化边界。无 BFF/前端、数据库或 NDJSON 形状变更。
- 共同调用方为 `chat.py` 流式接口；非流式不依赖正文增量。见 [聊天设计](../design/feature-chat.md)。

## 验证

`tests/test_chat_final_answer.py::test_successful_final_without_token_events_is_still_emitted` 以真实 agent 驱动模拟模型：第一条响应真实发送过程说明及工具调用增量，第二条响应关闭 token 流、只返回最终答案。断言两段都进入 `content_delta`，最终答案正确、仅两次模型调用、用量正常。

同文件覆盖补救无正文时 middleware 合成的提示也进入正文增量。八组后端自检、前端类型检查/lint 和聊天状态回归的实际命令及结果见 [正文回退问题的本次验证](2026-09-21-chat-repeat-previous-answer.md#本次验证与限制)。`git diff --check` 通过。未执行真实中转站或本次浏览器端到端验证。

## 历史与关联

- 2026-10-22：排查中转 Sonnet 5.5 工具后停止时确认结束事件正文遗漏。
- 与 [末尾空响应误用过程说明](2026-09-21-chat-repeat-previous-answer.md) 为独立但可叠加的缺陷：本问题处理已有最终正文的交付，关联问题处理没有最终正文时的判断与补救。
