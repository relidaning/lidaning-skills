import json
import sys
path = sys.argv[1]
with open(path) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get('type')
        if t == 'summary':
            print('SUMMARY:', obj.get('summary'))
            continue
        msg = obj.get('message')
        if not msg:
            continue
        role = msg.get('role')
        content = msg.get('content')
        if isinstance(content, str):
            print(f'--- {role} ---')
            print(content[:2000])
        elif isinstance(content, list):
            for c in content:
                ctype = c.get('type')
                if ctype == 'text':
                    print(f'--- {role} text ---')
                    print(c.get('text')[:2000])
                elif ctype == 'tool_use':
                    print(f'--- {role} tool_use: {c.get("name")} ---')
                    inp = c.get('input')
                    s = json.dumps(inp)
                    print(s[:800])
                elif ctype == 'tool_result':
                    cont = c.get('content')
                    if isinstance(cont, list):
                        for cc in cont:
                            if cc.get('type') == 'text':
                                print('--- tool_result ---')
                                print(cc.get('text')[:800])
                    elif isinstance(cont, str):
                        print('--- tool_result ---')
                        print(cont[:800])
