"""Execute generated named predicates.

Native integration is a separate gate.
"""

import shutil
import subprocess
import unittest

import migrate_lua_first as migration


@unittest.skipUnless(shutil.which("lua"), "Lua interpreter required")
class NamedPredicateMigrationTest(unittest.TestCase):
    def test_stored_creature_beta_queries_accept_live_monsters(self):
        for condition, expected, query_calls in (
            ({"npc_has_species": "ZOMBIE"}, True, 1),
            ({"npc_has_flag": "SEES"}, True, 1),
            ({"or": [{"npc_has_species": "ZOMBIE"}, {"npc_has_trait": "QUICK"}]}, True, 1),
            ("npc_is_alive", True, 1),
            ("npc_is_outside", True, 1),
            ("npc_is_avatar", False, 1),
            ({"not": "npc_is_avatar"}, True, 1),
            ({"and": ["npc_is_alive", "npc_is_outside"]}, True, 2),
            ({"npc_is_on_terrain_with_flag": "FLAT"}, True, 2),
        ):
            with self.subTest(condition=condition):
                lines = migration.render_static_set_condition(
                    {"set_condition": "creature_beta", "condition": condition},
                    True, False, True, False, None, "actor", "setter_beta",
                )
                self.assertIsNotNone(lines)
                query = migration.render_eoc_condition_expression(
                    {"get_condition": "creature_beta"},
                    named_condition_alpha_actor_proven=True,
                    npc_actor_proven=True, npc_actor_expression="context.actors.beta",
                )
                self.assertIsNotNone(query)
                script = "\n".join([
                    "local actor={kind='creature',subtype='character',is_valid=function() return true end}",
                    "local monster={kind='creature',subtype='monster',is_valid=function() return true end}",
                    "local context={data={},actors={alpha=actor,beta=monster}}",
                    "local calls=0",
                    "local function service_value(result) assert(result.ok); return result.value end",
                    "local function creature_query(owner,id)",
                    "assert(owner==monster and ((id.kind=='species' and id.value=='ZOMBIE') or",
                    "(id.kind=='json_flag' and id.value=='SEES'))); calls=calls+1",
                    "return {ok=true,value=true} end",
                    "local position={x=1,y=2,z=0}",
                    "local function snapshot(owner)",
                    "assert(owner==monster); calls=calls+1",
                    "return {ok=true,value={kind='monster',dead=false,outside=true,position=position}} end",
                    "local services={types={id=function(kind,value) return {kind=kind,value=value} end},",
                    "creatures={has_species=creature_query,has_flag=creature_query,snapshot=snapshot},",
                    "world={tile_has_flag=function(p,kind,flag)",
                    "assert(p==position and kind=='terrain' and flag=='FLAT'); calls=calls+1; return true end},",
                    "mutations={has_id_text=function() error('short-circuited Character query executed') end}}",
                    "\n".join(lines or []),
                    "assert((" + query + ")==" + migration._lua_literal(expected) + "); assert(calls==" + str(query_calls) + ")",
                    "for _,invalid in ipairs({{kind='item'},",
                    "{kind='creature',subtype='monster',is_valid=function() return false end}}) do",
                    "context.actors.beta=invalid; assert(not (" + query + ")); assert(calls==" + str(query_calls) + ") end",
                    "context.actors.beta=nil; assert(not (" + query + ")); assert(calls==" + str(query_calls) + ")",
                ])
                result = subprocess.run([shutil.which("lua"), "-"], input=script,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_stored_boolean_predicates_guard_only_evaluated_beta_leaves(self):
        alpha = {"u_has_trait": "QUICK"}
        beta = {"npc_has_trait": "QUICK"}
        cases = (
            ({"or": [alpha, beta]}, True, None, True, 1),
            ({"and": [alpha, beta]}, False, None, False, 1),
            ({"not": {"and": [alpha, beta]}}, False, None, True, 1),
            ({"not": {"or": [alpha, beta]}}, True, None, False, 1),
            ({"or": [alpha, beta]}, False, None, False, 1),
            ({"and": [alpha, beta]}, True, None, False, 1),
            ({"not": beta}, True, None, False, 0),
            ({"not": {"and": [alpha, beta]}}, True, None, False, 1),
            ({"or": [alpha, beta]}, False, True, True, 2),
            ({"and": [alpha, beta]}, True, False, False, 2),
            ({"not": beta}, True, False, True, 1),
        )
        for condition, alpha_matches, beta_matches, expected, calls in cases:
            # test_eoc must preserve the same lazy recursive semantics rather
            # than hiding a whole compound behind one eager beta guard.
            for referenced in (False, True):
                with self.subTest(condition=condition, alpha=alpha_matches,
                                  beta=beta_matches, referenced=referenced):
                    lines = migration.render_static_set_condition(
                        {"set_condition": "lazy", "condition":
                         {"test_eoc": "nested"} if referenced else condition},
                        True, False, True, False,
                        {"nested": {"condition": condition}}, "actor", "setter_beta",
                    )
                    self.assertIsNotNone(lines)
                    query = migration.render_eoc_condition_expression(
                        {"get_condition": "lazy"},
                        named_condition_alpha_actor_proven=True,
                        npc_actor_proven=True, npc_actor_expression="context.actors.beta",
                    )
                    self.assertIsNotNone(query)
                    script = "\n".join([
                        "local function live(subtype) return {kind='creature',subtype=subtype,is_valid=function() return true end} end",
                        "local actor,setter_beta=live('avatar'),live('npc')",
                        "local later_alpha,later_beta=live('character'),live('npc')",
                        "local context={data={},actors={alpha=actor,beta=setter_beta}}",
                        "local calls=0",
                        "local function service_value(result) assert(result.ok); return result.value end",
                        "local services={mutations={has_id_text=function(owner,id)",
                        "assert(id=='QUICK'); calls=calls+1",
                        "if owner==later_alpha then return {ok=true,value=" + migration._lua_literal(alpha_matches) + "} end",
                        "assert(owner==later_beta); return {ok=true,value=" + migration._lua_literal(beta_matches is True) + "} end}}",
                        "\n".join(lines or []),
                        "actor=later_alpha; context.actors={alpha=later_alpha,beta=" +
                        ("nil" if beta_matches is None else "later_beta") + "}",
                        "assert((" + query + ")==" + migration._lua_literal(expected) + ")",
                        "assert(calls==" + str(calls) + ")",
                    ])
                    result = subprocess.run([shutil.which("lua"), "-"], input=script,
                                            text=True, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_beta_named_literal_does_not_require_an_evaluating_beta(self):
        for condition in (
            {"u_has_trait": {"global_val": "stored_condition_beta"}},
            {"u_has_trait": "stored_condition_beta"},
            {"compare_string": ["stored_condition_beta", "stored_condition_beta"]},
        ):
            with self.subTest(condition=condition):
                lines = migration.render_static_set_condition(
                    {"set_condition": "alpha_only", "condition": condition},
                    True, False, False, False, None, "actor", None,
                )
                self.assertIsNotNone(lines)
                query = migration.render_eoc_condition_expression(
                    {"get_condition": "alpha_only"},
                    named_condition_alpha_actor_proven=True,
                )
                self.assertIsNotNone(query)
                script = "\n".join([
                    "local actor={kind='creature',subtype='character',is_valid=function() return true end}",
                    "local context={data={},actors={alpha=actor}}",
                    "local calls=0",
                    "local function service_value(result) assert(result.ok); return result.value end",
                    "local services={variables={resolve=function(data,owner,scope,name)",
                    "assert(data==context.data and owner==nil and scope=='global' and name=='stored_condition_beta')",
                    "return {ok=true,value={exists=true,value='QUICK'}} end},",
                    "mutations={has_id_text=function(owner,id)",
                    "assert(owner==actor and (id=='QUICK' or id=='stored_condition_beta'))",
                    "calls=calls+1; return {ok=true,value=true} end}}",
                    "\n".join(lines or []),
                    "assert(context.actors.beta==nil)",
                    "assert(" + query + ")",
                    "assert(calls==" + ("0" if "compare_string" in condition else "1") + ")",
                ])
                result = subprocess.run([shutil.which("lua"), "-"], input=script,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_named_predicate_combines_later_alpha_and_beta_without_capture(self):
        lines = migration.render_static_set_condition(
            {"set_condition": "pair", "condition": {"and": [
                {"u_has_trait": {"npc_val": "alpha_trait"}},
                {"npc_has_trait": {"u_val": "beta_trait"}},
            ]}}, True, False, True, False, None, "actor", "setter_beta",
        )
        self.assertIsNotNone(lines)
        query = migration.render_eoc_condition_expression(
            {"get_condition": "pair"}, named_condition_alpha_actor_proven=True,
            npc_actor_proven=True, npc_actor_expression="context.actors.beta",
        )
        self.assertIsNotNone(query)
        script = "\n".join([
            "local function live(subtype) return {kind='creature', subtype=subtype,",
            "is_valid=function() return true end} end",
            "local actor, setter_beta = live('avatar'), live('npc')",
            "local later_alpha, later_beta = live('character'), live('avatar')",
            "local calls = 0",
            "local context = {data={}, actors={alpha=actor,beta=setter_beta}}",
            "local services = {variables={}, mutations={}}",
            "local function service_value(r) assert(r.ok); return r.value end",
            "services.variables.resolve = function(data, owner, scope, name)",
            "assert(data == context.data)",
            "if name == 'alpha_trait' then assert(owner==later_beta and scope=='npc'); return {ok=true,value={exists=true,value='QUICK'}} end",
            "assert(name=='beta_trait' and owner==later_alpha and scope=='u'); return {ok=true,value={exists=true,value='TOUGH'}}",
            "end",
            "services.mutations.has_id_text = function(owner,id)",
            "calls=calls+1",
            "assert((owner==later_alpha and id=='QUICK') or (owner==later_beta and id=='TOUGH'))",
            "return {ok=true,value=true} end",
            "\n".join(lines),
            "actor=later_alpha; context.actors={alpha=later_alpha,beta=later_beta}",
            "assert(" + query + "); assert(calls==2)",
            "for _, invalid in ipairs({{kind='item'}, {kind='creature',subtype='monster'},",
            "{kind='creature',subtype='npc',is_valid=function() return false end}}) do",
            "context.actors.beta=invalid; assert(not (" + query + ")); assert(calls==2) end",
            "context.actors.beta=nil; assert(not (" + query + ")); assert(calls==2)",
        ])
        result = subprocess.run([shutil.which("lua"), "-"], input=script,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stored_npc_only_queries_reject_other_character_subtypes(self):
        for condition, field, expected in (
            ({"npc_has_class": "NC_NONE"}, "class", {"value": "NC_NONE"}),
            ({"npc_aim_rule": "AIM_PRECISE"}, "aim", "AIM_PRECISE"),
            ({"npc_engagement_rule": "ENGAGE_ALL"}, "engagement", "ENGAGE_ALL"),
            ({"npc_cbm_reserve_rule": "CBM_RESERVE_ALL"}, "cbm_reserve", "CBM_RESERVE_ALL"),
            ({"npc_cbm_recharge_rule": "CBM_RECHARGE_ALL"}, "cbm_recharge", "CBM_RECHARGE_ALL"),
        ):
            with self.subTest(condition=condition):
                lines = migration.render_static_set_condition(
                    {"set_condition": "npc_only", "condition": condition},
                    True, False, True, False, None, "actor", "setter_beta",
                )
                self.assertIsNotNone(lines)
                query = migration.render_eoc_condition_expression(
                    {"get_condition": "npc_only"}, named_condition_alpha_actor_proven=True,
                    npc_actor_proven=True, npc_actor_expression="context.actors.beta",
                )
                state = migration._lua_literal({field: expected})
                script = "\n".join([
                    "local actor = {}",
                    "local context={actors={}}",
                    "local calls=0",
                    "local services={npcs={}}",
                    "local function service_value(r) assert(r.ok); return r.value end",
                    "local function query_npc(npc)",
                    "assert(npc==context.actors.beta and npc.subtype=='npc')",
                    "calls=calls+1; return {ok=true,value=" + state + "} end",
                    "services.npcs.get=query_npc; services.npcs.ai_rules=query_npc",
                    "\n".join(lines),
                    "for _, subtype in ipairs({'avatar','character'}) do",
                    "context.actors.beta={kind='creature',subtype=subtype,is_valid=function() return true end}",
                    "assert(not (" + query + ")); assert(calls==0) end",
                    "context.actors.beta={kind='creature',subtype='npc',is_valid=function() return true end}",
                    "assert(" + query + "); assert(calls==1)",
                ])
                result = subprocess.run([shutil.which("lua"), "-"], input=script,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_stored_predicate_uses_evaluating_dialogue_beta(self):
        lines = migration.render_static_set_condition(
            {
                "set_condition": "beta_test",
                "condition": {"npc_has_trait": "QUICK"},
            },
            True, False, True, False, None, "actor", "actor",
        )
        self.assertIsNotNone(lines)
        query = migration.render_eoc_condition_expression(
            {"get_condition": "beta_test"}, avatar_actor_proven=True,
            named_condition_alpha_actor_proven=True, npc_actor_proven=True,
            npc_actor_expression="context.actors.beta",
        )
        self.assertIsNotNone(query)
        script = "\n".join([
            "local function live_actor(subtype)",
            " return {kind='creature', subtype=subtype, is_valid=function() return true end}",
            "end",
            "local actor, new_partner = live_actor('avatar'), live_actor('npc')",
            "local target_partner = new_partner",
            "local context = { actors = { alpha = actor, beta = actor } }",
            "local function service_value(result)",
            "  assert(result.ok); return result.value",
            "end",
            "local services = {",
            "types = { id = function(kind, id) return id end },",
            "creatures = {snapshot = function(owner) return {ok=true, value={kind=owner.subtype}} end},",
            "mutations = { has_id_text = function(owner, id)",
            "assert(id == 'QUICK')",
            "return {ok=true, value=owner == target_partner}",
            "end } }",
            "\n".join(lines),
            "assert(not (" + query + "))",
            "local parent = context",
            "local child = {",
            "actors={alpha=actor, beta=new_partner}, conditions={}}",
            "for name, predicate in pairs(context.conditions) do",
            "child.conditions[name]=predicate end",
            "context = child",
            "assert(" + query + ",",
            "'stored predicate reused the defining participant mapping')",
            "context = parent",
            "assert(not (" + query + "))",
            "context.actors.beta = nil",
            "target_partner = actor",
            "assert(not (" + query + "), 'absent beta must not become evaluating alpha')",
            "context.actors.beta = {kind='item'}",
            "assert(not (" + query + "), 'an item beta cannot gain Character proof')",
            "context.actors.beta = {kind='creature', subtype='npc', is_valid=function() return false end}",
            "assert(not (" + query + "), 'stale beta cannot gain Character proof')",
        ])
        result = subprocess.run(
            [shutil.which("lua"), "-"], input=script, text=True,
            capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_empty_named_predicate_can_be_written_read_and_replaced(self):
        def setter(expression):
            lines = migration.render_static_set_condition(
                {"set_condition": "", "condition": {"math": [expression]}},
                True, False, False, False, None, "actor", None,
            )
            self.assertIsNotNone(lines)
            return "\n".join(lines)

        query = migration.render_eoc_condition_expression(
            {"get_condition": ""}, avatar_actor_proven=True,
            named_condition_alpha_actor_proven=True,
        )
        self.assertIsNotNone(query)
        # const_dialogue stores empty keys normally, returns false when absent,
        # and replaces the predicate on a second assignment to the same key.
        script = "\n".join([
            "local actor = {}",
            "local context = {}",
            "assert(not (" + query + "))",
            setter("1 == 1"),
            "assert(type(context.conditions[\"\"]) == \"function\")",
            "assert(" + query + ")",
            setter("1 == 2"),
            "assert(not (" + query + "))",
        ])
        result = subprocess.run(
            [shutil.which("lua"), "-"], input=script, text=True,
            capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
