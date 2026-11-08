"""One global controller; constants remain statically reviewable."""
POLICY = {'revision': 9, 'carry_in_admissions': 3, 'carry_in_tokens': 45843, 'max_cumulative_admissions': 9, 'max_new_admissions': 6, 'preventive_cumulative_tokens': 200000, 'operational_tolerance': 700000, 'deadline_seconds': 120}
ANCESTRY = {'closure_sha256': '678dd44b316496fc847fe3b3686a233a2fd40d7afe89fd6e5d1d3132ca04f03d', 'checkpoint_sha256': '6e4ea14fe5a2e4317962ec329409b428c4845e0ed7627dd4c74879bb1904c361', 'predecessor_faults': ['SETUP_CLI_RETURNED_WITHOUT_SETTLED_USAGE'], 'prior_ancestry': {'closure_sha256': '8193dc80dba36296666223a1e29e4170ee233e319b46021037854b8f1dfbf67b', 'checkpoint_sha256': '78026c0b5c6c21524a7d3f41c1e3183c9ec685da313365b6faeaa2f4e0c3db9e', 'predecessor_faults': ['CAMPAIGN_RUNNER_EXCEPTION']}}
from independent_controller import Controller
from legacy_controller import Refused, seal, digest
import legacy_controller
assert POLICY == legacy_controller.POLICY and ANCESTRY == legacy_controller.ANCESTRY
