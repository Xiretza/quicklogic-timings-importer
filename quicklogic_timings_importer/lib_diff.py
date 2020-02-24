import difflib
import argparse
from pathlib import Path
import re
import sys
import diff_match_patch
import log_printer


def junk_characters(a):
    if a in ' \t\"':
        return True
    else:
        return False


def clean_lines(
        lines,
        remove_comments=True,
        move_entry_to_newline=True,
        remove_quotes=True,
        remove_whitespaces=True,
        unify_numbers=True,
        remove_line_breaks=True):
    '''Performs file preprocessing before running diff.

    It is used for removing all semantically irrelevant characters that may
    blur the real differences between two files. By default it converts all
    tabs to single whitespace.

    Parameters
    ----------

    Returns
    -------
    '''
    # join all lines into single string
    fullfile = '\n'.join(lines)

    if remove_comments:
        # remove comments (C/C++ style)
        fullfile = re.sub(r'(?:\/\*(.*?)\*\/)|(?:\/\/(.*?))', '',
                          fullfile, flags=re.DOTALL)

        # remove comments (Python style)
        fullfile = re.sub(r'#[^\n]*\n', '', fullfile, flags=re.DOTALL)

    # replace all tabs with single space
    fullfile = fullfile.replace('\t', ' ')

    if move_entry_to_newline:
        # move non-whitespace content after } to new line
        fullfile = re.sub(r'}\s*(?!\n)', '}\n', fullfile, flags=re.DOTALL)

    if remove_quotes:
        # remove quotes
        fullfile = fullfile.replace('"', '')

    if remove_whitespaces:
        # remove whitespaces
        fullfile = fullfile.replace(' ', '')

    if remove_line_breaks:
        fullfile = re.sub(r'\\\s*\n', '', fullfile, flags=re.DOTALL)

    # split single string into lines
    lines = fullfile.split('\n')
    fullfile = ''

    if remove_whitespaces:
        # remove empty lines and trailing whitespaces
        lines = [line.rstrip() for line in lines if line.strip()]

    if unify_numbers:
        floats = re.compile(
                r'(?P<number>[-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)')
        for i in range(len(lines)):
            lines[i] = floats.sub(
                    lambda m: str(float(m.group('number'))),
                    lines[i])

    # add newlines at the end of each line
    lines = [line + '\n' for line in lines]

    return lines


def diff_files(
        in1,
        in2,
        print_diff=True,
        html_path=None,
        html_row_width=100,
        return_similarity=False,
        similarity_method='quick'):
    if html_path:
        diff = difflib.HtmlDiff(
                charjunk=junk_characters,
                tabsize=4,
                wrapcolumn=html_row_width)
        with open(html_path, 'w') as outfile:
            result = diff.make_file(in1, in2, context=True)
            outfile.write(result)
    if print_diff:
        diff = difflib.ndiff(
                in1,
                in2,
                charjunk=junk_characters)
        print(''.join(diff))
    if return_similarity:
        seqmatcher = difflib.SequenceMatcher(None, ''.join(in1), ''.join(in2))
        if similarity_method == 'normal':
            return seqmatcher.ratio()
        elif similarity_method == 'quick':
            return seqmatcher.quick_ratio()
        elif similarity_method == 'real_quick':
            return seqmatcher.real_quick_ratio()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
            "input1",
            help="First Liberty file",
            type=Path)
    parser.add_argument(
            "input2",
            help="Second Liberty file",
            type=Path)
    parser.add_argument(
            "--output-html",
            help="Generate side-by-side diff to HTML file with given path",
            type=Path)
    parser.add_argument(
            "--html-row-width",
            help="Row width of the HTML side-by-side column",
            default=100,
            type=int)
    parser.add_argument(
            "--not-remove-comments",
            help="Do not remove comments before comparing files",
            action="store_true")
    parser.add_argument(
            "--not-move-entry-to-newline",
            help="Do not move content after closing bracket '}' to newline",
            action="store_true")
    parser.add_argument(
            "--not-remove-quotes",
            help="Do not remove quotes '\"' from documents before comparison",
            action="store_true")
    parser.add_argument(
            "--not-remove-whitespaces",
            help="Do not remove comments before comparing files",
            action="store_true")
    parser.add_argument(
            "--not-remove-line-breaks",
            help=r"Do not remove line breaks '\\n'",
            action="store_true")
    parser.add_argument(
            "--not-unify-numbers",
            help="Do not convert numbers in both files to unified form",
            action="store_true")
    parser.add_argument(
            "--print-diff",
            help="Print the diff to stdout",
            action="store_true")
    parser.add_argument(
            "--compute-similarity",
            help="Computes and prints the similarity between files (0-1)",
            action="store_true")
    parser.add_argument(
            "--similarity-method",
            help="The method used for computing similarity",
            type=str,
            default='quick',
            choices=['normal', 'quick', 'real_quick'])
    parser.add_argument(
            "--log-suppress-below",
            help="The mininal not suppressed log level",
            type=str,
            default="ERROR",
            choices=log_printer.LOGLEVELS)

    args = parser.parse_args()

    log_printer.SUPPRESSBELOW = args.log_suppress_below

    with open(args.input1, 'r') as input1:
        in1 = input1.readlines()
    with open(args.input2, 'r') as input2:
        in2 = input2.readlines()

    in1 = clean_lines(
            in1,
            not args.not_remove_comments,
            not args.not_move_entry_to_newline,
            not args.not_remove_quotes,
            not args.not_remove_whitespaces,
            not args.not_unify_numbers,
            not args.not_remove_line_breaks)

    in2 = clean_lines(
            in2,
            not args.not_remove_comments,
            not args.not_move_entry_to_newline,
            not args.not_remove_quotes,
            not args.not_remove_whitespaces,
            not args.not_unify_numbers,
            not args.not_remove_line_breaks)

    similarity = diff_files(
            in1,
            in2,
            args.print_diff,
            args.output_html,
            args.html_row_width,
            args.compute_similarity,
            args.similarity_method)
    if args.compute_similarity:
        print('Similarity between documents:  {}'.format(similarity))
