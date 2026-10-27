"""Local operator retention task; no source match files are accessed."""
import argparse
from .storage import expire

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--expire',action='store_true',required=True);p.parse_args();expire()
