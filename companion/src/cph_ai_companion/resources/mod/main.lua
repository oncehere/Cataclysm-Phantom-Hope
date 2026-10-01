local ccb = require("ccb")

-- Registration and metadata scanning never start a model or external process.
-- The native bridge is enabled only after entering a world with this Mod.
ccb.runtime.handler("cph_ai_companion_ready", function()
    ccb.services.actor_control.enable(true)
end, 1)
ccb.runtime.on("world_ready", "cph_ai_companion_ready")
