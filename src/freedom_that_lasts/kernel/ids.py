"""
ID generation using UUIDv7 (time-ordered UUIDs)

UUIDv7 provides sortable, globally unique identifiers with embedded timestamps,
making event logs naturally ordered and efficient for range queries.

Fun fact: UUID stands for Universally Unique Identifier - there are 2^122 possible
UUIDv7 values, meaning you'd need to generate a trillion IDs per second for
85 years to have a 50% chance of a collision!
"""

import secrets
import time
from typing import Protocol


class IdFactory(Protocol):
    """Protocol for ID generation strategies"""

    def generate(self) -> str:
        """Generate a new unique ID"""
        ...


def generate_id() -> str:
    """
    Generate a UUIDv7-like identifier (time-ordered UUID)

    Format: 8-4-4-4-12 hex characters (36 chars with hyphens)
    First 48 bits: Unix timestamp in milliseconds
    Next 12 bits: Random
    Remaining 62 bits: Random

    Returns:
        Sortable UUID string (e.g., "01908e9a-3b87-7000-8000-123456789abc")
    """
    # Get current timestamp in milliseconds
    timestamp_ms = int(time.time() * 1000)

    # Extract 48 bits of timestamp
    timestamp_48 = timestamp_ms & 0xFFFFFFFFFFFF

    # Generate random bits
    rand_12 = secrets.randbits(12)
    rand_62 = secrets.randbits(62)

    # Construct UUIDv7-like format
    # Version 7 (0111) in bits 48-51
    # Variant (10) in bits 64-65
    time_high = (timestamp_48 >> 32) & 0xFFFF
    time_mid = (timestamp_48 >> 16) & 0xFFFF
    time_low_and_version = ((timestamp_48 & 0xFFFF) << 16) | (0x7000 | rand_12)
    clock_seq_and_variant = 0x8000 | ((rand_62 >> 48) & 0x3FFF)
    node = rand_62 & 0xFFFFFFFFFFFF

    # Format as UUID string
    uuid_str = (
        f"{time_high:04x}{time_mid:04x}-"
        f"{(time_low_and_version >> 16) & 0xFFFF:04x}-"
        f"{time_low_and_version & 0xFFFF:04x}-"
        f"{clock_seq_and_variant:04x}-"
        f"{node:012x}"
    )

    return uuid_str


class DefaultIdFactory:
    """Default ID factory using UUIDv7-like generation"""

    def generate(self) -> str:
        return generate_id()


# Global default factory
default_id_factory = DefaultIdFactory()
