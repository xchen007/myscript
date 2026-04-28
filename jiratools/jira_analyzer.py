#!/usr/bin/env python3
"""
JIRA Sprint Analyzer - Analyze sprint worklog and statistics
"""

import argparse
import json
import re
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

from utils.shell import run_local_cmd, test_binary
from utils.display import display_width, make_hyperlink, print_table
from utils.concurrent import run_concurrent


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


def _adf_to_text(node: Any) -> str:
    """Recursively extract plain text from an Atlassian Document Format (ADF) node."""
    if not isinstance(node, dict):
        return node if isinstance(node, str) else ''
    ntype = node.get('type', '')
    if ntype == 'text':
        return node.get('text', '')
    if ntype == 'hardBreak':
        return '\n'
    if ntype == 'mention':
        return node.get('attrs', {}).get('text', '')
    text = ''.join(_adf_to_text(c) for c in node.get('content', []))
    if ntype in ('paragraph', 'heading'):
        return text + '\n'
    if ntype == 'listItem':
        return '• ' + text.rstrip('\n') + '\n'
    return text


class JiraAnalyzer:
    def __init__(self, user: str, label: str | list[str], jira_bin: str,
                 jira_url: str = None, show_report: bool = False,
                 show_json: bool = False, epic: str = None):
        self.user = user
        # Accept a single string or a list of labels
        if isinstance(label, list):
            self.labels = [l.strip() for l in label if l.strip()]
        else:
            self.labels = [l.strip() for l in label.split(',') if l.strip()]
        self.label = ','.join(self.labels)  # raw string for backward compat
        self.jira_bin = jira_bin
        self.jira_url = jira_url.rstrip('/') if jira_url else None
        # Browse URL uses the web UI host (strip -cli suffix, e.g. jirap-cli → jirap)
        import re as _re
        self.browse_url = _re.sub(r'-cli(?=\.)', '', self.jira_url) if self.jira_url else None
        self.show_report = show_report
        self.show_json = show_json
        self.epic = epic
        self.tickets = []

    def test_connection(self) -> bool:
        """Test whether the configured jira_bin is callable."""
        return test_binary(self.jira_bin)

    # Error messages that indicate "no data" rather than a real failure
    NO_RESULT_PATTERNS = ['No result found', 'no result found']

    def run_command(self, cmd: str, retry_count: int = 3) -> Optional[str]:
        """Execute jira CLI command with retry mechanism.
        Returns None on real failure, '' (empty string) when no results found."""
        for attempt in range(retry_count):
            try:
                result = run_local_cmd(
                    cmd,
                    use_login_shell=True,
                    timeout=30,
                    check=False,
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
            except Exception as e:
                if attempt == retry_count - 1:
                    print(f"❌ Error executing command: {e}", file=sys.stderr)
                else:
                    print(f"⚠️  Error, retrying ({attempt + 1}/{retry_count})...", file=sys.stderr)

        return None

    def _fetch_for_label(self, label: str) -> tuple:
        """Fetch ticket keys for a single label. Returns (label, keys)."""
        cmd = f"{self.jira_bin} issue list --raw -a {self.user} --label {label}"
        output = self.run_command(cmd)
        if output is None or output == '':
            return (label, [])
        try:
            data = json.loads(output)
            return (label, [t['key'] for t in data])
        except (json.JSONDecodeError, KeyError):
            return (label, [])

    def fetch_ticket_lists(self) -> Dict[str, List[str]]:
        """Fetch ticket lists for all labels. Deduplicates across labels (first-label-wins)."""
        print(f"📋 Step 1: Fetching ticket lists for {len(self.labels)} label(s)...", file=sys.stderr)

        if len(self.labels) == 1:
            lbl = self.labels[0]
            _, keys = self._fetch_for_label(lbl)
            print(f"✓ Found {len(keys)} tickets", file=sys.stderr)
            return {lbl: keys}

        results = run_concurrent(self.labels, self._fetch_for_label, max_workers=5)

        seen: set[str] = set()
        label_tickets: Dict[str, List[str]] = {}
        total = 0
        for label, keys in results:
            unique = [k for k in keys if k not in seen]
            seen.update(unique)
            label_tickets[label] = unique
            total += len(unique)
            print(f"  ✓ [{label}] {len(unique)} tickets", file=sys.stderr)

        print(f"✓ Found {total} tickets across {len(self.labels)} label(s)", file=sys.stderr)
        return label_tickets

    def fetch_epic_tickets(self) -> List[str]:
        """Fetch all sub-ticket keys under an Epic using 'jira epic list'."""
        print(f"📋 Fetching tickets for Epic {self.epic}...", file=sys.stderr)
        cmd = f'{self.jira_bin} epic list {self.epic} --raw'
        output = self.run_command(cmd)
        if output is None or output == '':
            print(f"✓ Found 0 tickets", file=sys.stderr)
            return []
        try:
            lines = output.strip().split('\n')
            if len(lines) < 2:
                print(f"✓ Found 0 tickets", file=sys.stderr)
                return []
            # TSV with multi-tab alignment: TYPE  KEY  SUMMARY  STATUS  ...
            # Filter empty strings from split to handle consecutive tabs
            keys = []
            for line in lines[1:]:
                cols = [c for c in line.split('\t') if c]
                if len(cols) >= 2 and cols[1].strip():
                    keys.append(cols[1].strip())
            print(f"✓ Found {len(keys)} tickets", file=sys.stderr)
            return keys
        except Exception:
            print(f"⚠️  Failed to parse epic ticket list", file=sys.stderr)
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
        """Extract total worklog time in hours for self.user only"""
        try:
            fields = issue_data.get('fields', {})
            worklog = fields.get('worklog', {})
            worklogs = worklog.get('worklogs', [])

            total_seconds = sum(
                log.get('timeSpentSeconds', 0) for log in worklogs
                if self._is_user_worklog(log)
            )
            return total_seconds / 3600  # Convert to hours
        except Exception:
            return 0.0

    def _is_user_worklog(self, log: Dict[str, Any]) -> bool:
        """Check if a worklog entry belongs to self.user."""
        author = log.get('author', {})
        return (author.get('name', '') == self.user
                or author.get('key', '') == self.user
                or author.get('accountId', '') == self.user)

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

    def _parse_ticket_details(self, ticket: str, details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse raw JIRA issue JSON into a normalised ticket dict."""
        try:
            fields = details.get('fields', {})

            raw_desc = fields.get('description')
            if isinstance(raw_desc, dict):
                description = _adf_to_text(raw_desc).strip()
            elif isinstance(raw_desc, str):
                description = raw_desc.strip()
            else:
                description = ''

            assignee_field = fields.get('assignee') or {}
            assignee = assignee_field.get('displayName') or assignee_field.get('name') or ''

            points = None
            for sp_field in ('story_points', 'customfield_10016', 'customfield_10028', 'customfield_10004'):
                val = fields.get(sp_field)
                if val is not None:
                    try:
                        points = float(val)
                        break
                    except (TypeError, ValueError):
                        pass

            # Collect per-worklog entries with date (for daily chart) — user only
            worklog_entries = []
            for wl in fields.get('worklog', {}).get('worklogs', []):
                if not self._is_user_worklog(wl):
                    continue
                started = wl.get('started', '')
                seconds = wl.get('timeSpentSeconds', 0)
                if started and seconds:
                    worklog_entries.append({'date': started[:10], 'seconds': seconds})

            return {
                'key': ticket,
                'type': fields.get('issuetype', {}).get('name', 'N/A'),
                'status': fields.get('status', {}).get('name', 'N/A'),
                'priority': fields.get('priority', {}).get('name', 'N/A'),
                'summary': fields.get('summary', 'N/A'),
                'description': description,
                'assignee': assignee,
                'points': points,
                'estimated_time': (fields.get('timeoriginalestimate') or 0) / 3600,
                'log_time': self.extract_worklog_time(details),
                'done_label': self._extract_done_label(fields),
                'worklog_entries': worklog_entries,
                'labels': fields.get('labels', []),
            }
        except Exception as e:
            print(f"⚠️  Error processing ticket {ticket}: {e}", file=sys.stderr)
            return None

    def _fetch_and_parse(self, ticket: str) -> Optional[Dict[str, Any]]:
        """Fetch a single ticket's details and parse them (thread-safe)."""
        details = self.fetch_ticket_details(ticket)
        if not details:
            return None
        return self._parse_ticket_details(ticket, details)

    def process_tickets(self, label_tickets: Dict[str, List[str]]):
        """Process each ticket concurrently and collect data with label tag."""
        all_keys: List[str] = []
        key_label_map: Dict[str, str] = {}
        for lbl, keys in label_tickets.items():
            for key in keys:
                all_keys.append(key)
                key_label_map[key] = lbl

        print(f"🔍 Step 2: Fetching details for {len(all_keys)} tickets...", file=sys.stderr)

        def on_progress(completed: int, total: int, ticket: str):
            if completed == 1 or completed == total:
                print(f"  [{completed}/{total}] {ticket}", file=sys.stderr)

        results = run_concurrent(
            all_keys,
            self._fetch_and_parse,
            max_workers=5,
            progress=on_progress,
        )

        self.tickets = []
        for r in results:
            if r is not None:
                r['label'] = key_label_map.get(r['key'], self.labels[0] if self.labels else '')
                self.tickets.append(r)

    def process_epic_tickets(self, keys: List[str]):
        """Process ticket list from epic query (no label tagging)."""
        print(f"🔍 Fetching details for {len(keys)} tickets...", file=sys.stderr)

        def on_progress(completed: int, total: int, ticket: str):
            if completed == 1 or completed == total:
                print(f"  [{completed}/{total}] {ticket}", file=sys.stderr)

        results = run_concurrent(
            keys,
            self._fetch_and_parse,
            max_workers=5,
            progress=on_progress,
        )

        self.tickets = []
        for r in results:
            if r is not None:
                r['label'] = ''
                self.tickets.append(r)

        print(f"✓ Processed {len(self.tickets)} tickets successfully", file=sys.stderr)

    # Sort order definitions
    TYPE_ORDER = {'Epic': 0, 'Story': 1, 'Task': 2, 'Sub-task': 3, 'Bug': 4}
    STATUS_ORDER = {'Open': 0, 'In Progress': 1, 'In Review': 2, 'Resolved': 3, 'Closed': 4}
    PRIORITY_ORDER = {
        'Blocker': 0, 'Critical': 1, 'Highest': 1,
        'High': 2, 'Major': 2,
        'Medium': 3, 'Normal': 3,
        'Minor': 4, 'Low': 4,
        'Trivial': 5, 'Lowest': 5,
    }

    def _ticket_sort_key(self, ticket: Dict[str, Any]) -> tuple:
        """Sort by: type > status > ticket number"""
        type_rank = self.TYPE_ORDER.get(ticket['type'], 99)
        status_rank = self.STATUS_ORDER.get(ticket['status'], 99)
        # Extract numeric part from ticket key (e.g. SDSTOR-21930 -> 21930)
        key_parts = ticket['key'].rsplit('-', 1)
        ticket_num = int(key_parts[1]) if len(key_parts) == 2 and key_parts[1].isdigit() else 0
        return (type_rank, status_rank, ticket_num)

    def generate_json_output(self):
        """Output structured JSON for GUI consumption.

        Emits a single sentinel line to stdout:
          __SPRINT_TABLE_JSON__:<json>
        All progress messages continue to go to stderr.
        """
        sorted_tickets = sorted(self.tickets, key=self._ticket_sort_key)

        tickets_data = []
        for t in sorted_tickets:
            url = f"{self.browse_url}/browse/{t['key']}" if self.browse_url else None
            project = t['key'].rsplit('-', 1)[0]
            tickets_data.append({
                'key': t['key'],
                'project': project,
                'type': t['type'],
                'type_rank': self.TYPE_ORDER.get(t['type'], 99),
                'status': t['status'],
                'status_rank': self.STATUS_ORDER.get(t['status'], 99),
                'priority': t['priority'],
                'priority_rank': self.PRIORITY_ORDER.get(t['priority'], 99),
                'summary': t['summary'],
                'description': t.get('description', ''),
                'assignee': t.get('assignee', ''),
                'points': t.get('points'),
                'estimated_seconds': int((t.get('estimated_time', 0) or 0) * 3600),
                'log_seconds': int((t.get('log_time', 0) or 0) * 3600),
                'done_label': t.get('done_label', ''),
                'url': url,
                'labels': t.get('labels', []),
            })

        total_log_seconds = sum(t['log_seconds'] for t in tickets_data)
        n = len(tickets_data)

        week_summary: Dict[str, int] = defaultdict(int)
        status_counts: Dict[str, int] = defaultdict(int)
        type_counts: Dict[str, int] = defaultdict(int)
        for t in tickets_data:
            if t['done_label']:
                week_summary[t['done_label']] += 1
            status_counts[t['status']] += 1
            type_counts[t['type']] += 1

        total_points = sum((t.get('points') or 0) for t in tickets_data)

        # Aggregate worklog entries by (date, label)
        daily_agg: Dict[tuple, int] = defaultdict(int)
        for t in self.tickets:
            for entry in t.get('worklog_entries', []):
                daily_agg[(entry['date'], t['label'])] += entry['seconds']
        daily_log = [{'date': d, 'seconds': s, 'label': l}
                     for (d, l), s in sorted(daily_agg.items())]

        # Aggregate by (week_start_monday, label)
        weekly_agg: Dict[tuple, int] = defaultdict(int)
        for e in daily_log:
            dt = datetime.strptime(e['date'], '%Y-%m-%d')
            week_start = (dt - timedelta(days=dt.weekday())).strftime('%Y-%m-%d')
            weekly_agg[(week_start, e['label'])] += e['seconds']
        weekly_log = [{'week': w, 'seconds': s, 'label': l}
                      for (w, l), s in sorted(weekly_agg.items())]

        stats = {
            'total_tickets': n,
            'total_log_seconds': total_log_seconds,
            'avg_log_seconds': total_log_seconds // n if n else 0,
            'total_points': total_points,
            'week_summary': dict(sorted(week_summary.items())),
            'status_counts': dict(status_counts),
            'type_counts': dict(type_counts),
        }

        meta = {
            'user': self.user,
            'label': self.label,
            'labels': self.labels,
            'epic': self.epic,
            'generated_at': datetime.now().isoformat(),
            'schema_version': 2,
        }

        payload = {'tickets': tickets_data, 'stats': stats, 'meta': meta,
                   'daily_log': daily_log, 'weekly_log': weekly_log}
        print(f"__SPRINT_TABLE_JSON__:{json.dumps(payload, ensure_ascii=False)}", flush=True)

    def generate_report(self):
        """Generate report with formatted tables"""
        if self.show_json:
            self.generate_json_output()
            return

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
        if self.browse_url:
            formatters[0] = lambda key: make_hyperlink(key, f"{self.browse_url}/browse/{key}")

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

        base_url = self.browse_url or 'https://jira'
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
            if self.epic:
                # Epic mode: fetch all sub-tickets under the epic
                keys = self.fetch_epic_tickets()
                if not keys:
                    if self.show_json:
                        self.generate_json_output()
                    return
                self.process_epic_tickets(keys)
            else:
                # Sprint mode: fetch by user + label
                label_tickets = self.fetch_ticket_lists()
                all_empty = all(len(v) == 0 for v in label_tickets.values())
                if all_empty:
                    if self.show_json:
                        self.generate_json_output()
                    return
                self.process_tickets(label_tickets)
            
            # Generate and print report
            self.generate_report()
            
        except KeyboardInterrupt:
            print("\n❌ Operation cancelled by user", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Unexpected error: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze JIRA sprint worklog and statistics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with all required arguments
  jira-analyzer --jira-bin /path/to/jira_cli -u xchen17 -l SDS-CP-Sprint08-2026

  # Test jira command connectivity
  jira-analyzer --jira-bin /path/to/jira_cli --test

  # Show sprint report table
  jira-analyzer --jira-bin /path/to/jira_cli -u xchen17 -l SDS-CP-Sprint08-2026 -r

  # Output JSON for GUI
  jira-analyzer --jira-bin /path/to/jira_cli -u xchen17 -l SDS-CP-Sprint08-2026 --json
        """
    )

    parser.add_argument(
        '--jira-bin',
        required=True,
        help='Path to the jira CLI binary'
    )
    parser.add_argument(
        '-u', '--user',
        help='JIRA assignee username'
    )
    parser.add_argument(
        '-l', '--label',
        action='append',
        dest='labels',
        help='JIRA label to filter tickets (repeatable, or comma-separated)'
    )
    parser.add_argument(
        '--jira-url',
        help='JIRA instance base URL (e.g. https://jirap.corp.ebay.com)'
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
    parser.add_argument(
        '-j', '--json',
        action='store_true',
        help='Output structured JSON for GUI consumption (suppresses text tables)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test whether the jira CLI command is reachable and exit'
    )
    parser.add_argument(
        '--epic',
        help='Epic ticket key (e.g. SDSTOR-21000). Fetches all sub-tickets under this epic.'
    )

    args = parser.parse_args()

    # --all enables every section
    if args.all:
        args.report = True

    # --test mode: verify command and exit
    if args.test:
        analyzer = JiraAnalyzer(user='_test_', label='_test_', jira_bin=args.jira_bin)
        sys.exit(0 if analyzer.test_connection() else 1)

    # Epic mode: only --epic and --jira-bin required
    if args.epic:
        analyzer = JiraAnalyzer(
            user=args.user or '',
            label=[],
            jira_bin=args.jira_bin,
            jira_url=args.jira_url,
            show_report=args.report,
            show_json=args.json,
            epic=args.epic,
        )
        analyzer.run()
        return

    # Validate required parameters for sprint mode
    if not args.user or not args.labels:
        print("❌ Error: Both --user and --label are required", file=sys.stderr)
        parser.print_help(file=sys.stderr)
        sys.exit(1)

    # Flatten comma-separated labels from all --label args
    all_labels: list[str] = []
    for raw in args.labels:
        all_labels.extend(l.strip() for l in raw.split(',') if l.strip())

    analyzer = JiraAnalyzer(
        user=args.user,
        label=all_labels,
        jira_bin=args.jira_bin,
        jira_url=args.jira_url,
        show_report=args.report,
        show_json=args.json,
    )
    analyzer.run()


if __name__ == '__main__':
    main()
