# Scenario Story Smoke

一个独立、可关闭的 Lua 场景素材，供物品交付、剧情分支和存读档验收。
依赖只有核心 `ccb`，不依赖 AI 同伴、LLM、`Lua_First_Example` 或 `TEST_DATA`。
使用已有 `Lua_First_Example` 所示的原生 Item、菜单、背包消费和角色持久状态接口，
没有新增游戏接口或剧情执行器。

用 [场景入口](../../../tools/scenarios/README.md) 的 `story-delivery` 准备隔离目录。
新建世界时核对预设已包含 `Scenario_Story_Smoke`，用调试菜单生成
`scenario_story_smoke_terminal` 和两块 `rock`。

- 使用终端选 **Deliver one rock**：从当前角色携带的物品消费恰好一块石头，
  保存 `delivery_branch=delivered`、`delivery_count=1`。这是终端接收点的交付，
  不声称实现 NPC 物品转移。
- 选 **Keep the rock**：不消费物品，保存 `delivery_branch=kept`。
- 取消或缺少物品：不提交分支，仍能重新选择。
- 已选分支再次使用只显示持久记录，不重复消费。保存、退出、重进后核对记录与库存。
- 每个角色只能选择一次。新角色或新隔离运行用于测试另一分支；没有清空状态的后门。

加载检查只能证明内容加载。实际菜单、消费数量与存读档仍需按生成的
`CHECKLIST.md` 人工验收；启动工具不会自动标记通过。
