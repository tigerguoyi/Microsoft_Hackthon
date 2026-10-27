"""Bounded media decoder process, invoked only after upload gates."""
import json
import sys
from .storage import decoder

if __name__ == '__main__':
    print(json.dumps(decoder(sys.argv[1])))
