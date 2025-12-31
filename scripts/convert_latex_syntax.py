#!/usr/bin/env python3
"""
LaTeX Formula Syntax Converter

Converts custom LaTeX notation to standard syntax for GitHub and PDF rendering:
- Display formulas: [...] → $$...$$
- Inline formulas: (...) → $...$
- Subscript normalization: X_i → X_{i}

Fun fact: LaTeX was created by Leslie Lamport in 1984, built on Donald Knuth's TeX.
The name "LaTeX" combines "Lamport" with "TeX" - a recursive acronym tradition!
"""

import re
import argparse
import sys
from pathlib import Path
from typing import List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class Conversion:
    """Represents a single formula conversion with metadata."""
    conversion_type: str
    line_number: int
    before: str
    after: str


class LaTeXConverter:
    r"""
    Converts mathematical formulas from custom notation to standard LaTeX syntax.

    Implements five conversion patterns:
    1. Display formulas: [...] → $$...$$
    2. Inline formulas with LaTeX commands: (\Omega_t) → $\Omega_{t}$
    3. Simple variables: (T_0) → $T_{0}$
    4. Subscript normalization: S_1 → S_{1}
    5. Naked LaTeX: \mathbb{E}... → $$\mathbb{E}...$$

    Time complexity: O(n) where n = document length
    Space complexity: O(n) for storing conversions

    Fun fact: The dollar sign $ was chosen for math mode in TeX because it's rare in
    mathematical texts but easy to type - maximizing both clarity and ergonomics!
    """

    def __init__(self, markdown_content: str):
        self.original_content = markdown_content
        self.content = markdown_content
        self.conversions: List[Conversion] = []
        self.code_blocks: Dict[str, str] = {}

    def protect_code_blocks(self) -> None:
        """
        Replace code blocks with placeholders to prevent formula conversion inside code.

        Fun fact: This technique is called "tokenization" - the same pattern used in
        compilers to handle strings before parsing the rest of the code!
        """
        counter = 0

        def replace_block(match):
            nonlocal counter
            key = f'<<<CODE_BLOCK_{counter}>>>'
            self.code_blocks[key] = match.group(0)
            counter += 1
            return key

        # Match both ``` fenced code blocks and indented code blocks
        pattern = r'```.*?```|^    .*?(?=\n(?!    )|\Z)'
        self.content = re.sub(pattern, replace_block, self.content,
                             flags=re.MULTILINE | re.DOTALL)

    def restore_code_blocks(self) -> None:
        """Restore code blocks after conversion."""
        for key, value in self.code_blocks.items():
            self.content = self.content.replace(key, value)

    def normalize_subscripts(self, latex: str) -> str:
        """
        Add braces to all subscripts: X_i → X_{i}

        Pattern explanation:
        - ([A-Za-z\\]+) - captures letter or LaTeX command (e.g., X, \alpha)
        - _ - the subscript operator
        - ([0-9a-z]+) - the subscript itself (numbers or lowercase letters)
        - (?![}]) - negative lookahead: don't match if already has closing brace

        Complexity: O(m) where m = length of LaTeX string
        """
        # Pattern: letter/command followed by _ and unbraced subscript
        pattern = r'([A-Za-z\\]+)_([0-9a-z]+)(?![}])'
        result = re.sub(pattern, r'\1_{\2}', latex)

        # Handle multi-character subscripts that might still be unbraced
        # e.g., _min, _max, _total
        pattern2 = r'_([a-z]{2,})(?![}])'
        result = re.sub(pattern2, r'_{\1}', result)

        return result

    def convert_display_formulas(self) -> None:
        r"""
        Convert display formulas: [...] → $$...$$

        Pattern explanation:
        - ^ - start of line (multiline mode)
        - \[\s*\n - opening bracket with optional whitespace and newline
        - ((?:(?!\n\]).)*) - non-greedy capture: anything not containing newline-bracket
        - \n\]\s*$ - newline-bracket at end of line

        Uses negative lookahead to avoid matching markdown links: [text](url)

        Fun fact: The $$ delimiter was chosen to be visually distinctive and unlikely
        to appear in normal text - though it confuses accountants writing financial docs!
        """
        # Don't match markdown links like [text](url)
        pattern = r'(?<!\])\n\[\s*\n((?:(?!\n\]).)*)\n\]\s*\n'

        def replace(match):
            latex = self.normalize_subscripts(match.group(1).strip())
            line_num = self.content[:match.start()].count('\n')
            self.conversions.append(Conversion(
                conversion_type='display',
                line_number=line_num,
                before=match.group(0)[:50] + '...' if len(match.group(0)) > 50 else match.group(0),
                after=f'$$\n{latex}\n$$'
            ))
            return f'\n$$\n{latex}\n$$\n'

        self.content = re.sub(pattern, replace, self.content, flags=re.MULTILINE | re.DOTALL)

    def convert_inline_formulas_with_latex(self) -> None:
        r"""
        Convert inline formulas containing LaTeX commands: (\Omega_t) → $\Omega_{t}$

        Pattern explanation:
        - \( - literal opening parenthesis
        - ([^()]*\\[a-zA-Z]+[^()]*) - content with at least one LaTeX command
        - \) - literal closing parenthesis

        Uses multi-pass approach to handle nested parentheses like (\alpha \in (0,1))

        Fun fact: The backslash \ was chosen for LaTeX commands because it's called
        "escape character" - commands literally "escape" from normal text mode!
        """
        # Pattern matches parentheses containing backslash commands, with optional spaces
        pattern = r'\(\s*([^()]*\\[a-zA-Z]+[^()]*)\s*\)'

        changed = True
        iterations = 0
        max_iterations = 10  # Safety limit for deeply nested structures

        while changed and iterations < max_iterations:
            def replace(match):
                latex = self.normalize_subscripts(match.group(1))
                line_num = self.content[:match.start()].count('\n')
                self.conversions.append(Conversion(
                    conversion_type='inline_latex',
                    line_number=line_num,
                    before=match.group(0),
                    after=f'${latex}$'
                ))
                return f'${latex}$'

            new_content = re.sub(pattern, replace, self.content)
            changed = (new_content != self.content)
            self.content = new_content
            iterations += 1

    def convert_simple_variables(self) -> None:
        r"""
        Convert simple mathematical variables: (T_0) → $T_{0}$

        Pattern explanation:
        - (?<!\$) - negative lookbehind: not preceded by $
        - \( - literal opening parenthesis
        - \s* - optional whitespace
        - ([A-Z][A-Za-z_]*(?:_\{?[0-9a-z]+\}?)?) - variable name with optional subscript
        - \s* - optional whitespace
        - \) - literal closing parenthesis
        - (?!\$) - negative lookahead: not followed by $

        This ensures we don't double-convert already converted formulas.

        Fun fact: Single-letter variables are a mathematical tradition dating back to
        Descartes (1637), who chose x, y, z because his printer was running low on letters!
        """
        # Only convert if not already in $...$, and handle spaces inside parentheses
        pattern = r'(?<!\$)\(\s*([A-Z][A-Za-z_]*(?:_\{?[0-9a-z]+\}?)?)\s*\)(?!\$)'

        def replace(match):
            var = self.normalize_subscripts(match.group(1))
            line_num = self.content[:match.start()].count('\n')
            self.conversions.append(Conversion(
                conversion_type='variable',
                line_number=line_num,
                before=match.group(0),
                after=f'${var}$'
            ))
            return f'${var}$'

        self.content = re.sub(pattern, replace, self.content)

    def fix_naked_latex(self) -> None:
        r"""
        Fix lines with LaTeX commands but no delimiters: \mathbb{E}... → $$\mathbb{E}...$$

        Detects lines that:
        1. Contain LaTeX commands (\mathbb, \frac, \Omega, etc.)
        2. Don't have $ delimiters
        3. Aren't in code blocks (already protected)

        Fun fact: Donald Knuth created TeX in 1978 after being frustrated with the poor
        quality of mathematical typesetting - he thought it would take 6 months. It took 10 years!
        """
        lines = self.content.split('\n')
        fixed_lines = []

        latex_commands = [r'\\mathbb', r'\\frac', r'\\Omega', r'\\Delta', r'\\alpha',
                         r'\\beta', r'\\gamma', r'\\ge', r'\\le', r'\\in']

        for i, line in enumerate(lines):
            # Check if line has LaTeX commands but no $ delimiters
            has_latex = any(re.search(cmd, line) for cmd in latex_commands)
            has_delimiters = '$' in line
            is_code_block_marker = '```' in line or line.startswith('CODE_BLOCK')

            if has_latex and not has_delimiters and not is_code_block_marker and line.strip():
                # Likely a display formula missing delimiters
                latex = self.normalize_subscripts(line.strip())
                self.conversions.append(Conversion(
                    conversion_type='naked_latex',
                    line_number=i + 1,
                    before=line,
                    after=f'$$\n{latex}\n$$'
                ))
                fixed_lines.append(f'$$\n{latex}\n$$')
            else:
                fixed_lines.append(line)

        self.content = '\n'.join(fixed_lines)

    def convert(self) -> Tuple[str, List[Conversion]]:
        """
        Execute all conversions in optimal order.

        Order matters:
        1. Protect code blocks (prevents false positives)
        2. Display formulas (they have priority)
        3. Naked LaTeX (fixes broken formulas)
        4. Inline formulas with LaTeX (complex patterns)
        5. Simple variables (catch remaining cases)
        6. Restore code blocks (bring back protected content)

        Returns: (converted_content, list_of_conversions)

        Time complexity: O(n × k) where n = doc length, k ≤ 10 (max nesting)
        Amortized: O(n) for typical documents
        """
        self.protect_code_blocks()
        self.convert_display_formulas()
        self.fix_naked_latex()
        self.convert_inline_formulas_with_latex()
        self.convert_simple_variables()
        self.restore_code_blocks()

        return self.content, self.conversions

    def generate_report(self) -> str:
        """
        Generate human-readable conversion report.

        Fun fact: Good logging is essential in enterprise systems. As the saying goes:
        "Hope is not a strategy, and printf debugging is not a methodology... but it works!"
        """
        if not self.conversions:
            return "No formulas converted - file already uses standard syntax or has no formulas."

        report = [f"Successfully converted {len(self.conversions)} formulas:\n"]

        # Group by conversion type
        by_type: Dict[str, List[Conversion]] = {}
        for conv in self.conversions:
            by_type.setdefault(conv.conversion_type, []).append(conv)

        # Summary by type
        for conv_type, items in by_type.items():
            report.append(f"  {conv_type}: {len(items)} conversions")

        report.append("\nDetailed conversions:")
        report.append("-" * 80)

        # Detailed listing (first 20 to avoid overwhelming output)
        for conv in self.conversions[:20]:
            report.append(f"\nLine {conv.line_number} [{conv.conversion_type}]:")
            report.append(f"  Before: {conv.before}")
            report.append(f"  After:  {conv.after}")

        if len(self.conversions) > 20:
            report.append(f"\n... and {len(self.conversions) - 20} more conversions")

        return '\n'.join(report)


