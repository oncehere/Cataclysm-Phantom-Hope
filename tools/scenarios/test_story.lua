-- Offline branch regression using the actual Mod entrypoint and a tiny ccb double.
-- This does not prove native UI, inventory mutation or save-file persistence.
-- Run from the repository root: lua tools/scenarios/test_story.lua
local persistent = {}
local inventory = 0
local choice = nil
local handler = nil
local messages = {}
local consumes = 0
local actor = {}
local context = { character = actor }
function context:message(text)
    messages[#messages + 1] = text
end
local ccb = {
    state = { character = {
        get = function(key, default)
            if persistent[key] == nil then return default end
            return persistent[key]
        end,
        set = function(key, value) persistent[key] = value end,
    } },
    presentation = { choose = function() return choice end },
    runtime = { handler = function(id, callback, version)
        assert(id == "scenario_story_smoke_terminal" and version == 1)
        handler = callback
    end },
    services = {
        types = { id = function(kind, id) assert(kind == "item"); return id end },
        inventory = { consume = function(character, id, count)
            assert(character == actor and id == "rock" and count == 1)
            consumes = consumes + 1
            if inventory < count then return { ok = false } end
            inventory = inventory - count
            return { ok = true }
        end },
    },
    content = {
        Item = function(definition)
            assert(definition.id == "scenario_story_smoke_terminal")
            local item = {}
            for _, method in ipairs({"mass_grams", "volume_ml", "price_cents", "material", "on_use"}) do
                item[method] = function() end
            end
            return item
        end,
        add = function() end,
    },
}
package.loaded.ccb = ccb
local function load()
    dofile("data/mods/Scenario_Story_Smoke/main.lua")
    assert(type(handler) == "function")
end
load()
assert(handler(context) == 0 and next(persistent) == nil and consumes == 0) -- cancel
choice = "deliver"
handler(context)
assert(next(persistent) == nil and inventory == 0) -- insufficient stock leaves branch open
inventory = 2
handler(context)
assert(inventory == 1 and persistent.delivery_branch == "delivered" and persistent.delivery_count == 1)
local before = consumes
handler(context)
load() -- new closures must consult state, not a module-local completion flag
handler(context)
assert(inventory == 1 and consumes == before and messages[#messages]:find("branch=delivered", 1, true))
persistent = {} -- a different character
inventory = 2
choice = "keep"
handler(context)
load()
choice = "deliver"
handler(context)
assert(inventory == 2 and consumes == before and persistent.delivery_branch == "kept")
assert(messages[#messages]:find("delivered=0", 1, true))
print("PASS: cancel, insufficient stock, one delivery, repeated use, re-entry, and keep branch")
