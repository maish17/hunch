"""Config consistency checks. REAL tests - these pass today and must keep passing.

They catch the mistakes that would otherwise surface as confusing bugs later: a
channel pointing at a component that does not exist, a mode missing a baseline,
an enum in schemas/common.schema.json drifting from the config files, a WARNING
limit set further out than its CRITICAL limit.
"""

import unittest

from p4maint import configs
from schemas.validate import errors, load_schema


class TestChannelSchemaFile(unittest.TestCase):
    def setUp(self):
        self.ch = configs.load_channels()
        self.components = {c["id"]: c for c in self.ch["hierarchy"]["components"]}

    def test_channels_json_matches_its_schema(self):
        self.assertEqual(errors(self.ch, "channels_config"), [])

    def test_channel_names_are_unique(self):
        names = configs.channel_names(self.ch)
        self.assertEqual(len(names), len(set(names)))

    def test_every_channel_points_at_a_real_component_and_matching_subsystem(self):
        for channel in self.ch["channels"]:
            with self.subTest(channel=channel["name"]):
                self.assertIn(channel["component"], self.components)
                self.assertEqual(channel["subsystem"], self.components[channel["component"]]["subsystem"])

    def test_hierarchy_is_a_tree(self):
        """Each component is listed under exactly the subsystem it names."""
        listed = {}
        for sub in self.ch["hierarchy"]["subsystems"]:
            for comp in sub["components"]:
                self.assertNotIn(comp, listed, f"{comp} listed under two subsystems")
                listed[comp] = sub["id"]
        for comp_id, comp in self.components.items():
            self.assertEqual(listed.get(comp_id), comp["subsystem"])

    def test_warning_limits_sit_inside_critical_limits(self):
        for channel in self.ch["channels"]:
            lim = channel["limits"]
            with self.subTest(channel=channel["name"]):
                if lim["warning_high"] is not None and lim["critical_high"] is not None:
                    self.assertLess(lim["warning_high"], lim["critical_high"])
                if lim["warning_low"] is not None and lim["critical_low"] is not None:
                    self.assertGreater(lim["warning_low"], lim["critical_low"])
                if lim["type"] == "relative":
                    for key in ["warning_high", "critical_high"]:
                        if lim[key] is not None:
                            self.assertGreater(lim[key], 0)
                    for key in ["warning_low", "critical_low"]:
                        if lim[key] is not None:
                            self.assertLess(lim[key], 0)

    def test_all_four_faults_are_covered_by_some_channel(self):
        covered = set()
        for channel in self.ch["channels"]:
            covered.update(channel["diagnostic_for"])
        fault_ids = {f["id"] for f in configs.load_faults()["faults"]}
        self.assertEqual(covered, fault_ids)


class TestModes(unittest.TestCase):
    def test_every_mode_has_a_baseline_for_every_per_mode_and_thermal_channel(self):
        ch = configs.load_channels()
        needs_baseline = [c["name"] for c in ch["channels"] if c["baseline_type"] in ("per_mode", "thermal_lag")]
        for mode in configs.load_modes()["modes"]:
            for name in needs_baseline:
                with self.subTest(mode=mode["id"], channel=name):
                    self.assertIn(name, mode["baselines"])

    def test_baselines_only_name_real_channels(self):
        names = set(configs.channel_names(configs.load_channels()))
        for mode in configs.load_modes()["modes"]:
            self.assertTrue(set(mode["baselines"]) <= names, mode["id"])


class TestEnumsMatchConfig(unittest.TestCase):
    """schemas/common.schema.json repeats some ids for validation; they must not drift."""

    def setUp(self):
        self.defs = load_schema("common")["$defs"]

    def test_op_modes(self):
        self.assertEqual(set(self.defs["op_mode"]["enum"]), {m["id"] for m in configs.load_modes()["modes"]})

    def test_robot_states(self):
        sm = configs.load_state_machine()
        self.assertEqual(set(self.defs["robot_status"]["enum"]), set(sm["robot"]["states"]))

    def test_work_order_states(self):
        sm = configs.load_state_machine()
        self.assertEqual(set(self.defs["work_order_status"]["enum"]), set(sm["work_order"]["states"]))

    def test_fault_modes(self):
        fault_ids = {f["id"] for f in configs.load_faults()["faults"]}
        self.assertEqual(set(self.defs["fault_mode"]["enum"]), fault_ids | {"unknown"})

    def test_subsystems(self):
        subs = {s["id"] for s in configs.load_channels()["hierarchy"]["subsystems"]}
        self.assertEqual(set(self.defs["subsystem"]["enum"]), subs)


class TestFaultsAndStateMachine(unittest.TestCase):
    def test_fault_primary_channels_exist_for_every_wheel(self):
        names = set(configs.channel_names(configs.load_channels()))
        for fault in configs.load_faults()["faults"]:
            pattern = fault["primary_channel_pattern"]
            wheels = ["fl", "fr", "rl", "rr"] if "{wheel}" in pattern else [None]
            for wheel in wheels:
                name = pattern.replace("{wheel}", wheel) if wheel else pattern
                self.assertIn(name, names, fault["id"])

    def test_signatures_use_the_vocabulary(self):
        faults = configs.load_faults()
        allowed = set(faults["signature_vocabulary"])
        for fault in faults["faults"]:
            self.assertTrue(set(fault["signature"].values()) <= allowed, fault["id"])

    def test_bearing_wear_and_wheel_drag_differ_only_in_temperature_evidence(self):
        """The central diagnosis case, written into the config on purpose."""
        faults = {f["id"]: f["signature"] for f in configs.load_faults()["faults"]}
        differing = {k for k in faults["bearing_wear"] if faults["bearing_wear"][k] != faults["wheel_drag"][k]}
        self.assertEqual(differing, {"wheel_temp", "thermal_residual"})

    def test_transitions_only_use_known_states(self):
        sm = configs.load_state_machine()
        for machine in ["robot", "work_order"]:
            states = set(sm[machine]["states"])
            for t in sm[machine]["transitions"]:
                self.assertIn(t["from"], states)
                self.assertIn(t["to"], states)
                self.assertNotEqual(t["from"], t["to"])


class TestDetectorAndGeneratorAgreeAtStart(unittest.TestCase):
    """The detector keeps its own copy of physical beliefs (it must not read
    generator.json). They start equal; change one on purpose only to test model mismatch."""

    def test_battery_model_matches(self):
        det = configs.load_detector_params()["battery_model"]
        gen = configs.load_generator_params()["battery"]
        self.assertEqual(det["ocv_table_soc_pct_to_v"], gen["ocv_table_soc_pct_to_v"])
        self.assertEqual(det["r_int_nominal_ohm"], gen["r_int_ohm"])

    def test_thermal_model_matches(self):
        det = configs.load_detector_params()["thermal_model"]
        gen = configs.load_generator_params()
        self.assertEqual(det["r_th_k_per_w"], gen["drive_thermal"]["r_th_k_per_w"])
        self.assertEqual(det["tau_s"], gen["drive_thermal"]["r_th_k_per_w"] * gen["drive_thermal"]["c_th_j_per_k"])
        self.assertEqual(det["r_arm_ohm"], gen["drive_motor"]["r_arm_ohm"])

    def test_batch_length_matches_evaluation_cadence(self):
        batch_s = configs.load_generator_params()["timing"]["batch_s"]
        self.assertEqual(batch_s, configs.load_detector_params()["evaluation"]["cadence_s"])


if __name__ == "__main__":
    unittest.main()
