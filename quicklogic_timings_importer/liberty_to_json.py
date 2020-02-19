#!/usr/bin/env python3

import quicklogic_timings_importer
import argparse
from pathlib import Path
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input",
            help="LIB file containing timings",
            type=Path)
    parser.add_argument(
            "output",
            help="The output JSON file containing LIB timings",
            type=Path)
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=quicklogic_timings_importer.LOGLEVELS)

    args = parser.parse_args()

    quicklogic_timings_importer.SUPPRESSBELOW = args.log_suppress_below

    with open(args.input, 'r') as infile:
        libfile = infile.readlines()

    libfile = ['{\n'] + libfile + ['}']

    timingdict = (quicklogic_timings_importer
                  .LibertyToSDFParser.load_timing_info_from_lib(libfile))

    with open(args.output, 'w') as out:
        json.dump(timingdict, out, indent=4)


if __name__ == '__main__':
    main()
