"""Check the data a player sends when creating a hunt. Owner: B.

Plain Python with no Flask and no database, so it is easy to test.
"""

from treasure_input import parse_number

MAX_NAME_LENGTH = 60
MAX_DESCRIPTION_LENGTH = 200
MIN_CAPACITY = 1
MAX_CAPACITY = 50
DEFAULT_CAPACITY = 10


def parse_capacity(value):
    """Return a whole number of players between MIN_CAPACITY and MAX_CAPACITY."""
    number = parse_number(value, "capacity", MIN_CAPACITY, MAX_CAPACITY)
    if not number.is_integer():
        raise ValueError("capacity must be a whole number")
    return int(number)


def parse_hunt(data):
    """Return {"name", "description", "capacity"} ready for the Hunt table.

    Raises ValueError with a message a player can read if anything is wrong.
    """
    if not isinstance(data, dict):
        raise ValueError("Send the hunt as JSON or form data")

    name = data.get("name") or ""
    description = data.get("description") or ""
    if not isinstance(name, str) or not isinstance(description, str):
        raise ValueError("name and description must be text")
    name, description = name.strip(), description.strip()
    if not name:
        raise ValueError("name is required")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"name must be at most {MAX_NAME_LENGTH} characters")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise ValueError(f"description must be at most {MAX_DESCRIPTION_LENGTH} characters")

    capacity = data.get("capacity")
    if capacity is None or (isinstance(capacity, str) and not capacity.strip()):
        capacity = DEFAULT_CAPACITY  # optional: the form may leave it empty

    return {"name": name, "description": description, "capacity": parse_capacity(capacity)}
