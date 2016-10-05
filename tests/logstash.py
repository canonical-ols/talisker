import json
import yaml
import sys
import subprocess
import shlex


config_path = 'talisker/logstash/config'
input_path = 'talisker/logstash/input'

tmpl = """
input { stdin { type => %(type)s }}
%(filter)s
output { stdout { codec => json_lines }}
"""


inputs = [t['input'] for t in suite['tests'].values()]
filter = open(suite['filter']).read()
with open(config_path, 'w') as f:
    f.write(tmpl % dict(
        path='/opt/logstash/input', filter=filter, type=suite['type']))

cmd = shlex.split(
    '{0}/bin/logstash --quiet -f {0}/patterns/config'.format(
    '/opt/logstash'))

try:
    output = subprocess.check_output(
        ['lxc', 'exec', 'logstash', '--'] + cmd,
        input=('\n'.join(inputs).encode('utf8')),
    )
except Exception as e:
    print(e.stdout)

lines = output.decode('utf8').splitlines()

for json_line, (name, test) in zip(lines, suite['tests'].items()):
    if json_line.startswith('{:'):
        continue
    out = json.loads(json_line)
    for k, v in test['expected'].items():
        assert out[k] == v



