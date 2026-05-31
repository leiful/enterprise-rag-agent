import sys
import unittest


def main():
    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir=".", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
