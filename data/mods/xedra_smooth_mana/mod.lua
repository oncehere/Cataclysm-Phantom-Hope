local ccb = require("ccb")

return ccb.ModDefinition {
    id = "xedra_smooth_mana",
    name = "Xedra：情绪渐进回蓝",
    version = "1.0.1",
    description = "梦行者在平静时以基础速度的10%恢复魔力；情绪越强恢复越快，取消35点士气门槛。",
    category = "rebalance",
    dependencies = { "xedra_evolved" },
}
