`parse_bool` currently treats every non-empty string as True. Support true/false/1/0/yes/no/on/off case-insensitively, and raise ValueError for anything else.
