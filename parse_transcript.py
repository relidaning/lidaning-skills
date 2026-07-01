import json

with open('/home/shake/.claude/projects/-data-apps-lidaning-skills/3218759a-a10b-4afe-a169-acc7cc5b0113.jsonl') as f:
    lines = f.readlines()

for i, line in enumerate(lines, start=1):
    line = line.strip()
    if not line:
        continue
    obj = json.loads(line)
    t = obj.get('type', '')

    if t == 'user' and 'message' in obj:
        msg = obj['message']
        content = msg.get('content', '')
        if isinstance(content, str) and content and not content.startswith('<'):
            print(f'[{i}] USER: {content[:600]}')
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    if b.get('type') == 'text':
                        txt = b.get('text', '')
                        skip = txt.startswith('Base directory') or txt.startswith('<')
                        if txt and len(txt) > 20 and not skip:
                            print(f'[{i}] USER_TEXT: {txt[:600]}')

    if t == 'assistant' and 'message' in obj:
        msg = obj['message']
        if isinstance(msg, dict):
            content = msg.get('content', [])
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get('type') == 'text':
                        txt = b.get('text', '')
                        if txt and len(txt) > 30:
                            print(f'[{i}] ASST: {txt[:800]}')
                            print()
