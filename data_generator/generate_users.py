def generate_users(count=1000, seed=42):
    """Neutral test identities, without demographic or preference fields."""
    return [{"id": f"U{i + 1:04d}", "name": f"User {i + 1:04d}"} for i in range(count)]
