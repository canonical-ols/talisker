import sys

import requests
from prometheus_client.parser import text_string_to_metric_families
from sparklines import sparklines


data = requests.get(sys.argv[1])
output = []

for metric in text_string_to_metric_families(data.text):
    if metric.type == 'histogram':
        buckets = [(float(s[1]['le']), s[2]) for s in metric.samples if 'le' in s[1]]
        buckets.sort()
        deacc = []
        for (b1, v1), (b2, v2) in reversed(list(zip(buckets, buckets[1:]))):
            deacc.append(v2 - v1)
        deacc.append(buckets[0][1])
        line = sparklines(list(reversed(deacc)))[0]
    elif metric.type == 'counter':
        line = metric.samples[0][2]
    output.append((metric.name, line))

width = max(len(s[0]) for s in output)


for name, line in output:
    print('{:{width}} {}\n'.format(name, line, width=str(width+2)))
