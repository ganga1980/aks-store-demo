"""
Session Customer Generator

Generates random customer identity (ID, name, email) for each chat session.
This simulates different customers interacting with the customer agent.
"""

import random
import uuid
from dataclasses import dataclass
from typing import Optional

# Common first names
FIRST_NAMES = [
    "Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Sophia", "Mason",
    "Isabella", "William", "Mia", "James", "Charlotte", "Oliver", "Amelia",
    "Benjamin", "Harper", "Elijah", "Evelyn", "Lucas", "Abigail", "Henry",
    "Emily", "Alexander", "Elizabeth", "Michael", "Sofia", "Daniel", "Avery",
    "Matthew", "Ella", "Aiden", "Scarlett", "Joseph", "Grace", "Jackson",
    "Chloe", "Sebastian", "Victoria", "David", "Riley", "Carter", "Aria",
    "Wyatt", "Lily", "Jayden", "Aurora", "John", "Zoey", "Owen", "Nora",
]

# Common last names
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
    "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green",
    "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell",
    "Carter", "Roberts", "Chen", "Kim", "Patel", "Singh", "Kumar",
]

# Email domains
EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "protonmail.com", "aol.com", "mail.com", "example.com", "test.com",
]


@dataclass
class SessionCustomer:
    """
    Represents a customer for the current session.

    Attributes:
        customer_id: Unique customer identifier (UUID)
        first_name: Customer's first name
        last_name: Customer's last name
        email: Customer's email address
        status: Customer status (new, active, returning)
    """
    customer_id: str
    first_name: str
    last_name: str
    email: str
    status: str = "active"

    @property
    def full_name(self) -> str:
        """Get customer's full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        """Get customer's display name (first name only)."""
        return self.first_name

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "customer_id": self.customer_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "status": self.status,
        }


def generate_session_customer(
    customer_id: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
) -> SessionCustomer:
    """
    Generate a random customer identity for a session.

    Args:
        customer_id: Override customer ID (default: generated UUID)
        first_name: Override first name (default: random)
        last_name: Override last name (default: random)
        email: Override email (default: generated from name)

    Returns:
        SessionCustomer with generated or provided details
    """
    # Generate customer ID if not provided
    if customer_id is None:
        customer_id = f"cust_{uuid.uuid4().hex[:12]}"

    # Pick random names if not provided
    if first_name is None:
        first_name = random.choice(FIRST_NAMES)
    if last_name is None:
        last_name = random.choice(LAST_NAMES)

    # Generate email if not provided
    if email is None:
        domain = random.choice(EMAIL_DOMAINS)
        # Create email variants: firstname.lastname, firstnamelastname, firstname+random
        email_variants = [
            f"{first_name.lower()}.{last_name.lower()}@{domain}",
            f"{first_name.lower()}{last_name.lower()}@{domain}",
            f"{first_name.lower()}{random.randint(1, 999)}@{domain}",
        ]
        email = random.choice(email_variants)

    # Randomly assign customer status
    status_weights = [("new", 0.3), ("active", 0.5), ("returning", 0.2)]
    status = random.choices(
        [s[0] for s in status_weights],
        weights=[s[1] for s in status_weights]
    )[0]

    return SessionCustomer(
        customer_id=customer_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        status=status,
    )


# Thread-local storage for session customer context
_session_customer: Optional[SessionCustomer] = None


def set_session_customer(customer: SessionCustomer) -> None:
    """Set the current session's customer context."""
    global _session_customer
    _session_customer = customer


def get_session_customer() -> Optional[SessionCustomer]:
    """Get the current session's customer context."""
    return _session_customer


def clear_session_customer() -> None:
    """Clear the current session's customer context."""
    global _session_customer
    _session_customer = None
