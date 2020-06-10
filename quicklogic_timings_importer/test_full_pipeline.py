#!/usr/bin/env python3

from .liberty_to_json import LibertyToJSONParser
from .json_to_liberty import JSONToLibertyWriter
import json
from . import log_printer
from pathlib import Path
import argparse
from .lib_diff import clean_lines, diff_files
import sys


def similarity_float(x):
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError('{} is not float'.format(x))
    if x < 0.0 or x > 1.0:
        raise argparse.ArgumentTypeError('{} not in range [0,1]'.format(x))
    return x


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "inputlist",
            help="File containing list of absolute " +
                 "paths to test Liberty files",
            type=Path)
    parser.add_argument(
            "--output-json-root-dir",
            help="Optional directory to store generated JSON files",
            type=Path)
    parser.add_argument(
            "--output-lib-root-dir",
            help="Optional directory to store generated Liberty files",
            type=Path)
    parser.add_argument(
            "--print-lib-diff",
            help="If present, the diff for Liberty files is printed on fail",
            action='store_true')
    parser.add_argument(
            "--lib-similarity-threshold",
            help="Float value representing similarity threshold below " +
            "which files are no longer considered to be similar",
            type=similarity_float,
            default=0.999,
            )
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=log_printer.LOGLEVELS)

    args = parser.parse_args()

    log_printer.SUPPRESSBELOW = args.log_suppress_below

    with open(args.inputlist, 'r') as liblistfile:
        liblist = [Path(path.strip()) for path in liblistfile.readlines()]

    liblist = sorted(liblist)

    numfailed = {
            "lib-to-json": 0,
            "json-to-lib": 0,
            "newlib-to-json": 0,
            "comparison-json": 0,
            "comparison-lib": 0}

    numskipped = {
            "lib-to-json": 0,
            "json-to-lib": 0,
            "newlib-to-json": 0,
            "comparison-json": 0,
            "comparison-lib": 0}

    filenum = 0
    numfiles = len(liblist)

    procline = '[{:04d}/{:04d},lj={:04d},jn={:04d},nj={:04d},jj={:04d},ll={:04d}] Processing {}'  # noqa: E501

    for libname in liblist:
        filenum += 1
        namecore = Path(str(libname.parent)[1:]) / libname.stem
        print(procline.format(
            filenum,
            numfiles,
            numfailed['lib-to-json'],
            numfailed['json-to-lib'],
            numfailed['newlib-to-json'],
            numfailed['comparison-json'],
            numfailed['comparison-lib'],
            libname))
        with open(libname, 'r') as libfile:
            inputliberty = libfile.readlines()
        inputliberty = ['{\n'] + inputliberty + ['}']
        jsondict = {}
        # try parsing LIB file
        try:
            jsondict = LibertyToJSONParser.load_timing_info_from_lib(
                    inputliberty)
            if args.output_json_root_dir:
                targetfile = Path(
                        str(args.output_json_root_dir / namecore) + '.json')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    json.dump(jsondict, out, indent=2)
            log_printer.log('INFO', ' lib-to-json: {}'.format(libname))
        except Exception as ex:
            log_printer.log(
                    'ERROR', 'lib-to-json:  {} | {}'.format(
                        type(ex).__name__,
                        libname))
            numfailed['lib-to-json'] += 1
            numskipped['json-to-lib'] += 1
            numskipped['newlib-to-json'] += 1
            numskipped['comparison-json'] += 1
            numskipped['comparison-lib'] += 1
            continue
        # try converting it back to LIB
        liblines = []
        try:
            liblines = JSONToLibertyWriter.convert_json_to_liberty(jsondict)
            if args.output_lib_root_dir:
                targetfile = Path(
                        str(args.output_lib_root_dir / namecore) + '.lib')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    out.write('\n'.join(liblines))
            log_printer.log('INFO', ' json-to-lib: {}'.format(libname))
        except Exception as ex:
            log_printer.log(
                    'ERROR', 'json-to-lib:  {} | {}'.format(
                        type(ex).__name__, libname))
            numfailed['json-to-lib'] += 1
            numskipped['newlib-to-json'] += 1
            numskipped['comparison-json'] += 1
            numskipped['comparison-lib'] += 1
            continue
        # convert generated LIB back to JSON and compare the results
        liblines = ['{\n'] + liblines + ['}']
        newjson = {}
        try:
            newjson = LibertyToJSONParser.load_timing_info_from_lib(liblines)
            if args.output_json_root_dir:
                targetfile = Path(
                        str(args.output_json_root_dir / namecore) +
                        '-new.json')
                targetfile.parent.mkdir(parents=True, exist_ok=True)
                with open(targetfile, 'w') as out:
                    json.dump(newjson, out, indent=2)
            log_printer.log('INFO', ' newlib-to-json: {}'.format(libname))
        except Exception as ex:
            log_printer.log('ERROR', 'newlib-to-json:  {} | {}'.format(
                type(ex).__name__, libname))
            numfailed['newlib-to-json'] += 1
            numskipped['comparison-json'] += 1
            numskipped['comparison-lib'] += 1
            continue
        if jsondict == newjson:
            log_printer.log('INFO', ' comparison-json: {}'.format(libname))
        else:
            log_printer.log('ERROR', 'comparison-json:  {} | {}'.format(
                'jsondict != newjson', libname))
            with open('{}_wrong.json'.format(filenum), 'w') as wrong:
                json.dump(newjson, wrong, indent=2)
            numfailed['comparison-json'] += 1
        in1 = clean_lines(inputliberty[1:-1])
        in2 = clean_lines(liblines[1:-1])
        similarity = diff_files(
                in1,
                in2,
                print_diff=False,
                return_similarity=True,
                similarity_method='quick')
        if similarity > args.lib_similarity_threshold:
            log_printer.log('INFO', ' comparison-lib: {} | {}'.format(
                similarity, libname))
        else:
            log_printer.log('ERROR', 'comparison-lib:  {} | {}'.format(
                similarity, libname))
            numfailed['comparison-lib'] += 1
            if args.print_lib_diff:
                diff_files(in1, in2, print_diff=True)

    isfailed = False
    for key in numfailed.keys():
        if numfailed[key] > 0:
            isfailed = True
        print('{}: {} out of {} failed ({}% succeded, {} were skipped)'.format(
            key,
            numfailed[key],
            numfiles,
            100.0 * (numfiles - numfailed[key]) / numfiles, numskipped[key]))

    if isfailed:
        sys.exit(1)


if __name__ == '__main__':
    main()
