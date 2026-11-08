from dataclasses import dataclass


@dataclass
class User:
    name: str
    email: str

    def display_name(self):
        return self.name.strip().title()
