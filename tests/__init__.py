"""All the automatic tests. Run them from the project folder with:  python -m unittest

(This file makes the folder a package, so unittest finds the tests in it.)
"""

import os

# The project folder (one level up). Tests that build their own Flask(...) app pass it as
# root_path, so Flask still finds templates/ and static/ now that the tests live in tests/.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
