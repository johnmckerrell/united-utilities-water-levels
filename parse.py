#!/usr/bin/env python3
"""Parse git history of reservoir-levels.html into data.json"""

import subprocess
import json
import re
import sys

MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def parse_date_str(s):
    m = re.match(r'(\d{1,2})\w*\s+(\w+)\s+(\d{4})', s.strip())
    if m:
        day, month_name, year = m.groups()
        month = MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def strip_tags(s):
    s = re.sub(r'<[^>]+>', '', s).strip()
    return (s
            .replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            .replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' '))


def parse_pct(s):
    s = strip_tags(s).rstrip('%').strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_html(html):
    result = {'date': None, 'reservoirs': [], 'thirlmereDepth': None}

    # --- Date ---
    # New format (2023+): <th scope="col"><strong>17th May 2026</strong></th>
    date_m = re.search(
        r'<th[^>]*scope=["\']col["\'][^>]*>.*?<strong[^>]*>\s*([^<]+?)\s*</strong>',
        html, re.DOTALL
    )
    if not date_m:
        # Old format (2022): first <td> in tbody containing a <strong> with a date
        date_m = re.search(
            r'<td[^>]*>\s*<strong[^>]*>\s*(\d{1,2}\w*\s+\w+\s+\d{4})\s*</strong>\s*</td>',
            html
        )
    if date_m:
        result['date'] = parse_date_str(date_m.group(1))

    # --- Reservoir rows ---
    # Split on <tr so we get individual row blocks, then check each block.
    # New format: <th scope="row">Name</th> + 4 <td>
    # Old format: <td><strong>Name</strong></td> + 4 <td style="...">VALUE</td>
    for block in re.split(r'<tr[\s>]', html):
        name = None
        remaining_html = block

        # New format
        th_m = re.search(r'<th[^>]*scope=["\']row["\'][^>]*>(.*?)</th>', block, re.DOTALL)
        if th_m:
            name = strip_tags(th_m.group(1))
            # tds are everything after the th
            remaining_html = block[th_m.end():]
        else:
            # Old format: first td contains <strong>Name</strong>, rest have % values
            td_m = re.search(r'<td[^>]*>\s*<strong[^>]*>(.*?)</strong>\s*</td>', block, re.DOTALL)
            if td_m:
                candidate = strip_tags(td_m.group(1))
                # Only treat as a name if it doesn't look like a date or column header
                if candidate and not re.search(r'\d{4}|Actual|Change|Average|Last year', candidate):
                    name = candidate
                    remaining_html = block[td_m.end():]

        if not name:
            continue

        tds = re.findall(r'<td[^>]*>(.*?)</td>', remaining_html, re.DOTALL)

        if len(tds) >= 4:
            result['reservoirs'].append({
                'name': name,
                'actual': parse_pct(tds[0]),
                'change': parse_pct(tds[1]),
                'avgYear': parse_pct(tds[2]),
                'lastYear': parse_pct(tds[3]),
            })
        elif len(tds) == 1 and 'thirlmere' in name.lower() and 'metr' in name.lower():
            depth_str = strip_tags(tds[0]).strip()
            try:
                result['thirlmereDepth'] = float(depth_str)
            except ValueError:
                pass

    return result


def main():
    log_out = subprocess.run(
        ['git', 'log', '--format=%H %as', '--', 'reservoir-levels.html'],
        capture_output=True, text=True
    ).stdout.strip()

    if not log_out:
        print("No commits found", file=sys.stderr)
        sys.exit(1)

    commits = [(line.split()[0], line.split()[1]) for line in log_out.splitlines() if line.strip()]
    print(f"Processing {len(commits)} commits...", file=sys.stderr)

    records = []
    seen_dates = set()

    for i, (commit_hash, commit_date) in enumerate(commits):
        if i % 50 == 0:
            print(f"  {i}/{len(commits)}", file=sys.stderr)

        result = subprocess.run(
            ['git', 'show', f'{commit_hash}:reservoir-levels.html'],
            capture_output=True, text=True, errors='replace'
        )
        if result.returncode != 0 or not result.stdout:
            continue

        data = parse_html(result.stdout)
        date_key = data['date'] or commit_date

        if not date_key or date_key in seen_dates:
            continue
        seen_dates.add(date_key)

        if data['reservoirs']:
            records.append({
                'date': date_key,
                'reservoirs': data['reservoirs'],
                'thirlmereDepth': data['thirlmereDepth'],
            })

    records.sort(key=lambda r: r['date'])

    with open('data.json', 'w') as f:
        json.dump(records, f, separators=(',', ':'))

    print(f"Wrote {len(records)} records to data.json", file=sys.stderr)


if __name__ == '__main__':
    main()