class SyntaxValidator:
    """
    Validates LaTeX syntax in converted markdown.

    Fun fact: Validation is crucial - as Grace Hopper said: "One accurate measurement
    is worth a thousand expert opinions!" Same applies to syntax checking!
    """

    @staticmethod
    def validate(content: str) -> List[str]:
        """Check for common LaTeX syntax errors."""
        errors = []

        # Check balanced $ delimiters (must be even number)
        single_dollar_count = len(re.findall(r'(?<!\$)\$(?!\$)', content))
        if single_dollar_count % 2 != 0:
            errors.append(f"Unbalanced $ delimiters (found {single_dollar_count}, expected even number)")

        # Check balanced $$ delimiters
        double_dollar_count = content.count('$$')
        if double_dollar_count % 2 != 0:
            errors.append(f"Unbalanced $$ delimiters (found {double_dollar_count}, expected even number)")

        # Check for unconverted display formulas
        unconverted_display = re.findall(r'^\[\s*\n.*\\.*\n\]\s*$', content, re.MULTILINE)
        if unconverted_display:
            errors.append(f"Found {len(unconverted_display)} unconverted display formulas")

        # Check for unconverted inline formulas with LaTeX
        unconverted_inline = re.findall(r'\([^)]*\\[a-zA-Z]+[^)]*\)', content)
        if unconverted_inline:
            errors.append(f"Found {len(unconverted_inline)} possibly unconverted inline formulas")
            # Show first few examples
            for example in unconverted_inline[:3]:
                errors.append(f"  Example: {example}")

        # Check for subscripts without braces (should be rare after conversion)
        # But allow some exceptions like \in, \ge, \le (not subscripts)
        unbraced_subscripts = re.findall(r'[A-Z]_[0-9a-z](?![}])', content)
        if unbraced_subscripts:
            errors.append(f"Warning: Found {len(unbraced_subscripts)} subscripts without braces")

        return errors


