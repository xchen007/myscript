#!/usr/bin/env python3
"""
JIRA Sprint Analyzer - Analyze sprint worklog and statistics
"""

import argparse
import configparser
import json
import re
import subprocess
import sys
import os
import shlex
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


def parse_jira_datetime(date_str: str) -> Optional[datetime]:
    """Parse JIRA datetime string (e.g. '2026-04-21T05:55:20.000-0700')."""
    if not date_str:
        return None
    try:
        # Normalize timezone: -0700 → -07:00 (required by fromisoformat)
        normalized = re.sub(r'([+-])(\d{2})(\d{2})$', r'\1\2:\3', date_str)
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def classify_week(dt: datetime) -> str:
    """Return 'this week', 'last week', or 'YYYY-MM-DD' for the given datetime."""
    today = datetime.now(tz=dt.tzinfo).date() if dt.tzinfo else datetime.now().date()
    target = dt.date()
    days_since_monday = today.weekday()  # 0=Mon, 6=Sun
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(weeks=1)
    if target >= this_monday:
        return "this week"
    elif target >= last_monday:
        return "last week"
    return target.strftime('%Y-%m-%d')


def display_width(s: str) -> int:
    """Calculate display width accounting for CJK double-width characters"""
    width = 0
    for ch in s:
        cp = ord(ch)
        if (0x1100 <= cp <= 0x115F or
                0x2E80 <= cp <= 0x303E or
                0x3041 <= cp <= 0xA4CF or
                0xAC00 <= cp <= 0xD7AF or
                0xF900 <= cp <= 0xFAFF or
                0xFE10 <= cp <= 0xFE1F or
                0xFE30 <= cp <= 0xFE4F or
                0xFF00 <= cp <= 0xFF60 or
                0xFFE0 <= cp <= 0xFFE6):
            width += 2
        else:
            width += 1
    return width


def pad_cell(s: str, width: int) -> str:
    """Left-pad string to display width, accounting for wide characters"""
    return s + ' ' * max(0, width - display_width(s))


def make_hyperlink(text: str, url: str) -> str:
    """Wrap text in OSC 8 terminal hyperlink escape sequence"""
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def print_table(headers: List[str], rows: List[List[str]], title: str = "",
                col_overrides: Dict[int, int] = None,
                cell_formatters: Dict[int, Any] = None):
    """Print a formatted ASCII table with CJK-aware column widths.
    col_overrides:    {col_index: forced_width}
    cell_formatters:  {col_index: fn(raw_cell) -> formatted_str}
                      Formatters may add invisible escape codes; width is
                      always calculated from the raw cell value.
    """
    if not rows:
        return

    # Calculate column widths using display_width (from raw cell values)
    col_widths = []
    for i, header in enumerate(headers):
        max_width = display_width(header)
        for row in rows:
            if i < len(row):
                max_width = max(max_width, display_width(str(row[i])))
        col_widths.append(max_width)

    # Apply any forced overrides
    if col_overrides:
        for idx, width in col_overrides.items():
            if 0 <= idx < len(col_widths):
                col_widths[idx] = width

    # Print title if provided
    if title:
        print(f"\n{title}")

    sep_width = sum(col_widths) + len(headers) * 3 - 1

    # Print header
    header_row = " │ ".join(pad_cell(h, col_widths[i]) for i, h in enumerate(headers))
    print(f" {header_row} ")
    print("─" * sep_width)

    # Print rows — apply cell_formatters AFTER padding calculation
    for row in rows:
        cells = []
        for i in range(len(headers)):
            raw = str(row[i]) if i < len(row) else ''
            padding = ' ' * max(0, col_widths[i] - display_width(raw))
            if cell_formatters and i in cell_formatters:
                cells.append(cell_formatters[i](raw) + padding)
            else:
                cells.append(raw + padding)
        print(f" {' │ '.join(cells)} ")

    print()


