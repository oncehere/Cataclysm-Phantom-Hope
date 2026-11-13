import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKY = ROOT / 'data/mods/Sky_Island'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def entry(path, key, value):
    return next(x for x in load(path) if x.get(key) == value)

def walk(value):
    yield value
    if isinstance(value, dict):
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)

class ModAdaptationTest(unittest.TestCase):
    def test_upgrade_state_transitions(self):
        topics = load(SKY / 'dialog_statue.json')
        responses = [x for topic in topics for x in topic.get('responses', [])]
        challenge = next(x for x in responses if x.get('text') == 'Challenge Mode')
        clair = next(x for x in responses if x.get('text') == 'Upgrade: Scouting Clairvoyance 2')
        self.assertIn({'math': ['challenge_mode_available < 1']}, challenge['condition']['and'])
        self.assertIn({'math': ['scoutingclairvoyancetime == 20']}, clair['condition']['and'])
        self.assertNotIn({'math': ['scouting_clairvoyance == 1']}, clair['condition']['and'])
        challenge_mission = entry(SKY / 'missions/raid_upgrades/challenge.json', 'id', 'SKYISLAND_UPGRADE_challenge_mode')
        self.assertIn({'math': ['challenge_mode_available = 1']}, list(walk(challenge_mission)))
        scouting = load(SKY / 'missions/raid_upgrades/scouting.json')
        self.assertIn({'math': ['scoutingclairvoyancetime = 20']}, list(walk(scouting)))
        self.assertIn({'math': ['scoutingclairvoyancetime = 60']}, list(walk(scouting)))

    def test_merchant_initializes_target_before_update(self):
        path = SKY / 'effectoncondition/island_upgrades.json'
        build = entry(path, 'id', 'EOC_skyisland_build_merchant_stall')
        self.assertEqual(build['effect'][0], {'run_eocs': 'EOC_memorize_island'})
        self.assertEqual(build['effect'][1]['target_var'], {'global_val': 'OM_island_n'})
        memorize = entry(path, 'id', 'EOC_memorize_island')
        self.assertIn({'global_val': 'OM_island_n'}, list(walk(memorize)))
        self.assertIn({'run_eocs': 'EOC_skyisland_build_merchant_stall'}, list(walk(load(SKY / 'missions/island_upgrades/merchants.json'))))
        self.assertNotIn("wipe their inventory", (SKY / 'dialog_statue.json').read_text(encoding='utf-8'))

    def test_interaction_and_balthazar(self):
        base = entry(SKY / 'effectoncondition/items_spells.json', 'id', 'ter_close_tears_and_portals')
        inter = entry(SKY / 'mod_interactions/mindovermatter/ter_transform.json', 'id', 'ter_close_tears_and_portals')
        self.assertEqual(base['trap'], inter['trap'])
        self.assertEqual(inter['field'][0]['valid_field'], ['fd_fatigue', 'fd_tear_in_reality_temporary'])
        disabled = load(SKY / 'effectoncondition/disabled.json')
        self.assertEqual({x['id'] for x in disabled}, {'EOC_START_BALTHAZAR_COUNTERS', 'EOC_DAILY_BALTHAZAR_POWER'})
        self.assertTrue(all(x['effect'] == [] for x in disabled))
        core = entry(ROOT / 'data/json/effects_on_condition/npc_eocs/balthazar_fac_eocs.json', 'id', 'EOC_BALTHAZAR_CHECK_PROGRESS')
        self.assertIn({'current_dimension': 'default'}, core['condition']['and'])
        self.assertIn({'math': ['balthazar_destroyed != 1']}, core['condition']['and'])

    def test_recipes_preserve_core_and_enable_autolearn(self):
        for name, core_path, mod_path in [
            ('mask_filter', 'data/json/recipes/armor/head.json', 'data/mods/innawood/recipes/armor/head.json'),
            ('churn', 'data/json/recipes/tools/tool.json', 'data/mods/innawood/recipes/tool.json'),
        ]:
            with self.subTest(recipe=name):
                core = entry(ROOT / core_path, 'result', name)
                mod = entry(ROOT / mod_path, 'result', name)
                self.assertTrue(mod.pop('autolearn'))
                self.assertEqual(mod, core)

if __name__ == '__main__':
    unittest.main()
