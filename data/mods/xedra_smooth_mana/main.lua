local ccb = require("ccb")

local interval = 180 -- Native mana recovery settles every three minutes.
local state = ccb.state.character

local function value(result)
    assert(result.ok, "Xedra smooth mana: native operation failed")
    return result.value
end

local function recover_fraction(payload)
    local actor = payload.character
    if actor.subtype ~= "avatar" then
        return
    end

    local now = ccb.services.turn()
    if now % interval ~= 0 or state.get("last_tick", -1) == now then
        return
    end
    state.set("last_tick", now)

    if not value(ccb.services.mutations.has_id_text(actor, "DREAMER")) then
        state.set("fraction", 0)
        return
    end

    local mana = value(ccb.services.spells.mana(actor))
    if mana.current >= mana.maximum or mana.regeneration_per_turn <= 0 then
        state.set("fraction", 0)
        return
    end

    -- The engine already grants floor(pulse). Only retain what it discards.
    -- This snapshot includes equipment, mutations and recovery penalties.
    local pulse = mana.regeneration_per_turn * interval
    local fraction = state.get("fraction", 0) + pulse - math.floor(pulse)
    local extra = math.floor(fraction + 1e-9)
    if extra > 0 then
        mana = value(ccb.services.spells.modify_mana(actor, extra)).after
    end

    if mana.current >= mana.maximum then
        state.set("fraction", 0)
    else
        state.set("fraction", math.max(0, fraction - extra))
    end
end

ccb.runtime.handler("recover_fraction", recover_fraction, 1)
ccb.runtime.handler("next_recovery", function()
    return interval - ccb.services.turn() % interval
end, 1)

-- Character callbacks run after the avatar's native body/mana update.
-- Their saved due turn and our character state both survive save/load.
ccb.runtime.character_recurring("recover_fraction", "next_recovery")

-- Character-scoped Lua state belongs to the player save, so do not carry a
-- body's fractional recovery over when the player takes control of an NPC.
ccb.runtime.handler("reset_fraction_on_control", function()
    state.set("fraction", 0)
end, 1)
ccb.runtime.hook("on_control_npc", "reset_fraction_on_control")
