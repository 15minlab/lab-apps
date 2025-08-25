import random

def get_random_boolean():
  """
  Returns a random boolean value (True or False).
  """
  return random.choice([True, False])

# Example usage:
random_value = get_random_boolean()
print(random_value)