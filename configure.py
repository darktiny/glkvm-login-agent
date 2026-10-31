#!/usr/bin/env python3
"""Interactive device setup. The Mac password is supplied only at invocation."""
import getpass,json,os
from pathlib import Path
root=Path(__file__).resolve().parent
os.umask(0o077)
c=json.loads((root/'config.example.json').read_text())
for key,prompt,name in [('kvm_password_file','GLKVM admin password: ','kvm-password'),('api_key_file','DeepSeek API key: ','deepseek-key')]:
    if key=='kvm_password_file' and (root/name).exists():
        c[key]=str(root/name)
        continue
    value=getpass.getpass(prompt)
    if not value or any(x in value for x in '\r\n\x00'):raise SystemExit('Invalid secret')
    fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:f.write(value)
    c[key]=str(root/name)
c['decoder']=str(root/'ffmpeg')
(root/'config.json').write_text(json.dumps(c,indent=2)+'\n')
print('Configured. Supply --password for each login invocation.')