class JiraAnalyzer:
    CONFIG_FILE = os.path.expanduser('~/.my_jira_config')
    
    def __init__(self, user: str, label: str, jira_url: str = None,
                 show_report: bool = False):
        self.user = user
        self.label = label
        self.jira_url = jira_url.rstrip('/') if jira_url else None
        self.show_report = show_report
        self.jira_bin = self._find_jira_bin()
        self.tickets = []

    @staticmethod
    def _find_jira_bin() -> str:
        """Locate the jira_cli binary via PATH. Returns full path or 'jira_cli' as fallback."""
        import shutil
        found = shutil.which('jira_cli')
        if found:
            return found
        return 'jira_cli'

    @classmethod
    def load_config(cls) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Load configuration from ~/.my_jira_config"""
        if not os.path.exists(cls.CONFIG_FILE):
            return None, None, None
        
        try:
            config = configparser.ConfigParser()
            config.read(cls.CONFIG_FILE)
            
            user = config.get('jira', 'user', fallback=None)
            label = config.get('jira', 'label', fallback=None)
            jira_url = config.get('jira', 'jira_url', fallback=None)
            return user, label, jira_url
        except Exception as e:
            print(f"⚠️  Error reading config file: {e}", file=sys.stderr)
            return None, None, None

    # Error messages that indicate "no data" rather than a real failure
    NO_RESULT_PATTERNS = ['No result found', 'no result found']

    def run_command(self, cmd: str, retry_count: int = 3) -> Optional[str]:
        """Execute jira CLI command with retry mechanism.
        Returns None on real failure, '' (empty string) when no results found."""
        # Source ~/.zshrc to get env vars (JIRA_API_TOKEN etc.), suppress its output
        shell_path = os.environ.get('SHELL', '/bin/zsh')
        wrapped_cmd = f"{shell_path} -c 'source ~/.zshrc >/dev/null 2>&1; {cmd}'"
        for attempt in range(retry_count):
            try:
                result = subprocess.run(
                    wrapped_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    return result.stdout.strip()

                # Detect "no results" — not a real error, no need to retry
                stderr = result.stderr or ''
                if any(p in stderr for p in self.NO_RESULT_PATTERNS):
                    return ''  # signal: command succeeded but zero results

                if attempt == retry_count - 1:
                    print(f"❌ Command failed after {retry_count} attempts: {cmd}", file=sys.stderr)
                    print(f"   Error: {stderr}", file=sys.stderr)
                else:
                    print(f"⚠️  Retry attempt {attempt + 1}/{retry_count} for: {cmd}", file=sys.stderr)
            except subprocess.TimeoutExpired:
                if attempt == retry_count - 1:
                    print(f"❌ Command timeout after {retry_count} attempts: {cmd}", file=sys.stderr)
                else:
                    print(f"⚠️  Timeout, retrying ({attempt + 1}/{retry_count})...", file=sys.stderr)
            except Exception as e:
                if attempt == retry_count - 1:
                    print(f"❌ Error executing command: {e}", file=sys.stderr)
                else:
                    print(f"⚠️  Error, retrying ({attempt + 1}/{retry_count})...", file=sys.stderr)

        return None

    def fetch_ticket_list(self) -> List[str]:
        """Fetch ticket list from JIRA"""
        print(f"📋 Step 1: Fetching ticket list for user '{self.user}' with label '{self.label}'...", file=sys.stderr)

        cmd = f"{self.jira_bin} issue list --raw -a {self.user} --label {self.label}"
        output = self.run_command(cmd)

        if output is None:
            print("❌ Failed to fetch ticket list", file=sys.stderr)
            return []

        if output == '':
            print(f"ℹ️  未找到 label='{self.label}' 的 tickets", file=sys.stderr)
            return []

        try:
            tickets_data = json.loads(output)
            tickets = [t['key'] for t in tickets_data]
            print(f"✓ Found {len(tickets)} tickets", file=sys.stderr)
            return tickets
        except (json.JSONDecodeError, KeyError) as e:
            print(f"❌ Failed to parse ticket list: {e}", file=sys.stderr)
            return []

    def fetch_ticket_details(self, ticket: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a ticket (including worklog)"""
        cmd = f"{self.jira_bin} issue view {ticket} --raw"
        output = self.run_command(cmd)
        
        if not output:
            return None
        
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return None

    def extract_worklog_time(self, issue_data: Dict[str, Any]) -> float:
        """Extract total worklog time in hours"""
        try:
            fields = issue_data.get('fields', {})
            worklog = fields.get('worklog', {})
            worklogs = worklog.get('worklogs', [])
            
            total_seconds = sum(log.get('timeSpentSeconds', 0) for log in worklogs)
            return total_seconds / 3600  # Convert to hours
        except Exception:
            return 0.0

    def _extract_done_label(self, fields: Dict[str, Any]) -> str:
        """Return 'this week'/'last week'/'YYYY-MM-DD' for Resolved/Closed tickets.

        Priority: Closed time (fields['updated']) > Resolved time (fields['resolutiondate']).
        Returns '' for all other statuses or when neither date is available.
        """
        status = fields.get('status', {}).get('name', '')
        if status not in ('Resolved', 'Closed'):
            return ''

        # For Closed tickets the last update is the close action; for Resolved use resolutiondate
        if status == 'Closed':
            dt = parse_jira_datetime(fields.get('updated')) or \
                 parse_jira_datetime(fields.get('resolutiondate'))
        else:  # Resolved
            dt = parse_jira_datetime(fields.get('resolutiondate')) or \
                 parse_jira_datetime(fields.get('updated'))

        return classify_week(dt) if dt else ''

    def process_tickets(self, tickets: List[str]):
        """Process each ticket and collect data"""
        print(f"🔍 Step 2: Fetching details for {len(tickets)} tickets...", file=sys.stderr)
        
        for idx, ticket in enumerate(tickets, 1):
            if idx % 50 == 1 or idx == len(tickets):
                print(f"  [{idx}/{len(tickets)}] {ticket}", file=sys.stderr)
            
            details = self.fetch_ticket_details(ticket)
            if not details:
                continue
            
            try:
                fields = details.get('fields', {})
                
                ticket_info = {
                    'key': ticket,
                    'type': fields.get('issuetype', {}).get('name', 'N/A'),
                    'status': fields.get('status', {}).get('name', 'N/A'),
                    'priority': fields.get('priority', {}).get('name', 'N/A'),
                    'summary': fields.get('summary', 'N/A'),
                    'estimated_time': (fields.get('timeoriginalestimate') or 0) / 3600,
                    'log_time': self.extract_worklog_time(details),
                    'done_label': self._extract_done_label(fields),
                }
                
                self.tickets.append(ticket_info)
                    
            except Exception as e:
                print(f"⚠️  Error processing ticket {ticket}: {e}", file=sys.stderr)
                continue
        
        print(f"✓ Processed {len(self.tickets)} tickets successfully", file=sys.stderr)

    # Sort order definitions
    TYPE_ORDER = {'Epic': 0, 'Story': 1, 'Task': 2, 'Sub-task': 3, 'Bug': 4}
    STATUS_ORDER = {'Open': 0, 'In Progress': 1, 'In Review': 2, 'Resolved': 3, 'Closed': 4}

    def _ticket_sort_key(self, ticket: Dict[str, Any]) -> tuple:
        """Sort by: type > status > ticket number"""
        type_rank = self.TYPE_ORDER.get(ticket['type'], 99)
        status_rank = self.STATUS_ORDER.get(ticket['status'], 99)
        # Extract numeric part from ticket key (e.g. SDSTOR-21930 -> 21930)
        key_parts = ticket['key'].rsplit('-', 1)
        ticket_num = int(key_parts[1]) if len(key_parts) == 2 and key_parts[1].isdigit() else 0
        return (type_rank, status_rank, ticket_num)

    def generate_report(self):
        """Generate report with formatted tables"""
        # Header
        print("\n" + "="*80)
        print("# JIRA Sprint 分析报告".center(80))
        print("="*80)
        print(f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"查询参数: 用户={self.user}, Label={self.label}\n")
        
        # Ticket Summary Table (sorted by type > status > ticket number)
        print("\n## Ticket 汇总")
        print("-" * 80)
        headers = ["Ticket", "类型", "状态", "优先级", "Estimated", "Log Time", "完成", "标题"]
        sorted_tickets = sorted(self.tickets, key=self._ticket_sort_key)

        # Calculate title column width from full (untruncated) titles
        max_title_width = max(
            (display_width(t['summary']) for t in sorted_tickets),
            default=display_width("标题")
        )

        rows = []
        for ticket in sorted_tickets:
            est = ticket.get('estimated_time', 0)
            rows.append([
                ticket['key'],
                ticket['type'],
                ticket['status'],
                ticket['priority'],
                f"{est:.2f}h" if est else '-',
                f"{ticket['log_time']:.2f}h",
                ticket.get('done_label', ''),
                ticket['summary'],
            ])

        # Ticket column: clickable hyperlink if jira_url is configured
        formatters = {}
        if self.jira_url:
            formatters[0] = lambda key: make_hyperlink(key, f"{self.jira_url}/browse/{key}")

        print_table(headers, rows, col_overrides={7: max_title_width},
                    cell_formatters=formatters if formatters else None)

        # Overall Statistics
        print("\n## 统计\n")
        print("-" * 50)
        total_tickets = len(self.tickets)
        total_log_time = sum(t['log_time'] for t in self.tickets)
        avg_log_time = total_log_time / total_tickets if total_tickets > 0 else 0

        print(f"  总 Ticket 数:      {total_tickets}")
        print(f"  总 Log Time:       {total_log_time:.2f} 小时")
        print(f"  平均 Log Time:     {avg_log_time:.2f} 小时\n")

        # Report table
        if self.show_report:
            self.generate_sprint_report()

    def generate_sprint_report(self):
        """Print a plain-text report table for sharing (no hyperlinks, full URLs)."""
        sorted_tickets = sorted(self.tickets, key=self._ticket_sort_key)

        print("\n## Sprint 报告")
        print("-" * 80)

        base_url = self.jira_url or 'https://jira'
        headers = ["Ticket URL", "状态", "Estimated", "Log Time", "标题", "完成"]

        max_url_width = max(
            (display_width(f"{base_url}/browse/{t['key']}") for t in sorted_tickets),
            default=display_width("Ticket URL")
        )
        max_title_width = max(
            (display_width(t['summary']) for t in sorted_tickets),
            default=display_width("标题")
        )

        rows = []
        for t in sorted_tickets:
            url = f"{base_url}/browse/{t['key']}"
            est = t.get('estimated_time', 0)
            rows.append([
                url,
                t['status'],
                f"{est:.2f}h" if est else '-',
                f"{t['log_time']:.2f}h",
                t['summary'],
                t.get('done_label', ''),
            ])

        print_table(headers, rows, col_overrides={0: max_url_width, 4: max_title_width})

        # Footer: summarise which weeks tickets were completed
        week_counts: Dict[str, int] = defaultdict(int)
        for t in sorted_tickets:
            label = t.get('done_label', '')
            if label:
                week_counts[label] += 1
        if week_counts:
            summary_parts = [f"{label}: {cnt} tickets"
                             for label, cnt in sorted(week_counts.items())]
            print(f"\n  ✅ 完成汇总: {', '.join(summary_parts)}\n")

    def run(self):
        """Main execution"""
        try:
            # Fetch and process tickets
            tickets = self.fetch_ticket_list()
            if not tickets:
                return  # message already printed in fetch_ticket_list
            
            self.process_tickets(tickets)
            
            # Generate and print report
            self.generate_report()
            
        except KeyboardInterrupt:
            print("\n❌ Operation cancelled by user", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    # Load config file first
    config_user, config_label, config_jira_url = JiraAnalyzer.load_config()
    
    parser = argparse.ArgumentParser(
        description='Analyze JIRA sprint worklog and statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  Settings can be loaded from ~/.my_jira_config:
    [jira]
    user = xchen17
    label = SDS-CP-Sprint08-2026
    jira_url = https://jirap.corp.ebay.com

Examples:
  # Use config file values (summary only)
  python jira_analyzer.py
  
  # Show sprint report table
  python jira_analyzer.py -r
  
  # Show everything (summary + report)
  python jira_analyzer.py --all
        """
    )
    
    parser.add_argument(
        '-u', '--user',
        default=config_user,
        help=f'JIRA assignee username (default from config: {config_user or "not set"})'
    )
    parser.add_argument(
        '-l', '--label',
        default=config_label,
        help=f'JIRA label to filter tickets (default from config: {config_label or "not set"})'
    )
    parser.add_argument(
        '-r', '--report',
        action='store_true',
        help='Show sprint report table (plain URLs, suitable for sharing)'
    )
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help='Show all information (equivalent to -r)'
    )

    args = parser.parse_args()

    # --all enables every section
    if args.all:
        args.report = True
    
    # Validate required parameters
    if not args.user or not args.label:
        print("❌ Error: Both --user and --label are required", file=sys.stderr)
        if not config_user or not config_label:
            print("\nConfiguration file ~/.my_jira_config not found or incomplete.", file=sys.stderr)
            print("Please create it with the following content:\n", file=sys.stderr)
            print("  [jira]", file=sys.stderr)
            print("  user = your_username", file=sys.stderr)
            print("  label = your_label", file=sys.stderr)
            print("  jira_url = https://your-jira-instance.com", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        sys.exit(1)
    
    analyzer = JiraAnalyzer(
        user=args.user,
        label=args.label,
        jira_url=config_jira_url,
        show_report=args.report
    )
    analyzer.run()


if __name__ == '__main__':
    main()
