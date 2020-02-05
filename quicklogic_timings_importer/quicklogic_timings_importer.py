# import sdf_timing
from pathlib import Path
import argparse
import re
import json


def join_duplicate_keys(ordered_pairs):
    d = {}
    for k, v in ordered_pairs:
        if k in d:
            if type(d[k]) == list:
                d[k].append(v)
            else:
                d[k] = [d[k], v]
        else:
            d[k] = v
    return d


def load_timing_info_from_lib(inputfilename: str) -> (str, dict):
    '''TODO
    '''

    # REGEX defining the dictionary name in LIB file, i.e. "pin ( QAI )",
    # "pin(FBIO[22])" or "timing()"
    structdecl = re.compile(r'^(?P<indent>\s*)(?P<type>[A-Za-z]+)\s*\(\s*\"?(?P<name>[A-Za-z0-9_]*(\[[0-9]+\])?)\"?\s*\)')  # noqa: E501

    # REGEX defining typical variable name, which is any variable starting with
    # alphabetic character, followed by [A-Za-z_0-9] characters, and not within
    # quotes
    vardecl = re.compile(r'(?P<variable>(?<!\")[a-zA-Z_][a-zA-Z_0-9]*(\[[0-9]+\])?(?![^\:]*\"))')  # noqa: E501

    # Load LIB file
    with open(inputfilename, 'r') as infile:
        libfile = infile.readlines()

    # remove empty lines
    libfile = [line.rstrip() for line in libfile if line.strip()]

    # remove comments (C/C++ style)
    fullfile = '\n'.join(libfile)
    fullfile = re.sub(r'(?:\/\*(.*?)\*\/)|(?:\/\/(.*?))', '',
                      fullfile, flags=re.DOTALL)
    libfile = fullfile.split('\n')
    fullfile = ''

    # extract file header
    header = libfile.pop(0)

    # remove PORT DELAY root name
    libfile[0] = '{'

    # replace semicolons with commas
    libfile = [line.replace(';', ',') for line in libfile]

    # remove parenthesis from struct names
    for i, line in enumerate(libfile):
        libfile[i] = structdecl.sub(r'\g<indent>\g<type>\g<name> :', line)

    # wrap all text in quotes
    for i, line in enumerate(libfile):
        libfile[i] = vardecl.sub(r'"\g<variable>"', line)

    # add colons after closing braces
    for i, line in enumerate(libfile):
        libfile[i] = line.replace("}", "},")

    # remove colons before closing braces
    fullfile = '\n'.join(libfile)
    fullfile = re.sub(r',(?P<tmp>\s*})', r'\g<tmp>', fullfile, flags=re.DOTALL)
    libfile = fullfile.split('\n')
    fullfile = ''

    # remove the colon in the end of file
    libfile[-1] = re.sub(r',\s*', '', libfile[-1])

    timingdict = json.loads('\n'.join(libfile),
                            object_pairs_hook=join_duplicate_keys)

    return header, timingdict


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input",
            help="LIB file containing timings from EOS-3",
            type=Path)
    parser.add_argument(
            "output",
            help="The output SDF file containing timing",
            type=Path)

    args = parser.parse_args()

    print("Processing {}".format(args.input))
    _, timingdict = load_timing_info_from_lib(args.input)

    with open(args.output, 'w') as out:
        json.dump(timingdict, out, indent=4)
