from slowapi import Limiter
from slowapi.util import get_remote_address

# Rate limiter instance using client remote IP address
limiter = Limiter(key_func=get_remote_address)
