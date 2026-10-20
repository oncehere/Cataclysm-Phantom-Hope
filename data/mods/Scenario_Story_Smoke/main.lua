local ccb = require("ccb")
local state = ccb.state.character

local function use_terminal(context)
    local branch = state.get("delivery_branch", "unselected")
    local delivered = state.get("delivery_count", 0)
    if branch ~= "unselected" then
        context:message("Scenario record: branch=" .. branch .. "; delivered=" .. delivered .. ".")
        return 0
    end
    local choice = ccb.presentation.choose("Scenario delivery terminal: one rock", {
        { id = "deliver", label = "Deliver one rock", description = "Consume exactly one carried rock and save the delivery branch." },
        { id = "keep", label = "Keep the rock", description = "Consume nothing and save the keep branch." },
    })
    if choice == "deliver" then
        local consumed = ccb.services.inventory.consume(context.character,
            ccb.services.types.id("item", "rock"), 1)
        if not consumed.ok then
            context:message("No rock delivered. The branch is still unselected.")
            return 0
        end
        state.set("delivery_count", 1)
        state.set("delivery_branch", "delivered")
        context:message("One rock delivered. Scenario record: branch=delivered; delivered=1.")
    elseif choice == "keep" then
        state.set("delivery_branch", "kept")
        context:message("Nothing consumed. Scenario record: branch=kept; delivered=0.")
    else
        context:message("Cancelled. The branch is still unselected.")
    end
    return 0
end

ccb.runtime.handler("scenario_story_smoke_terminal", use_terminal, 1)

local terminal = ccb.content.Item {
    id = "scenario_story_smoke_terminal",
    name = "scenario delivery terminal",
    description = "A test-only terminal for one-item delivery, a permanent character story branch, and save/reload checks. No companion or model is required.",
    symbol = "?",
}
terminal:mass_grams(150)
terminal:volume_ml(250)
terminal:price_cents(0)
terminal:material("plastic", 1)
terminal:on_use("scenario_story_smoke_terminal", "Choose or inspect the story branch")
ccb.content.add(terminal)
