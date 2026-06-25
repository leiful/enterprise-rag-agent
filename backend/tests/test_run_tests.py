import unittest
from unittest.mock import patch

import run_tests


class RunTestsCliTests(unittest.TestCase):
    def test_groups_argument_runs_requested_groups_in_order(self):
        with patch.object(run_tests, "parse_args") as parse_args:
            parse_args.return_value = run_tests.argparse.Namespace(
                paths=[],
                group=None,
                groups=["database", "vector", "api"],
                list_groups=False,
            )
            with patch.object(run_tests.unittest.TextTestRunner, "run") as run:
                run.return_value.wasSuccessful.return_value = True
                with patch.object(run_tests, "load_group_suite") as load_group_suite:
                    load_group_suite.side_effect = lambda loader, tests_dir, group: group

                    exit_code = run_tests.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            [call.args[2] for call in load_group_suite.call_args_list],
            ["database", "vector", "api"],
        )
        self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
