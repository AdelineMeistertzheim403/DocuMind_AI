"""CI release metadata: immutable image digests and explicitly supported database revision."""
import argparse
import ast
import json
from pathlib import Path
import re

REGISTRY='registry.adelinemeistertzheim.fr'
COMPONENTS={'backend':'BACKEND_IMAGE','frontend':'FRONTEND_IMAGE','postgres':'POSTGRES_IMAGE'}


def schema_head(root):
    revisions={}
    for path in (root/'migrations/versions').glob('*.py'):
        values={}
        for node in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(node,ast.Assign):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id in {'revision','down_revision'}:
                        values[target.id]=ast.literal_eval(node.value)
        revisions[values['revision']]=values['down_revision']
    heads=set(revisions)-{value for value in revisions.values() if value}
    if len(heads)!=1:raise ValueError('Exactly one migration head is required')
    return heads.pop()


def validate_release(data):
    if not isinstance(data,dict) or data.get('format')!=1 or not re.fullmatch(r'[a-f0-9]{40}',str(data.get('git_sha',''))):
        raise ValueError('Invalid release identity')
    if set(data.get('images',{}))!=set(COMPONENTS):raise ValueError('Three pinned image references are required')
    for name in COMPONENTS:
        if not re.fullmatch(re.escape(f'{REGISTRY}/documind-ai/{name}@sha256:')+r'[a-f0-9]{64}',str(data['images'][name])):
            raise ValueError('Unexpected registry, component or digest')
    revision=data.get('schema_revision')
    if not isinstance(revision,str) or not re.fullmatch(r'[a-zA-Z0-9_]+',revision):raise ValueError('Invalid schema revision')
    if data.get('supported_schema_revisions')!=[revision]:raise ValueError('Only the tested schema revision is supported')
    if 'security_profile' in data and (data['security_profile']!='public-beta-2026-10-v1' or revision!='0007'):
        raise ValueError('Unrecognized release security profile')
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sha',required=True)
    parser.add_argument('--backend',required=True)
    parser.add_argument('--frontend',required=True)
    parser.add_argument('--postgres',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--security-profile',choices=['public-beta-2026-10-v1'])
    args=parser.parse_args()
    head=schema_head(Path('.'))
    data={'format':1,'git_sha':args.sha,'schema_revision':head,'supported_schema_revisions':[head],
        'images':{name:f'{REGISTRY}/documind-ai/{name}@{getattr(args,name)}' for name in COMPONENTS}}
    if args.security_profile:data['security_profile']=args.security_profile
    data=validate_release(data)
    args.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
