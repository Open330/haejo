"""Resize an observed macOS window through AXSize or its window-bound resize grip."""
import argparse
import json
import math
import re
from .flow import Selector


def main(argv, driver):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target')
    parser.add_argument('--helper', required=True, action='store_true')
    parser.add_argument('--window', help='exact observed window title')
    parser.add_argument('--width', type=float, required=True)
    parser.add_argument('--height', type=float, required=True)
    args = parser.parse_args(argv)
    if not all(math.isfinite(n) and 0 < n <= 16384 for n in (args.width, args.height)):
        parser.error('width and height must be positive points, at most 16384')
    if 'action.resize_window' not in getattr(driver, 'capabilities', ()):
        print(json.dumps({'type': 'error', 'error': 'resize_unavailable', 'effect': 'not_started',
                          'detail': 'update the signed helper'}))
        return 1
    observation = driver.observe(args.target, 'tree_full')
    if observation.get('type') != 'observation':
        print(json.dumps(observation, ensure_ascii=False))
        return 1
    indices = (Selector(role='Window', title=args.window).resolve_all(observation['tree']) if args.window else
               [int(match.group(1)) for line in observation['tree'].splitlines()
                if (match := re.match(r'^(\d+) Window(?:\s|$)', line))])
    if len(indices) != 1:
        print(json.dumps({'type': 'error', 'error': 'window_missing_or_ambiguous',
                          'effect': 'not_started', 'detail': 'specify --window with an exact observed title'}))
        return 1
    result = driver.act(observation['obs_id'], args.target,
                        {'name': 'resize_window', 'element_index': indices[0],
                         'width': args.width, 'height': args.height},
                        risk_class='preapproved', approved=True, intent_text='Requested window resize')
    from .access_log import current
    if current.get() is not None:
        current.get().task_result(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('type') == 'acted' and result.get('size_verified') is True else 1
