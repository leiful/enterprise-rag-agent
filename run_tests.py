import sys
import unittest
import argparse
from pathlib import Path


TEST_GROUPS = {
    "fast": [
        "test_ai_agent.py",
        "test_config.py",
        "test_document_parsers.py",
        "test_knowledge_access.py",
        "test_knowledge_metadata.py",
        "test_knowledge_sources.py",
        "test_memory.py",
        "test_preflight_prod_check.py",
        "test_rag_eval_gate.py",
        "test_rag_status.py",
        "test_tools.py",
    ],
    "api": ["test_main_api.py"],
    "database": ["test_database.py", "test_db_utils.py"],
    "vector": ["test_vector_store.py"],
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run backend tests.")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional unittest module, file, class, or test path.",
    )
    parser.add_argument(
        "--group",
        choices=sorted(TEST_GROUPS),
        help="Run a maintained subset: fast, api, database, or vector.",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="Show available test groups and exit.",
    )
    return parser.parse_args()


def load_group_suite(loader, tests_dir, group):
    suite = unittest.TestSuite()
    for pattern in TEST_GROUPS[group]:
        suite.addTests(loader.discover(start_dir=str(tests_dir), pattern=pattern))
    return suite


def main():
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    backend_dir = project_root / "backend"
    tests_dir = backend_dir / "tests"
    sys.path.insert(0, str(backend_dir))

    if args.list_groups:
        for name, patterns in TEST_GROUPS.items():
            print(f"{name}: {', '.join(patterns)}")
        return 0

    loader = unittest.defaultTestLoader
    if args.paths:
        suite = loader.loadTestsFromNames(args.paths)
    elif args.group:
        suite = load_group_suite(loader, tests_dir, args.group)
    else:
        suite = loader.discover(start_dir=str(tests_dir), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
