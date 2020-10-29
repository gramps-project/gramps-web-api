"""Test utility functions."""

from typing import Dict, List


def check_empty(object1, object2):
    """Check keys for empty values in first object no longer exist in second."""
    for key in object1:
        if object1[key] in [[], "", None, {}]:
            assert key not in object2
        else:
            if isinstance(object1[key], Dict):
                check_empty(object1[key], object2[key])
            if isinstance(object1[key], List):
                for item in object1:
                    if isinstance(item, List) or isinstance(item, Dict):
                        check_empty(item, object2[object1.index(item)])