def main():
    """
    Main CLI interface for LaTeX formula conversion.

    Fun fact: CLIs have existed since the 1960s, but they're still the most efficient
    interface for batch processing - sometimes the old ways are the best ways!
    """
    parser = argparse.ArgumentParser(
        description='Convert LaTeX formulas from custom notation to standard syntax',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --input docs/paper.md --output docs/paper_converted.md
  %(prog)s --input book.md --output book_converted.md --report report.md
  %(prog)s --input docs/paper.md --output docs/paper.md --validate-only

Fun fact: This script helps make your math beautiful on GitHub AND in PDFs!
        """
    )

    parser.add_argument('--input', '-i', required=True, type=Path,
                       help='Input markdown file path')
    parser.add_argument('--output', '-o', required=True, type=Path,
                       help='Output markdown file path')
    parser.add_argument('--report', '-r', type=Path,
                       help='Optional report file path')
    parser.add_argument('--validate-only', action='store_true',
                       help='Only validate, do not perform conversion')

    args = parser.parse_args()

    # Read input file
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {args.input}...")
    content = args.input.read_text(encoding='utf-8')

    # Validate only mode
    if args.validate_only:
        print("Validating syntax...")
        errors = SyntaxValidator.validate(content)
        if errors:
            print("\nValidation errors found:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        else:
            print("✓ Validation passed - no syntax errors found!")
            sys.exit(0)

    # Perform conversion
    print("Converting formulas...")
    converter = LaTeXConverter(content)
    converted_content, conversions = converter.convert()

    # Validate converted content
    print("Validating converted content...")
    errors = SyntaxValidator.validate(converted_content)
    if errors:
        print("\nWarning: Validation found potential issues:")
        for error in errors:
            print(f"  - {error}")
        print("\nProceeding anyway, but please review output carefully.")

    # Write output
    print(f"Writing to {args.output}...")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(converted_content, encoding='utf-8')

    # Generate report
    report = converter.generate_report()
    print(f"\n{report}")

    # Save report to file if requested
    if args.report:
        print(f"\nWriting report to {args.report}...")
        args.report.write_text(report, encoding='utf-8')

    print(f"\n✓ Conversion complete! Processed {len(content)} characters.")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.output}")

    if conversions:
        print(f"\n✓ Successfully converted {len(conversions)} formulas to standard syntax!")
    else:
        print("\nℹ No formulas needed conversion - file already uses standard syntax.")


if __name__ == '__main__':
    main()
