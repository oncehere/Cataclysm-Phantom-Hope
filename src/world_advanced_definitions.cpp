#include "world_advanced_options.h"

#include <locale>
#include <sstream>
#include <string>
#include <vector>

const std::vector<world_advanced_definition> &world_advanced_definitions()
{
    static const std::vector<world_advanced_definition> definitions = {
        {
            "SPAWN_ANIMAL_DENSITY", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Animal spawn density" ), to_translation( "Creatures" ),
            to_translation( "Scales spawns from animal groups, including mod animals. Fixed individual spawns may ignore this value. Low values remove food sources; high values can slow the game." ),
            to_translation( "multiplier" ), "1.0", 0, 50, 0.1
        },
        {
            "SPAWN_CITY_HORDE_THRESHOLD", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "City horde size threshold" ), to_translation( "Creatures" ),
            to_translation( "Cities larger than this size receive extra zombies; smaller cities use the random chance. -1 disables extra city hordes. Changes city danger and mod encounter balance." ),
            no_translation( "" ), "4", -1, 64, 1
        },
        {
            "SPAWN_CITY_HORDE_SMALL_CITY_CHANCE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Small-city horde chance denominator" ), to_translation( "Creatures" ),
            to_translation( "A city not above the threshold gets extra zombies with probability one in this number. 1 means every city. These are generated city groups, not a wandering-horde switch." ),
            no_translation( "" ), "16", 1, 1000, 1
        },
        {
            "SPAWN_CITY_HORDE_SPREAD", world_advanced_target::external, world_advanced_type::number,
            to_translation( "City horde spread" ), to_translation( "Creatures" ),
            to_translation( "Multiplies city size to determine the radius for extra zombie placement on roads. Changes encounter distribution; large radii cost more generation time. Zero is not supported." ),
            to_translation( "multiplier" ), "1.5", 0.1, 10, 0.1
        },
        {
            "SPAWN_CITY_HORDE_SCALAR", world_advanced_target::external, world_advanced_type::number,
            to_translation( "City horde population factor" ), to_translation( "Creatures" ),
            to_translation( "Extra zombie count is city size times this factor times the normal monster spawn density. 0 removes this extra population. Large values can severely slow play." ),
            to_translation( "zombies per city size" ), "80.0", 0, 1000, 1
        },
        {
            "PORTAL_STORM_IGNORE_NPC", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Portal storm creatures ignore NPCs" ), to_translation( "Creatures" ),
            to_translation( "Makes the affected portal storm enemies ignore NPCs. Changes the danger and scripted expectations of storms in the base game and mods." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "ZOMBIFY_INTO_ENABLED", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Alternative corpse zombification" ), to_translation( "Creatures" ),
            to_translation( "Enables monster definitions that turn corpses into another zombie type. Disabling changes corpse revival and can bypass creature progression supplied by mods." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "OVERRIDE_VEHICLE_INIT_STATE", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Override newly spawned vehicles" ), to_translation( "Vehicles" ),
            to_translation( "Uses the vehicle condition and fuel settings below for newly spawned vehicles. Overrides map and mod expectations; some forced vehicle conditions remain exempt." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "VEHICLE_STATUS_AT_SPAWN", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "New vehicle condition" ), to_translation( "Vehicles" ),
            to_translation( "When vehicle overrides are enabled: -1 is damaged, 0 is intact, 1 is disabled. Forced condition definitions can take precedence. Affects access to transport and mod balance." ),
            no_translation( "" ), "-1", -1, 1, 1
        },
        {
            "VEHICLE_FUEL_AT_SPAWN", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "New vehicle fuel" ), to_translation( "Vehicles" ),
            to_translation( "When vehicle overrides are enabled: -1 uses random fuel, 0 is empty, 100 is full. The current random distribution is bounded to 5-95 percent. Can alter scenario and mod vehicle supplies." ),
            to_translation( "percent" ), "-1", -1, 100, 1
        },
        {
            "VEHICLE_DEGRADATION_WHEN_DAMAGE", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Vehicle part permanent degradation" ), to_translation( "Vehicles" ),
            to_translation( "Allows damage to reduce the maximum repairable condition of vehicle parts. Also affects item definitions during loading, so this is fixed when play begins." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "NO_FAULTS", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Disable item fault definitions" ), to_translation( "Vehicles" ),
            to_translation( "Removes direct and grouped fault definitions when content is finalized, including vehicle, firearm, and clothing faults. Repairs and mod interactions may become unavailable. Explicitly forced or scripted faults can still occur." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "LATITUDE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Latitude" ), to_translation( "Climate and daylight" ),
            to_translation( "Sets the latitude for daylight calculations, not regional temperature. Polar values may have continuous daylight or darkness and unusual displayed sunrise times. Overrides geographic mod assumptions." ),
            to_translation( "degrees" ), "42.36", -90, 90, 0.01
        },
        {
            "LONGITUDE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Longitude" ), to_translation( "Climate and daylight" ),
            to_translation( "Sets longitude for astronomical calculations. Does not move the generated world or choose a climate region. Overrides geographic mod assumptions." ),
            to_translation( "degrees" ), "-71.06", -180, 180, 0.01
        },
        {
            "ETERNAL_WEATHER", world_advanced_target::external, world_advanced_type::text,
            to_translation( "Fixed weather ID" ), to_translation( "Climate and daylight" ),
            to_translation( "Use normal for natural weather, or a weather ID provided by the loaded content. Does not fix temperature or wind. Invalid IDs prevent starting; forced storms can disrupt base-game and mod events." ),
            no_translation( "" ), "normal", 0, 0, 1
        },
        {
            "HIGHWAY_GRID_ROW_SEPARATION", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "East-west highway separation" ), to_translation( "Highways" ),
            to_translation( "Spacing between east-west highway corridors in overmaps. Smaller values increase road generation and performance cost. Requires a highway component and variance below half the spacing." ),
            to_translation( "overmaps" ), "8", 4, 128, 1
        },
        {
            "HIGHWAY_GRID_COLUMN_SEPARATION", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "North-south highway separation" ), to_translation( "Highways" ),
            to_translation( "Spacing between north-south highway corridors in overmaps. Smaller values increase road generation and performance cost. Requires a highway component and variance below half the spacing." ),
            to_translation( "overmaps" ), "10", 4, 128, 1
        },
        {
            "HIGHWAY_GRID_VARIANCE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Highway intersection variance" ), to_translation( "Highways" ),
            to_translation( "Intersection displacement from the grid. Must be positive and less than half each highway spacing. Values above one quarter of either spacing risk poor connections, especially with mod geography. Large offsets can substantially increase generation time." ),
            to_translation( "overmaps" ), "2", 1, 31, 1
        },
        {
            "NO_NPC_FOOD", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Disable NPC survival needs" ), to_translation( "NPCs" ),
            to_translation( "NPCs no longer track food, thirst, or sleep normally. Changes companion and faction-camp resource needs and may bypass mod survival mechanics." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "MIN_CATCHUP_EXP_PER_POST_CATA_DAY", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Minimum NPC catch-up experience" ), to_translation( "NPCs" ),
            to_translation( "Minimum skill experience awarded per day since the Cataclysm when generating NPCs. Must not exceed the maximum. Changes late-game NPC strength and mod progression." ),
            to_translation( "experience per day" ), "50", 0, 10000, 1
        },
        {
            "MAX_CATCHUP_EXP_PER_POST_CATA_DAY", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum NPC catch-up experience" ), to_translation( "NPCs" ),
            to_translation( "Maximum skill experience awarded per day since the Cataclysm when generating NPCs. Must not be below the minimum. Large values can make generated NPCs much stronger." ),
            to_translation( "experience per day" ), "150", 0, 10000, 1
        },
        {
            "EXTRA_NPC_SKILL_LEVEL_CAP", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "NPC catch-up skill limit" ), to_translation( "NPCs" ),
            to_translation( "Highest skill level reached by catch-up experience when NPCs are generated. Does not cap all later skill training. Can alter mod NPC balance." ),
            to_translation( "skill level" ), "7", 0, 20, 1
        },
        {
            "PLAYER_MAX_STR_VALUE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum effective strength" ), to_translation( "Attributes and stamina" ),
            to_translation( "Caps effective strength for characters, including bonuses. Can limit mutations, spells, and mod progression. Inherited mod values remain unrestricted by this menu." ),
            no_translation( "" ), "30", 1, 1000, 1
        },
        {
            "PLAYER_MAX_DEX_VALUE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum effective dexterity" ), to_translation( "Attributes and stamina" ),
            to_translation( "Caps effective dexterity for characters, including bonuses. Can limit mutations, spells, and mod progression. Inherited mod values remain unrestricted by this menu." ),
            no_translation( "" ), "30", 1, 1000, 1
        },
        {
            "PLAYER_MAX_PER_VALUE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum effective perception" ), to_translation( "Attributes and stamina" ),
            to_translation( "Caps effective perception for characters, including bonuses. Can limit mutations, spells, and mod progression. Inherited mod values remain unrestricted by this menu." ),
            no_translation( "" ), "30", 1, 1000, 1
        },
        {
            "PLAYER_MAX_INT_VALUE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum effective intelligence" ), to_translation( "Attributes and stamina" ),
            to_translation( "Caps effective intelligence for characters, including bonuses. Can limit mutations, spells, and mod progression. Inherited mod values remain unrestricted by this menu." ),
            no_translation( "" ), "30", 1, 1000, 1
        },
        {
            "PLAYER_MAX_STAMINA_BASE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Base maximum stamina" ), to_translation( "Attributes and stamina" ),
            to_translation( "Base player stamina before cardio and enchantment modifiers. Alters movement and combat endurance, including mod effects. This is not the final maximum." ),
            to_translation( "stamina" ), "3500", 100, 100000, 100
        },
        {
            "PLAYER_CARDIOFIT_STAMINA_SCALING", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Cardio stamina contribution" ), to_translation( "Attributes and stamina" ),
            to_translation( "Multiplies cardiovascular fitness when calculating maximum stamina. 0 removes this contribution. Changes fitness progression and mod endurance balance." ),
            no_translation( "" ), "5", 0, 100, 1
        },
        {
            "PLAYER_BASE_STAMINA_REGEN_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Base stamina regeneration" ), to_translation( "Attributes and stamina" ),
            to_translation( "Base regeneration before fitness and other modifiers. 0 does not disable all recovery because some minimum recovery remains. Changes combat and travel balance." ),
            to_translation( "stamina per turn" ), "20.0", 0, 1000, 1
        },
        {
            "PLAYER_BASE_STAMINA_BURN_RATE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Base stamina consumption" ), to_translation( "Attributes and stamina" ),
            to_translation( "Base stamina cost used by movement and other actions. 0 does not guarantee every action is free. Changes exertion and mod endurance mechanics." ),
            no_translation( "" ), "15", 0, 1000, 1
        },
        {
            "PLAYER_HUNGER_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Base hunger rate" ), to_translation( "Survival and recovery" ),
            to_translation( "Scales baseline hunger accumulation before character modifiers. 0 suppresses this baseline, not every possible source. Can bypass survival requirements assumed by mods." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
        {
            "PLAYER_THIRST_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Base thirst rate" ), to_translation( "Survival and recovery" ),
            to_translation( "Scales baseline thirst accumulation before character modifiers. 0 suppresses this baseline, not every possible source. Can bypass survival requirements assumed by mods." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
        {
            "PLAYER_SLEEPINESS_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Base sleepiness rate" ), to_translation( "Survival and recovery" ),
            to_translation( "Scales baseline sleepiness accumulation before character modifiers. 0 suppresses this baseline, not every possible source. Can bypass survival requirements assumed by mods." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
        {
            "PLAYER_HEALING_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Player natural healing rate" ), to_translation( "Survival and recovery" ),
            to_translation( "Base natural healing before sleep, health, and other modifiers. Does not replace all medical effects. Changes injury recovery and mod medical balance." ),
            to_translation( "hit points per turn" ), "0.0001", 0, 0.01, 1e-05
        },
        {
            "NPC_HEALING_RATE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "NPC natural healing rate" ), to_translation( "Survival and recovery" ),
            to_translation( "Base natural healing before sleep, health, and other modifiers. Does not replace all medical effects. Changes injury recovery and mod medical balance." ),
            to_translation( "hit points per turn" ), "0.0001", 0, 0.01, 1e-05
        },
        {
            "NO_VITAMINS", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Disable dietary vitamins" ), to_translation( "Survival and recovery" ),
            to_translation( "Disables ordinary vitamin tracking and removes vitamin nutrition during content finalization. Other vitamin-like counters remain. Can disable nutrition mechanics expected by mods." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "COMBAT_SPEED_MODIFIER", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Weary melee speed factor" ), to_translation( "Combat and injuries" ),
            to_translation( "Scales the fatigue-related melee speed factor up to the non-weary limit. This is not a multiplier for every combat action. Changes fatigue and combat balance." ),
            to_translation( "multiplier" ), "1.0", 0.1, 10, 0.1
        },
        {
            "DISPERSION_PER_GUN_DAMAGE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Gun damage dispersion penalty" ), to_translation( "Combat and injuries" ),
            to_translation( "Dispersion added per gun damage level before overall scaling. 0 removes this penalty. Changes the usefulness of repairing firearms and mod weapon balance." ),
            no_translation( "" ), "20", 0, 1000, 1
        },
        {
            "GUN_DISPERSION_DIVIDER", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Gun dispersion divisor" ), to_translation( "Combat and injuries" ),
            to_translation( "Divides firearm dispersion; larger values make guns more accurate. Must stay positive. Changes the balance of weapons, sights, and mod firearms." ),
            to_translation( "divisor" ), "24.0", 0.1, 100, 0.1
        },
        {
            "WOUND_CHANCE", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Wound probability factor" ), to_translation( "Combat and injuries" ),
            to_translation( "Probability factor for wounds from damage: 0 prevents this wound check, 1 keeps the default. Does not prevent every injury or status effect. Changes mod medical balance." ),
            to_translation( "probability" ), "1.0", 0, 1, 0.01
        },
        {
            "PAIN_PENALTY_MOD_STR", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Pain penalty to strength" ), to_translation( "Combat and injuries" ),
            to_translation( "Fractional strength penalty per point of pain before other modifiers. 0 removes this component. Changes pain management and interacts with mod enchantments." ),
            to_translation( "fraction per pain" ), "0.005", 0, 0.1, 0.0005
        },
        {
            "PAIN_PENALTY_MOD_DEX", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Pain penalty to dexterity" ), to_translation( "Combat and injuries" ),
            to_translation( "Fractional dexterity penalty per point of pain before other modifiers. 0 removes this component. Changes pain management and interacts with mod enchantments." ),
            to_translation( "fraction per pain" ), "0.0075", 0, 0.1, 0.0005
        },
        {
            "PAIN_PENALTY_MOD_INT", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Pain penalty to intelligence" ), to_translation( "Combat and injuries" ),
            to_translation( "Fractional intelligence penalty per point of pain before other modifiers. 0 removes this component. Changes pain management and interacts with mod enchantments." ),
            to_translation( "fraction per pain" ), "0.01", 0, 0.1, 0.0005
        },
        {
            "PAIN_PENALTY_MOD_PER", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Pain penalty to perception" ), to_translation( "Combat and injuries" ),
            to_translation( "Fractional perception penalty per point of pain before other modifiers. 0 removes this component. Changes pain management and interacts with mod enchantments." ),
            to_translation( "fraction per pain" ), "0.01", 0, 0.1, 0.0005
        },
        {
            "WEARY_BMR_MULT", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Weariness threshold factor" ), to_translation( "Weariness" ),
            to_translation( "Portion of basal metabolic rate used for the weariness threshold. Larger values generally delay weariness; character modifiers and a minimum threshold still apply. Changes work and mod balance." ),
            to_translation( "multiplier" ), "0.54", 0.1, 10, 0.01
        },
        {
            "WEARY_THRESH_SCALING", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Successive weariness threshold factor" ), to_translation( "Weariness" ),
            to_translation( "Scales the threshold between successive weariness levels. Smaller values make later levels arrive sooner. Very small or zero values are unsupported because integer thresholds can stop advancing." ),
            to_translation( "multiplier" ), "0.75", 0.1, 1, 0.01
        },
        {
            "WEARY_INITIAL_STEP", world_advanced_target::external, world_advanced_type::number,
            to_translation( "First weariness threshold factor" ), to_translation( "Weariness" ),
            to_translation( "Scales the first weariness threshold. 0 removes the initial allowance. Changes the amount of activity possible before penalties and mod exhaustion balance." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
        {
            "WEARY_RECOVERY_MULT", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Weariness recovery fraction" ), to_translation( "Weariness" ),
            to_translation( "Controls recovery of the weariness tracker and calorie intake history. Must stay between 0 and 1. Zero does not remove every minimum recovery effect. Alters rest and mod survival balance." ),
            to_translation( "fraction" ), "0.05", 0, 1, 0.01
        },
        {
            "PROFICIENCY_TRAINING_SPEED", world_advanced_target::external, world_advanced_type::number,
            to_translation( "Proficiency training speed" ), to_translation( "Progression" ),
            to_translation( "Scales proficiency practice. 0 disables ordinary proficiency progress, while special training paths may differ. Can disrupt crafting and mod progression." ),
            to_translation( "multiplier" ), "1.0", 0, 100, 0.1
        },
        {
            "INT_BASED_LEARNING_BASE_VALUE", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Intelligence learning baseline" ), to_translation( "Progression" ),
            to_translation( "Intelligence at which the intelligence-based focus adjustment is neutral. Changes learning balance and interacts with mod intelligence bonuses." ),
            no_translation( "" ), "8", 0, 100, 1
        },
        {
            "INT_BASED_LEARNING_FOCUS_ADJUSTMENT", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Focus per intelligence point" ), to_translation( "Progression" ),
            to_translation( "Focus adjustment per intelligence point above or below the baseline. 0 removes this adjustment. Changes skill progression and mod balance." ),
            no_translation( "" ), "5", 0, 100, 1
        },
        {
            "INITIAL_STAT_POINTS", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Initial attribute points" ), to_translation( "Character creation" ),
            to_translation( "Changes point-based character creation. Has no equivalent effect in every point-pool mode. Can bypass or restrict character builds expected by scenarios and mods." ),
            to_translation( "points" ), "6", 0, 1000, 1
        },
        {
            "INITIAL_TRAIT_POINTS", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Initial trait points" ), to_translation( "Character creation" ),
            to_translation( "Changes point-based character creation. Has no equivalent effect in every point-pool mode. Can bypass or restrict character builds expected by scenarios and mods." ),
            to_translation( "points" ), "0", 0, 1000, 1
        },
        {
            "INITIAL_SKILL_POINTS", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Initial skill points" ), to_translation( "Character creation" ),
            to_translation( "Changes point-based character creation. Has no equivalent effect in every point-pool mode. Can bypass or restrict character builds expected by scenarios and mods." ),
            to_translation( "points" ), "2", 0, 1000, 1
        },
        {
            "MAX_TRAIT_POINTS", world_advanced_target::external, world_advanced_type::integer,
            to_translation( "Maximum trait points" ), to_translation( "Character creation" ),
            to_translation( "Changes point-based character creation. Has no equivalent effect in every point-pool mode. Can bypass or restrict character builds expected by scenarios and mods." ),
            to_translation( "points" ), "12", 0, 1000, 1
        },
        {
            "CBM_SLOTS_ENABLED", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Bionic slot restrictions" ), to_translation( "Other world rules" ),
            to_translation( "Enables body-part capacity limits for bionic installation. Can make base-game or mod bionic combinations impossible and alter existing bionic information." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "SHOW_MUTATION_SELECTOR", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Choose mutations" ), to_translation( "Other world rules" ),
            to_translation( "Shows a choice menu for supported player mutation paths. Not every scripted mutation uses it. Changes mutation randomness and can bypass mod progression expectations." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "GAME_EMP", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Temporary EMP disruption" ), to_translation( "Other world rules" ),
            to_translation( "Uses temporary electronic disruption in supported EMP paths, with a chance of permanent failure. Does not change every EMP effect. Alters electronic survival and mod balance." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "CAPITALISM", world_advanced_target::external, world_advanced_type::boolean,
            to_translation( "Bank balance in NPC trades" ), to_translation( "Other world rules" ),
            to_translation( "Allows supported NPC trades to use the player bank balance. Changes the economy and may bypass barter constraints assumed by factions and mods." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "REGION_ROADS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Intercity roads" ), to_translation( "Roads and cities" ),
            to_translation( "Enables intercity road generation where the region supports it. Does not remove every city street or special-site road. Disabling can isolate base-game and mod locations." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_RAILROADS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Railroads" ), to_translation( "Roads and cities" ),
            to_translation( "Enables railroad generation only where the region provides the needed component. Changing this can disrupt connections and assumptions of railroad mods." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "REGION_HIGHWAYS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Highways" ), to_translation( "Roads and cities" ),
            to_translation( "Enables highways where a highway component exists. Does not add a missing component. Changes travel routes, intersections, and locations expected by mods." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "CITY_SIZE", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "City size" ), to_translation( "Roads and cities" ),
            to_translation( "Overrides regional city size. 0 disables ordinary cities and city-required starts; special sites may still contain urban terrain. Changes building availability and mod scenario compatibility." ),
            no_translation( "" ), "8", 0, 16, 1
        },
        {
            "CITY_SPACING", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "City spacing" ), to_translation( "Roads and cities" ),
            to_translation( "Overrides regional city spacing. Larger values place cities farther apart. Small values can greatly increase generation cost and alter mod site placement." ),
            no_translation( "" ), "4", 0, 8, 1
        },
        {
            "REGION_FORESTS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Forests" ), to_translation( "Forests" ),
            to_translation( "Enables forests where a forest component exists. Disabling removes habitat and resources and may leave forest-dependent base-game or mod locations without valid terrain." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_FOREST_THRESHOLD", world_advanced_target::region, world_advanced_type::number,
            to_translation( "Forest noise threshold" ), to_translation( "Forests" ),
            to_translation( "Noise threshold for ordinary forest placement. Higher values generally reduce forest coverage. Must not exceed the thick-forest threshold. Alters habitat and site availability." ),
            no_translation( "" ), "0.2", 0, 1, 0.01
        },
        {
            "REGION_THICK_FOREST_THRESHOLD", world_advanced_target::region, world_advanced_type::number,
            to_translation( "Thick forest noise threshold" ), to_translation( "Forests" ),
            to_translation( "Noise threshold for thick forests. Higher values generally reduce dense forest coverage. Must be at least the ordinary forest threshold. Changes travel and mod habitat constraints." ),
            no_translation( "" ), "0.25", 0, 1, 0.01
        },
        {
            "REGION_SWAMPS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Swamps" ), to_translation( "Forests" ),
            to_translation( "Allows supported forests to become swamps. Requires existing forest and floodplain components. Disabling changes resources, monsters, and swamp-dependent mod locations." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_FOREST_TRAILS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Forest trails" ), to_translation( "Forests" ),
            to_translation( "Enables supported trails through forests. Disabling can reduce access to woodland sites and change trail-dependent mod placement." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_RIVER_SCALE", world_advanced_target::region, world_advanced_type::number,
            to_translation( "River width scale" ), to_translation( "Rivers and lakes" ),
            to_translation( "Scales river width; 0 disables river generation through this path. Large values remove usable land and can prevent base-game or mod sites and starts from fitting." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
        {
            "REGION_RIVER_FREQUENCY", world_advanced_target::region, world_advanced_type::number,
            to_translation( "New river attenuation" ), to_translation( "Rivers and lakes" ),
            to_translation( "Attenuation factor for additional main rivers: larger values produce fewer new rivers. Does not directly multiply river count. Changes crossings and water-dependent mod placement." ),
            to_translation( "factor" ), "1.5", 1, 5, 0.1
        },
        {
            "REGION_LAKES", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Lakes" ), to_translation( "Rivers and lakes" ),
            to_translation( "Enables lakes where the region provides a lake component. Disabling can remove lake-dependent special locations, including mod content." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_LAKE_THRESHOLD", world_advanced_target::region, world_advanced_type::number,
            to_translation( "Lake noise threshold" ), to_translation( "Rivers and lakes" ),
            to_translation( "Noise threshold for lake placement. Higher values generally reduce lake coverage. Large lakes can interfere with roads, starts, and base-game or mod locations." ),
            no_translation( "" ), "0.25", 0, 1, 0.01
        },
        {
            "REGION_LAKE_SIZE_MIN", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "Minimum lake area" ), to_translation( "Rivers and lakes" ),
            to_translation( "Smallest accepted lake area in overmap terrain tiles. Changes water coverage and lake-dependent location availability; extreme values may eliminate lakes." ),
            to_translation( "overmap terrain tiles" ), "20", 1, 32400, 1
        },
        {
            "REGION_LAKE_DEPTH", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "Lake bottom level" ), to_translation( "Rivers and lakes" ),
            to_translation( "Underground z-level used for lake bottoms. Must remain within supported underground levels. Changes swimming hazards and may conflict with underground mod content." ),
            to_translation( "z-level" ), "-5", -10, -1, 1
        },
        {
            "REGION_OCEANS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Oceans" ), to_translation( "Oceans" ),
            to_translation( "Enables oceans where an ocean component exists. Disabling removes ocean-dependent special locations. Enabling cannot create a component absent from a mod region." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_OCEAN_START_NORTH", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "North ocean start" ), to_translation( "Oceans" ),
            to_translation( "Distance from the origin at which the north ocean begins. -1 disables this direction. 0 can place ocean near the start and prevent base-game or mod locations from fitting." ),
            to_translation( "overmaps" ), "500", -1, 10000, 1
        },
        {
            "REGION_OCEAN_START_EAST", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "East ocean start" ), to_translation( "Oceans" ),
            to_translation( "Distance from the origin at which the east ocean begins. -1 disables this direction. 0 can place ocean near the start and prevent base-game or mod locations from fitting." ),
            to_translation( "overmaps" ), "10", -1, 10000, 1
        },
        {
            "REGION_OCEAN_START_SOUTH", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "South ocean start" ), to_translation( "Oceans" ),
            to_translation( "Distance from the origin at which the south ocean begins. -1 disables this direction. 0 can place ocean near the start and prevent base-game or mod locations from fitting." ),
            to_translation( "overmaps" ), "-1", -1, 10000, 1
        },
        {
            "REGION_OCEAN_START_WEST", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "West ocean start" ), to_translation( "Oceans" ),
            to_translation( "Distance from the origin at which the west ocean begins. -1 disables this direction. 0 can place ocean near the start and prevent base-game or mod locations from fitting." ),
            to_translation( "overmaps" ), "1000", -1, 10000, 1
        },
        {
            "REGION_RAVINE_COUNT", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "Ravine count" ), to_translation( "Ravines" ),
            to_translation( "Number of ravines requested per overmap where the component exists. More ravines fragment land, affect generation cost, and can block base-game or mod locations." ),
            no_translation( "" ), "0", 0, 10, 1
        },
        {
            "REGION_RAVINE_WIDTH", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "Ravine width" ), to_translation( "Ravines" ),
            to_translation( "Width of generated ravines. Larger values remove usable land and can sever routes or conflict with special locations from the base game and mods." ),
            to_translation( "overmap terrain tiles" ), "3", 1, 10, 1
        },
        {
            "REGION_RAVINE_DEPTH", world_advanced_target::region, world_advanced_type::integer,
            to_translation( "Ravine bottom level" ), to_translation( "Ravines" ),
            to_translation( "Underground z-level of ravine bottoms, also used by local map generation. Changes fall hazards and can conflict with underground mod content." ),
            to_translation( "z-level" ), "-3", -10, -1, 1
        },
        {
            "REGION_SPECIALS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Special locations" ), to_translation( "High-risk terrain rules" ),
            to_translation( "Enables ordinary regional special-location placement. Disabling can remove required mission and scenario locations in the base game and mods. Other placement paths may still create special terrain." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "REGION_MEGACITY", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Megacities" ), to_translation( "High-risk terrain rules" ),
            to_translation( "Requests five very large cities per overmap where the regional city component exists. Can be expensive and may violate available-building and location assumptions of mods." ),
            no_translation( "" ), "false", 0, 0, 1
        },
        {
            "REGION_NEIGHBOR_CONNECTIONS", world_advanced_target::region, world_advanced_type::boolean,
            to_translation( "Connections to neighboring overmaps" ), to_translation( "High-risk terrain rules" ),
            to_translation( "Uses neighboring overmap connections while generating the region. Disabling can leave roads and railways disconnected across boundaries and disrupt mod routes." ),
            no_translation( "" ), "true", 0, 0, 1
        },
        {
            "WORLD_TEMPERATURE_OFFSET", world_advanced_target::climate, world_advanced_type::number,
            to_translation( "Temperature offset" ), to_translation( "Climate and daylight" ),
            to_translation( "Adds to regional outdoor, underground, and root-cellar temperatures without selecting another biome. Changes freezing, food storage, survival, and mod climate assumptions. Local heat sources still apply; the separate natural-water temperature model is unchanged." ),
            to_translation( "degrees Celsius" ), "0.0", -100, 100, 1
        },
        {
            "WORLD_HUMIDITY_OFFSET", world_advanced_target::climate, world_advanced_type::number,
            to_translation( "Humidity offset" ), to_translation( "Climate and daylight" ),
            to_translation( "Adds percentage points to generated humidity, with the result bounded to 0-100 percent. Can change weather conditions and conflict with mod climate assumptions." ),
            to_translation( "percentage points" ), "0.0", -100, 100, 1
        },
        {
            "WORLD_WIND_MULTIPLIER", world_advanced_target::climate, world_advanced_type::number,
            to_translation( "Wind speed multiplier" ), to_translation( "Climate and daylight" ),
            to_translation( "Scales generated wind speed. 0 removes this generated wind, but direct overrides may differ. Changes wind chill, wind power, and mod climate balance." ),
            to_translation( "multiplier" ), "1.0", 0, 10, 0.1
        },
    };
    return definitions;
}

options_manager::cOpt world_advanced_definition::make_copt() const
{
    options_manager::cOpt option;
    option.sName = id;
    option.sPage = "world_default";
    option.sMenuText = name;
    option.sTooltip = help;
    option.hide = options_manager::COPT_NO_HIDE;
    switch( type ) {
        case world_advanced_type::boolean:
            option.sType = "bool";
            option.eType = options_manager::cOpt::CVT_BOOL;
            option.bDefault = default_value == "true";
            option.bSet = option.bDefault;
            break;
        case world_advanced_type::integer:
            option.sType = "int";
            option.eType = options_manager::cOpt::CVT_INT;
            option.iMin = static_cast<int>( minimum );
            option.iMax = static_cast<int>( maximum );
            option.iDefault = std::stoi( default_value );
            option.iSet = option.iDefault;
            option.format = "%i";
            break;
        case world_advanced_type::number: {
            option.sType = "float";
            option.eType = options_manager::cOpt::CVT_FLOAT;
            option.fMin = minimum;
            option.fMax = maximum;
            option.fStep = step;
            std::istringstream input( default_value );
            input.imbue( std::locale::classic() );
            input >> option.fDefault;
            option.fSet = option.fDefault;
            option.format = step < 0.0001 ? "%.5f" : step < 0.01 ? "%.4f" : "%.2f";
            break;
        }
        case world_advanced_type::text:
            option.sType = "string_input";
            option.eType = options_manager::cOpt::CVT_STRING;
            option.iMaxLength = 128;
            option.sDefault = default_value;
            option.sSet = default_value;
            break;
    }
    return option;
}
